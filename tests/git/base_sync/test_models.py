# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Auto-rebase contexts, requests, snapshots, and decisions."""

from __future__ import annotations

import dataclasses
import unittest
from pathlib import Path

from orchestrator.git.base_sync import models
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.state import WorkflowLabel

_PENDING_FIELD = "pending_auto_base_rebase_push_sha"

_PRE_REBASE_SHA = "abc1234"

_SPEC = "spec-sentinel"

_ISSUE = "issue-sentinel"

_WORKTREE = Path("/tmp/worktree")


class _StubClient:
    """Minimal stand-in for the one client call `to_context` makes."""

    def __init__(self, label: WorkflowLabel | None) -> None:
        self.label = label
        self.labelled_issue = None

    def workflow_label(self, issue: object) -> WorkflowLabel | None:
        self.labelled_issue = issue
        return self.label


def _request(gh: _StubClient, state: PinnedState) -> models._AutoRebaseRequest:
    """Build the refresh's request around the given client and state."""
    return models._AutoRebaseRequest(
        gh=gh,
        spec=_SPEC,
        issue=_ISSUE,
        state=state,
        worktree=_WORKTREE,
        pr_number=7,
        behind=3,
    )


class AutoRebaseRequestTest(unittest.TestCase):
    """The refresh's request derives the two fields a context adds."""

    def test_to_context_derives_label_and_sha(self) -> None:
        state = PinnedState(state_data={_PENDING_FIELD: _PRE_REBASE_SHA})
        gh = _StubClient(WorkflowLabel.VALIDATING)

        context = _request(gh, state).to_context(_PENDING_FIELD)

        self.assertEqual(context.label, WorkflowLabel.VALIDATING)
        self.assertEqual(context.pending_pre_rebase_sha, _PRE_REBASE_SHA)
        self.assertIs(gh.labelled_issue, _ISSUE)

    def test_to_context_carries_the_request_fields(self) -> None:
        # Everything the caller already assembled has to survive the
        # conversion untouched: a context built from a request is the same
        # attempt, not a re-derived one.
        state = PinnedState(state_data={})
        gh = _StubClient(None)
        request = _request(gh, state)

        context = request.to_context(_PENDING_FIELD)

        self.assertIs(context.gh, gh)
        self.assertIs(context.spec, request.spec)
        self.assertIs(context.issue, request.issue)
        self.assertIs(context.state, state)
        self.assertEqual(context.worktree, request.worktree)
        self.assertEqual(context.pr_number, request.pr_number)
        self.assertEqual(context.behind, request.behind)

    def test_to_context_leaves_an_unpinned_sha_none(self) -> None:
        # A first attempt has nothing pinned yet, so the recovery path can tell
        # "never started" apart from "interrupted between rebase and push".
        context = _request(_StubClient(None), PinnedState(state_data={})).to_context(
            _PENDING_FIELD,
        )

        self.assertIsNone(context.pending_pre_rebase_sha)
        self.assertIsNone(context.label)


class ModelDefaultsTest(unittest.TestCase):
    """Optional fields default so callers omit what their case does not use."""

    def test_recovery_context_defaults(self) -> None:
        context = models._AutoRebaseRecoveryContext(
            gh=_StubClient(None),
            spec=_SPEC,
            issue=_ISSUE,
            state=PinnedState(state_data={}),
            worktree=_WORKTREE,
            pr_number=7,
            label=WorkflowLabel.VALIDATING,
            pending_pre_rebase_sha=_PRE_REBASE_SHA,
        )

        self.assertEqual(context.behind, 0)
        self.assertIsNone(context.unparking_consumed_max)

    def test_recovery_snapshot_defaults(self) -> None:
        snapshot = models._AutoRebaseRecoverySnapshot(
            branch="issue-7",
            local_head=_PRE_REBASE_SHA,
        )

        self.assertEqual(snapshot.remote_head, "")
        self.assertEqual(snapshot.ahead, 0)
        self.assertEqual(snapshot.behind, 0)

    def test_decision_defaults_to_no_consumed_comment(self) -> None:
        decision = models._AutoRebaseDecision(should_continue=True)

        self.assertIsNone(decision.consumed_comment_id)


class FrozenModelTest(unittest.TestCase):
    """The models are frozen so an attempt's inputs cannot drift mid-flow."""

    def test_models_reject_attribute_assignment(self) -> None:
        frozen_cases = (
            (models._AutoRebaseDecision(should_continue=False), "should_continue"),
            (
                models._AutoRebaseRecoverySnapshot(branch="issue-7", local_head=_PRE_REBASE_SHA),
                "local_head",
            ),
            (_request(_StubClient(None), PinnedState(state_data={})), "behind"),
        )
        for instance, field_name in frozen_cases:
            with self.subTest(model=type(instance).__name__), self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(instance, field_name, "edited")


if __name__ == "__main__":
    unittest.main()
