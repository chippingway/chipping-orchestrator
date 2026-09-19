# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures for the read-only relabel guard and the handoff it accepts.

Both modules beside this one drive a whole implementing tick against an issue
an operator moved here while a `discussion` park was still on it, so they share
the seed and the two probes that decide what the guard sees.

The discussion stage's wire vocabulary is spelled out here rather than borrowed
from that stage's own test support: what these modules pin down is how THIS
stage reads pinned state it did not write, so the strings are part of the
contract under test and a shared constant would let a rename pass unnoticed on
the side that has to keep understanding it.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.worktrees import (
    paths as _worktree_paths,
    recovery as _worktree_recovery,
)
from orchestrator.workflow.engine import content_hash as _content_hash
from orchestrator.workflow.stages.implementing import handler as _implementing
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    KEY_PARK_REASON,
    LABEL_IMPLEMENTING,
    _agent,
    _issue_branch,
    _reported,
)

PUSH_BRANCH = "_push_branch"
COUNT_ADDED_LINES = "_count_added_lines"
ANCHOR_PR_WORKTREE = "_anchor_pr_worktree"
RUN_AGENT = "run_agent"
ENSURE_PR_WORKTREE = "_ensure_pr_worktree"
ENSURE_WORKTREE = "_ensure_worktree"

KEY_PR_NUMBER = "pr_number"
KEY_ROUND_BRANCH = "discussion_round_branch"
KEY_ROUND_SHA = "discussion_round_sha"
KEY_PLAN_PATH = "discussion_plan_path"
KEY_PLAN_SHA = "discussion_plan_sha"
KEY_PUBLISHING_SHA = "discussion_publishing_sha"
KEY_ROUND_OPEN = "discussion_round_open"
KEY_READ_ONLY_BASELINE = "read_only_baseline_sha"
KEY_HANDOFF_ANCHOR = "read_only_anchor_sha"
PARK_DISCUSSION_COMMITS = "discussion_commits"
PARK_DISCUSSION_PLAN_PUBLISHED = "discussion_plan_published"
PARK_DISCUSSION_RESPONSE = "discussion_response"
PARK_DISCUSSION_UNSAFE_RELABEL = "discussion_unsafe_relabel"
DISCUSSION_SESSION = "d-sess-1"

HEAD_BEFORE_ROUND = "head-before-the-round"
HEAD_AFTER_COMMIT = "head-after-the-agent-committed"

RELABEL_WATERMARK = 77000
UNEXPECTED_AGENT_MESSAGE = "should not run"
DEV_SESSION = "dev-sess"

_TEMP_PREFIX = "ro-relabel-"
_WORKTREE_PATH = "_worktree_path"
_BRANCH_HAS_UNPUSHED_COMMITS = "_branch_has_unpushed_commits"


def _seed_relabeled_discussion(
    issue_number: int, park_reason: str | None, **extra,
):
    """An issue an operator moved to `implementing` while discussion held it.

    The anchor is seeded because that is the shape a real park leaves: every
    exit the discussion stage takes records the branch and SHA its round
    opened on, and none of its parks withdraws the pair.

    The current body hash is seeded for a subtler reason. Without one the
    drift hook snapshots it, and that is a pinned-state write of its own on
    the same object -- it would persist whatever else the tick had staged and
    hide a handoff that was never durably written.

    A `park_reason` of `None` is the issue AFTER the guard accepted that
    relabel: the clear drops the flags durably before anything is spawned, so
    that is the only shape from which this stage can have pushed anything. Every
    other seeded value is overridable through `extra` for the same reason --
    what the guard leaves behind differs from what it was handed, and a test
    about the later shape has to be able to say so.
    """
    gh = FakeGitHubClient()
    issue = make_issue(issue_number, label=LABEL_IMPLEMENTING)
    gh.add_issue(issue)
    gh.seed_state(
        issue.number,
        **{
            "awaiting_human": park_reason is not None,
            "park_reason": park_reason,
            "discussion_agent": config.DECOMPOSE_AGENT_SPEC,
            "discussion_session_id": DISCUSSION_SESSION,
            "last_action_comment_id": RELABEL_WATERMARK,
            "user_content_hash": _content_hash._compute_user_content_hash(issue, set()),
            KEY_ROUND_BRANCH: _issue_branch(issue_number),
            KEY_ROUND_SHA: HEAD_BEFORE_ROUND,
            **extra,
        },
    )
    return gh, issue


class _RelabelStageCall:
    """One implementing tick with the worktree and branch probes pinned."""

    def __init__(self, gh, issue, worktree, unpushed_branch) -> None:
        self._gh = gh
        self._issue = issue
        self._worktree = worktree
        self._unpushed_branch = unpushed_branch

    def __call__(self) -> None:
        with (
            patch.object(
                _worktree_paths, _WORKTREE_PATH, return_value=self._worktree,
            ),
            patch.object(
                _worktree_recovery,
                _BRANCH_HAS_UNPUSHED_COMMITS,
                return_value=self._unpushed_branch,
            ),
        ):
            _implementing._handle_implementing(self._gh, _TEST_SPEC, self._issue)


class _ReadOnlyRelabelMixin:
    """Drive one implementing tick against a checkout that is on disk."""

    def _run_implementing_on_worktree(
        self, gh, issue, *, unpushed_branch, **run_options,
    ):
        """Both probes are patched from inside the call rather than around it:
        the hermetic seam set installs its own `_branch_has_unpushed_commits`,
        so a patch applied outside would be the one overridden.
        """
        with tempfile.TemporaryDirectory(prefix=_TEMP_PREFIX) as parent:
            worktree = Path(parent) / f"issue-{issue.number}"
            worktree.mkdir(parents=True, exist_ok=True)
            return self._run(
                _RelabelStageCall(gh, issue, worktree, unpushed_branch),
                **run_options,
            )

    def _assert_relabel_allowed(self, issue_number: int, park_reason: str) -> None:
        """One certified-tip relabel: the dev runs and the park is dropped.

        `has_new_commits` is True throughout, which is the only setting
        consistent with the ahead-of-base branch this scenario is about --
        both probes count commits against `<remote>/<base>`, so a branch the
        guard sees carrying commits is one the spawn path sees carrying them
        too. Letting it answer False would hide the whole defect: the guard
        would certify the branch and the recovered-worktree shortcut would
        then skip the implementer and republish those commits as its work.
        """
        gh, issue = _seed_relabeled_discussion(issue_number, park_reason)

        mocks = self._run_implementing_on_worktree(
            gh,
            issue,
            unpushed_branch=_issue_branch(issue.number),
            run_agent=_agent(session_id=DEV_SESSION, last_message=_reported()),
            has_new_commits=True,
            branch_tip_sha=HEAD_BEFORE_ROUND,
            head_shas=(HEAD_BEFORE_ROUND, HEAD_BEFORE_ROUND, HEAD_AFTER_COMMIT),
        )

        spawned = mocks[RUN_AGENT]
        spawned.assert_called_once()
        self.assertIn("You are the implementer", spawned.call_args.args[1])
        pinned_data = gh.pinned_data(issue.number)
        self.assertNotEqual(
            pinned_data.get(KEY_PARK_REASON), PARK_DISCUSSION_UNSAFE_RELABEL,
        )
        self.assertFalse(pinned_data.get(KEY_AWAITING_HUMAN))
        # The anchor goes with the park: the branch is the dev's from here.
        self.assertIsNone(pinned_data.get(KEY_ROUND_SHA))

    def _run_implementing_without_checkout(self, gh, issue, **run_options):
        """The same tick on a host that has no checkout for this issue at all.

        A fresh clone, or an operator's cleanup: the directory is gone and so is
        the local ref, which is the state every local probe reads as nothing to
        answer for. The path is pointed inside a temp dir that is never created,
        so `exists()` is false for real rather than by a mock.
        """
        with tempfile.TemporaryDirectory(prefix=_TEMP_PREFIX) as parent:
            missing = Path(parent) / f"issue-{issue.number}"
            return self._run(
                _RelabelStageCall(gh, issue, missing, None), **run_options,
            )
