# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures the discussion-stage tests share.

The stage discusses and waits until the humans confirm a design, so the two
assertions most modules below repeat are that nothing was published (no push,
no PR, no relabel) and that the worktree the round ran in is still on disk for
the next round and the operator to read. The one exit those do not describe is
the plan PR, which is covered on its own in `test_publication.py`.

`_run_discussion` seeds a HEAD that does not move across the round, because a
round is only read as having committed when the SHA it opened on changes under
it. A test about commits says so by overriding `head_shas`, and a moved HEAD is
read once more than it is moved: the publication check reads the tip it would
publish before deciding whether the branch is publishable at all.

What a conversation's LATER rounds are seeded and driven by lives beside this
in `discussion_resume_test_support.py`, since a park's durable record is a
fixture of its own shape.
"""
from __future__ import annotations

import contextlib
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.workflow.stages.discussion import handler as _discussion
from tests.support.fakes import FakeGitHubClient, FakeLabel, make_issue
from tests.workflow.fixtures import (
    _TEST_SPEC,
    LABEL_DISCUSSION,
    _PatchedWorkflowMixin,
)
from tests.workflow.git_owners import seam_patch

KEY_BASE_SHA = "discussion_base_sha"
KEY_BRANCH = "branch"
KEY_DISCUSSION_AGENT = "discussion_agent"
KEY_DISCUSSION_SESSION_ID = "discussion_session_id"
KEY_LAST_DISCUSSION_AT = "last_discussion_at"
KEY_PLAN_PATH = "discussion_plan_path"
KEY_PLAN_SHA = "discussion_plan_sha"
KEY_PR_NUMBER = "pr_number"
KEY_PUBLISHING_SHA = "discussion_publishing_sha"
KEY_ROUND_BRANCH = "discussion_round_branch"
KEY_ROUND_OPEN = "discussion_round_open"
KEY_ROUND_SHA = "discussion_round_sha"

PARK_DISCUSSION_RESPONSE = "discussion_response"
PARK_DISCUSSION_COMMITS = "discussion_commits"
PARK_DISCUSSION_DIRTY = "discussion_dirty"
PARK_DISCUSSION_PLAN_INVALID = "discussion_plan_invalid"
PARK_DISCUSSION_PLAN_PUBLISHED = "discussion_plan_published"
PARK_DISCUSSION_PUSH_FAILED = "discussion_push_failed"
PARK_DISCUSSION_SILENT = "discussion_silent"
PARK_DISCUSSION_STALE_PUBLISH = "discussion_stale_publication"
PARK_DISCUSSION_UNATTRIBUTED = "discussion_plan_unattributed"
PARK_DISCUSSION_STRANDED = "discussion_stranded"
PARK_DISCUSSION_TIMEOUT = "discussion_timeout"
PARK_DISCUSSION_UNREADABLE = "discussion_unreadable_worktree"

# The park an entirely different stage left on the issue before an operator
# relabeled it here: it awaits a human, but not one this stage ever asked.
PARK_FOREIGN_QUESTION = "agent_question"

HEAD_BEFORE_ROUND = "head-before-the-round"
HEAD_AFTER_COMMIT = "head-after-the-agent-committed"
UNMOVED_HEAD = (HEAD_BEFORE_ROUND, HEAD_BEFORE_ROUND)
# A round that moved HEAD is judged on what it committed, so the tip is read a
# third time by the publication check that decides whether it may be pushed.
MOVED_HEAD = (HEAD_BEFORE_ROUND, HEAD_AFTER_COMMIT, HEAD_AFTER_COMMIT)
# A resumed round on a checkout that is really on disk reads HEAD once more
# than an opening one: the hold's anchor check comes before the SHA it opens
# on and the SHA it is judged against.
UNMOVED_HEAD_RESUMED = (HEAD_BEFORE_ROUND,) * 3
MOVED_HEAD_RESUMED = (
    HEAD_BEFORE_ROUND, HEAD_BEFORE_ROUND, HEAD_AFTER_COMMIT, HEAD_AFTER_COMMIT,
)

CLEANUP_DECOMPOSE_WORKTREE = "_cleanup_decompose_worktree"
CLEANUP_QUESTION_WORKTREE = "_cleanup_question_worktree"
CLEANUP_TERMINAL_BRANCH = "_cleanup_terminal_branch"
ENSURE_DECOMPOSE_WORKTREE = "_ensure_decompose_worktree"
ENSURE_PR_WORKTREE = "_ensure_pr_worktree"
ENSURE_WORKTREE = "_ensure_worktree"
BRANCH_TIP_SHA = "_branch_tip_sha"
PUSH_BRANCH = "_push_branch"
AUTHED_TARGET_FETCH = "_authed_target_fetch"
REMOTE_BASE_TIP = "_remote_branch_tip"
RUN_AGENT = "run_agent"
WORKTREE_PATH = "_worktree_path"

COMMITTED_PATHS = "_committed_paths_since"
REVISION_CONTAINS_PATH = "_revision_contains_path"

SPEC_BACKEND = "claude"
SPEC_WITH_ARGS = f"{SPEC_BACKEND} --model claude-opus-5 --effort high"
SPEC_ARGS = ("--model", "claude-opus-5", "--effort", "high")
FLIPPED_SPEC = "codex -m gpt-5"
FLIPPED_BACKEND = "codex"
FLIPPED_ARGS = ("-m", "gpt-5")

DISCUSSION_TOPIC = "should the sink own its own schema?"
DISCUSSION_RESPONSE = "Two branches: own it, or borrow the writer's."
DISCUSSION_SESSION = "d-sess-1"

RESUME_SESSION_ID = "resume_session_id"

DIRTY_FILE_COUNT = 15
DIRTY_DISPLAY_LIMIT = 10
DIRTY_OVERFLOW_COUNT = DIRTY_FILE_COUNT - DIRTY_DISPLAY_LIMIT


@contextlib.contextmanager
def _configured_spec(agent_spec: str, backend: str, extra_args: tuple):
    """Run under one configured decomposer identity, args included.

    A bare backend cannot show whether a stage stored the spec or only the
    backend, and it cannot show which of two configurations a round ran under,
    so every test about the lock configures a spec that carries args.
    """
    with (
        patch.object(config, "DECOMPOSE_AGENT_SPEC", agent_spec),
        patch.object(config, "DECOMPOSE_AGENT", backend),
        patch.object(config, "DECOMPOSE_AGENT_ARGS", extra_args),
    ):
        yield


@contextlib.contextmanager
def _issue_worktree(issue_number: int):
    """Yield an on-disk per-issue checkout for the length of one tick."""
    with tempfile.TemporaryDirectory(prefix="discussion-worktree-") as parent:
        worktree = Path(parent) / f"issue-{issue_number}"
        worktree.mkdir(parents=True, exist_ok=True)
        yield worktree


def _issue_branch(issue_number: int, *, legacy: bool = False) -> str:
    """The per-issue ref, in either spelling the resolver can hand back.

    `legacy=True` is the pre-namespacing form a long-lived issue can still be
    pinned to, and it is a distinct ref rather than an alias: both can exist in
    the same clone at different tips, which is the whole reason the round
    records which one it opened on.
    """
    if legacy:
        return f"orchestrator/issue-{issue_number}"
    return (
        "orchestrator/chippingway__orchestrator/"
        f"issue-{issue_number}"
    )


def _dirty_files(count: int = DIRTY_FILE_COUNT) -> list[str]:
    return [f"file_{file_index}.py" for file_index in range(count)]


def _seed_discussion(number: int, *, body: str = DISCUSSION_TOPIC):
    gh = FakeGitHubClient()
    issue = make_issue(number, label=LABEL_DISCUSSION, body=body)
    gh.add_issue(issue)
    return gh, issue


def _paused_view(number: int, control_label: str):
    """The `discussion` issue a fresh fetch returns after a mid-run pause.

    The handler's own snapshot deliberately does not carry the control label,
    so a guard that trusted it would publish the round anyway.
    """
    view = make_issue(number, label=LABEL_DISCUSSION)
    view.labels.append(FakeLabel(control_label))
    return view


class _DiscussionWorkflowMixin(_PatchedWorkflowMixin):
    """One discussion tick, and the two things every module asserts about it."""

    def plan_path(self, issue_number: int) -> str:
        """The one path a confirmed round may commit, spelled independently.

        Written out here rather than imported from the owner, so a rename of
        the published path fails a test instead of agreeing with itself -- the
        prompt promises this path and the publication check refuses everything
        else, and both are only as good as their agreement on it.
        """
        return f"plans/issue-{issue_number}.md"

    def remote_reads(self, mocks) -> list:
        """The branches the remote-tip seam was asked about, in order.

        One seam answers two questions -- the base a round pins against and the
        per-issue branch a publication is about to move -- so an assertion about
        either has to say which one it means.
        """
        return [
            call.args[2] for call in mocks[REMOTE_BASE_TIP].call_args_list
        ]

    def assert_nothing_published(self, gh, mocks) -> None:
        """No branch pushed, no PR opened, no label moved -- on any exit."""
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(gh.opened_prs, [])
        self.assertEqual(gh.label_history, [])

    def assert_worktree_preserved(self, mocks) -> None:
        """Every teardown the stage could have reached stayed unused."""
        for teardown in (
            CLEANUP_QUESTION_WORKTREE,
            CLEANUP_TERMINAL_BRANCH,
            CLEANUP_DECOMPOSE_WORKTREE,
        ):
            with self.subTest(teardown=teardown):
                mocks[teardown].assert_not_called()

    def _run_discussion(self, gh, issue, **run_options):
        run_options.setdefault("head_shas", UNMOVED_HEAD)
        return self._run(
            lambda: _discussion._handle_discussion(gh, _TEST_SPEC, issue),
            **run_options,
        )

    def _run_discussion_in_temp_checkout(self, gh, issue, **run_options):
        """Run one tick against a checkout that lives only for that tick.

        For a test whose subject is what the tick makes of a tree that is on
        disk, but that has nothing to say about what is IN it.
        """
        with tempfile.TemporaryDirectory(prefix="discussion-tick-") as tree:
            return self._run_discussion_on_worktree(
                gh, issue, Path(tree), **run_options,
            )

    def _run_discussion_on_worktree(self, gh, issue, worktree, **run_options):
        """Run one tick against a checkout that is really on disk.

        `_worktree_path` is not part of the hermetic seam set, so a test whose
        subject is what the tick finds already in the tree has to point it at
        one that exists.
        """
        with seam_patch(WORKTREE_PATH, MagicMock(return_value=worktree)):
            return self._run_discussion(gh, issue, **run_options)
