# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pickup behavior for unlabeled issues: legacy decompose-off shortcut to
implementing, the `ALLOWED_ISSUE_AUTHORS` allowlist (case-insensitive
match, empty-list disables filter), and the anchors both starts publish before
dispatching a stage in the same tick."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import pickup
from orchestrator.workflow.stages.decomposition import run as _decomposing
from orchestrator.workflow.stages.implementing import handler as _implementing
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import _TEST_SPEC, _agent, _PatchedWorkflowMixin

_DECOMPOSE_CONFIG = "DECOMPOSE"
_ALLOWLIST_CONFIG = "ALLOWED_ISSUE_AUTHORS"
_CLARIFICATION_MESSAGE = "need clarification"
_IMPLEMENTING_LABEL = "workflow:implementing"
_DECOMPOSING_LABEL = "workflow:decomposing"
_ISSUE_NUMBER = 1
_START_DECOMPOSING = "_start_decomposing"
_START_IMPLEMENTING = "_start_implementing"


class _StageDispatchRecorder:
    """Stand in for a stage handler and capture what the issue already
    carried at the moment pickup dispatched it."""

    def __init__(self, github, issue_number: int) -> None:
        self._github = github
        self._issue_number = issue_number
        self.calls: list = []
        self.labels: list = []
        self.state: dict = {}

    def __call__(self, gh, spec, issue, **_route) -> None:
        self.calls.append((gh, spec, issue))
        self.labels = list(self._github.label_history)
        self.state = dict(self._github.pinned_data(self._issue_number))


class HandlePickupTest(unittest.TestCase, _PatchedWorkflowMixin):
    def test_decompose_off_routes_to_implementing(self) -> None:
        # Legacy path retained behind the DECOMPOSE kill switch: an
        # unlabeled issue still goes straight to implementing without a
        # decomposer round, so operators can disable decomposition without
        # redeploying old binaries.
        gh = FakeGitHubClient()
        issue = make_issue(1)
        gh.add_issue(issue)

        with patch.object(config, _DECOMPOSE_CONFIG, False):
            mocks = self._run(
                lambda: pickup._handle_pickup(gh, _TEST_SPEC, issue),
                run_agent=_agent(last_message=_CLARIFICATION_MESSAGE),
                has_new_commits=False,
            )

        self.assertTrue(
            any(":robot: orchestrator picking this up" in body
                for _, body in gh.posted_comments)
        )
        # Pickup flips the label to implementing; downstream handler may park
        # on awaiting_human but does not re-label.
        self.assertEqual(gh.label_history[0], (1, _IMPLEMENTING_LABEL))
        self.assertIn("created_at", gh.pinned_data(1))
        # _handle_implementing was actually entered (codex spawned).
        mocks["run_agent"].assert_called_once()

    def test_nonallowed_author_is_skipped(self) -> None:
        # A populated ALLOWED_ISSUE_AUTHORS allowlist must drop unlabeled
        # issues from outside that list silently -- no comment, no label,
        # no pinned state. This is the abuse guard: a stranger filing
        # issues on a public repo cannot make the orchestrator spawn agents.
        gh = FakeGitHubClient()
        issue = make_issue(1, author="stranger")
        gh.add_issue(issue)

        with patch.object(config, _ALLOWLIST_CONFIG, ("geserdugarov",)):
            mocks = self._run(
                lambda: pickup._handle_pickup(gh, _TEST_SPEC, issue),
                run_agent=_agent(last_message="should not run"),
                has_new_commits=False,
            )

        self.assertEqual(gh.posted_comments, [])
        self.assertEqual(gh.label_history, [])
        self.assertEqual(gh.pinned_data(1), {})
        mocks["run_agent"].assert_not_called()

    def test_pickup_proceeds_for_allowed_author(self) -> None:
        # Sanity: when the author IS in the list, pickup behaves exactly
        # like the unguarded path -- this guard is purely a triage filter.
        gh = FakeGitHubClient()
        issue = make_issue(1, author="alice")
        gh.add_issue(issue)

        with patch.object(config, _ALLOWLIST_CONFIG, ("alice", "bob")), \
             patch.object(config, _DECOMPOSE_CONFIG, False):
            self._run(
                lambda: pickup._handle_pickup(gh, _TEST_SPEC, issue),
                run_agent=_agent(last_message=_CLARIFICATION_MESSAGE),
                has_new_commits=False,
            )

        self.assertIn((1, _IMPLEMENTING_LABEL), gh.label_history)
        self.assertIn("created_at", gh.pinned_data(1))

    def test_pickup_matches_author_case_insensitively(self) -> None:
        # GitHub logins are case-insensitive: "Alice" and "alice" resolve
        # to the same account. The allowlist must accept either casing on
        # both sides so a maintainer's mixed-case configuration doesn't
        # silently reject legitimate issues.
        gh = FakeGitHubClient()
        issue = make_issue(1, author="Alice")
        gh.add_issue(issue)

        with patch.object(config, _ALLOWLIST_CONFIG, ("alice",)), \
             patch.object(config, _DECOMPOSE_CONFIG, False):
            self._run(
                lambda: pickup._handle_pickup(gh, _TEST_SPEC, issue),
                run_agent=_agent(last_message=_CLARIFICATION_MESSAGE),
                has_new_commits=False,
            )

        self.assertIn((1, _IMPLEMENTING_LABEL), gh.label_history)

    def test_empty_allowlist_lets_anyone_through(self) -> None:
        # Default config: empty tuple disables the filter so existing
        # single-user setups (and any deployment that hasn't opted in)
        # keep their current "anyone can trigger" behavior.
        gh = FakeGitHubClient()
        issue = make_issue(1, author="random-user")
        gh.add_issue(issue)

        with patch.object(config, _ALLOWLIST_CONFIG, ()), \
             patch.object(config, _DECOMPOSE_CONFIG, False):
            self._run(
                lambda: pickup._handle_pickup(gh, _TEST_SPEC, issue),
                run_agent=_agent(last_message=_CLARIFICATION_MESSAGE),
                has_new_commits=False,
            )

        self.assertIn((1, _IMPLEMENTING_LABEL), gh.label_history)


class PickupOwnerPatchTest(unittest.TestCase):
    """The owner reaches its own two starts and the stage handlers by module
    attribute, so the owning module is where a patch has to land."""

    def test_decompose_switch_selects_the_owner_start(self) -> None:
        selections = (
            (True, _START_DECOMPOSING, _START_IMPLEMENTING),
            (False, _START_IMPLEMENTING, _START_DECOMPOSING),
        )
        for decompose, taken_name, skipped_name in selections:
            with self.subTest(decompose=decompose):
                self._assert_start_selected(decompose, taken_name, skipped_name)

    def test_start_dispatches_stage_after_publishing(self) -> None:
        dispatches = (
            (
                pickup._start_decomposing,
                _decomposing,
                "_handle_decomposing",
                _DECOMPOSING_LABEL,
            ),
            (
                pickup._start_implementing,
                _implementing,
                "_handle_implementing",
                _IMPLEMENTING_LABEL,
            ),
        )
        for start, stage_owner, handler_name, label in dispatches:
            with self.subTest(handler=handler_name):
                self._assert_dispatched(start, stage_owner, handler_name, label)

    def _assert_start_selected(
        self, decompose: bool, taken_name: str, skipped_name: str,
    ) -> None:
        github = FakeGitHubClient()
        issue = make_issue(_ISSUE_NUMBER)
        github.add_issue(issue)

        with patch.object(config, _DECOMPOSE_CONFIG, decompose), \
             patch.object(pickup, _START_DECOMPOSING), \
             patch.object(pickup, _START_IMPLEMENTING):
            pickup._handle_pickup(github, _TEST_SPEC, issue)
            getattr(pickup, skipped_name).assert_not_called()
            self._assert_started(getattr(pickup, taken_name), github, issue)

    def _assert_started(self, start, github, issue) -> None:
        start.assert_called_once()
        self.assertEqual(start.call_args.args[:3], (github, _TEST_SPEC, issue))
        # The creation stamp is the only field pickup itself stages; the start
        # it hands the fresh state to owns every other one.
        self.assertIsNotNone(start.call_args.args[3].get("created_at"))

    def _assert_dispatched(
        self, start, stage_owner, handler_name: str, label: str,
    ) -> None:
        github = FakeGitHubClient()
        issue = make_issue(_ISSUE_NUMBER)
        github.add_issue(issue)
        recorder = _StageDispatchRecorder(github, _ISSUE_NUMBER)

        with patch.object(stage_owner, handler_name, recorder):
            start(github, _TEST_SPEC, issue, PinnedState())

        # The stage runs in the same tick, and only once the label and the
        # anchors it reads back are already durable on the issue.
        self.assertEqual(recorder.calls, [(github, _TEST_SPEC, issue)])
        self.assertEqual(recorder.labels, [(_ISSUE_NUMBER, label)])
        self.assertIn("pickup_comment_id", recorder.state)
        self.assertIn("user_content_hash", recorder.state)


if __name__ == "__main__":
    unittest.main()
