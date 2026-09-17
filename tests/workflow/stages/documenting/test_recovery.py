# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest

from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
    _agent,
)

# --- Workflow labels this stage routes between --------------------------
from tests.workflow.stages.documenting import (
    documenting_test_support as documenting_support,
)
from tests.workflow.stages.documenting.documenting_assertion_test_support import (
    _assert_referenced_publication,
    _pr_comment_text,
)
from tests.workflow.stages.documenting.documenting_test_support import (
    _BasicDocumentingFixture,
)

DOCUMENTING = "workflow:documenting"
IN_REVIEW = "in_review"
VALIDATING = "workflow:validating"

# --- Dev agent identity pinned into per-issue state ---------------------
DEV_AGENT = "codex"
DEV_SESSION = "dev-sess"

# --- Worktree HEAD SHAs threaded through the docs / recovery flows ------
SHA_BEFORE = documenting_support.SHA_BEFORE
# The head a docs pass leaves the checkout on. Each IS the commit the size
# gate proves that checkout to, because in production they are one read of one
# worktree: the stage names the commit it means to publish and the gate
# refuses a checkout standing anywhere else, so a fixture that spelled them
# differently would be modelling the race rather than the tick.
SHA_AFTER = MEASURED_CANDIDATE_SHA
SHA_DOCS = MEASURED_CANDIDATE_SHA
SHA_RECOVERED = MEASURED_CANDIDATE_SHA
SHA_PR_HEAD = "pr-head-sha"
# What the pull request stands on once somebody else has landed on it.
MOVED_PUBLICATION = "cafef00d" * 5

# --- Pinned-state field keys read back from `gh.pinned_data(...)` -------
DOCS_VERDICT = "docs_verdict"
DOCS_CHECKED_SHA = "docs_checked_sha"
REVIEW_ROUND = "review_round"
PARK_REASON = "park_reason"
AWAITING_HUMAN = "awaiting_human"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"

# --- Awaiting-human park reasons the docs handler writes ----------------
PARK_PUSH_FAILED = "push_failed"
PARK_AGENT_SILENT = "agent_silent"
PARK_AGENT_TIMEOUT = "agent_timeout"
PARK_DIVERGED = "diverged_branch"
PARK_FETCH_FAILED = "fetch_failed"
PARK_DIRTY = "dirty_worktree"
PARK_AGENT_QUESTION = "agent_question"
PARK_RESET_FAILED = "worktree_reset_failed"

# --- Docs verdict values persisted on a successful pass -----------------
VERDICT_UPDATED = "updated"
VERDICT_NO_CHANGE = "no_change"

# --- Repo docs paths the agent edits / the dirty guard reports ----------
README = "README.md"
DOCS_ARCHITECTURE = "docs/architecture.md"

# --- Mock keys returned by `_PatchedWorkflowMixin._run` -----------------
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"

UNCOMMITTED_CHANGE = "uncommitted change"
TRUSTED_AUTHOR = "alice"
USER_CONTENT_CHANGED = "issue body changed"
AUTHED_FETCH = "_authed_fetch"
ORIGINAL_BODY = "original body"
UPDATED_BODY_AFTER_DOCS = "updated body after prior docs commit"
WORKTREE_PATH = "_worktree_path"
GIT_HARDENED = "_git_hardened"
GIT_REV_LIST = "rev-list"
GIT_RESET = "reset"
GIT_HARD_RESET = "--hard"
GIT_CLEAN = "clean"
GIT_CLEAN_FLAGS = "-fd"
DRIFT_UNWIND_PENDING = "docs_drift_unwind_pending"

MISSING_PR_ISSUE_NUMBER = 101
PARKED_MISSING_PR_ISSUE_NUMBER = 102
COMMIT_REPLY_ISSUE_NUMBER = 401
COMMIT_REPLY_PR_NUMBER = 41
COMMIT_REPLY_COMMENT_ID = 2100
COMMIT_REPLY_WATERMARK = 2000
NO_COMMIT_REPLY_ISSUE_NUMBER = 403
NO_COMMIT_REPLY_PR_NUMBER = 43
NO_COMMIT_REPLY_COMMENT_ID = 3100
NO_COMMIT_REPLY_WATERMARK = 3000
RECOVERED_REPLY_ISSUE_NUMBER = 404
RECOVERED_REPLY_PR_NUMBER = 44
RECOVERED_REPLY_COMMENT_ID = 4100
RECOVERED_REPLY_WATERMARK = 4000
FAILED_PUSH_REPLY_ISSUE_NUMBER = 405
FAILED_PUSH_REPLY_PR_NUMBER = 45
FAILED_PUSH_REPLY_COMMENT_ID = 5100
FAILED_PUSH_REPLY_WATERMARK = 5000
NO_NEW_COMMENT_ISSUE_NUMBER = 402
NO_NEW_COMMENT_PR_NUMBER = 42
NO_NEW_COMMENT_WATERMARK = 2500
FULL_PROMPT_REPLY_ISSUE_NUMBER = 406
FULL_PROMPT_REPLY_PR_NUMBER = 46
FULL_PROMPT_REPLY_COMMENT_ID = 6100
FULL_PROMPT_REPLY_WATERMARK = 6000
NO_CHANGE_REPLY_ISSUE_NUMBER = 407
NO_CHANGE_REPLY_PR_NUMBER = 47
NO_CHANGE_REPLY_COMMENT_ID = 7100
NO_CHANGE_REPLY_WATERMARK = 7000
CONTINUE_COMMENT_ID = 9000
CONTINUE_PR_NUMBER = 47
CONTINUE_WATERMARK = 8000
CONTINUE_ISSUE_NUMBER = 730
QUESTION_CONTINUE_ISSUE_NUMBER = 731
INTERRUPTED_ISSUE_NUMBER = 202
INTERRUPTED_PR_NUMBER = 21
INTERRUPTED_RESUME_ISSUE_NUMBER = 203
INTERRUPTED_RESUME_PR_NUMBER = 23
INTERRUPTED_RESUME_COMMENT_ID = 2100
INTERRUPTED_RESUME_WATERMARK = 2000
PARKED_FIXTURE_WATERMARK = 6000
GIT_FAILURE_EXIT_CODE = 128
PENDING_UNWIND_COMMENT_ID = 999
EXTERNAL_MERGE_ISSUE_NUMBER = 180
EXTERNAL_MERGE_PR_NUMBER = 18000
CLOSED_ISSUE_NUMBER = 181
CLOSED_PR_NUMBER = 18100
FINAL_DOCS_PR_WATERMARK = 999
FINAL_DOCS_REPLY_ID = 2000
WATERMARK_ISSUE_NUMBER = 709
WATERMARK_PR_NUMBER = 73
PICKUP_COMMENT_ID = 900
PARK_COMMENT_ID = 950
HUMAN_REPLY_ID = 1100


class HandleDocumentingRecoveryTest(unittest.TestCase, _BasicDocumentingFixture):
    """Restart recovery: a previous tick committed docs but crashed
    before the push lands."""

    issue_number = 301
    pr_number = 31

    def test_recovered_commits_push_without_spawn(self) -> None:
        # A commit an earlier tick made is still one this orchestrator
        # publishes, so it goes out under its pull request's reference -- and
        # under that reference alone, whether the subject it was committed
        # under named nothing, named the tracked issue the way recent history
        # spells it, or carried that number beside one an earlier publication
        # had already appended.
        published = f"docs: recovered notes (#{self.pr_number})\n"
        for committed in self._recovered_messages():
            with self.subTest(committed=committed):
                gh, mocks = self._recovered_tick(committed)

                # The agent must NOT be spawned -- the recovered commits are
                # enough to advance.
                mocks[RUN_AGENT].assert_not_called()
                self.assertIn((self.issue_number, IN_REVIEW), gh.label_history)
                state = gh.pinned_data(self.issue_number)
                self.assertEqual(state.get(DOCS_VERDICT), VERDICT_UPDATED)
                _assert_referenced_publication(
                    self,
                    mocks,
                    state,
                    (documenting_support.SHA_UNREFERENCED, published),
                    SHA_RECOVERED,
                )
                self.assertIn("recovered docs commit", _pr_comment_text(gh))

    def test_referenced_commit_pushed_unamended(self) -> None:
        # A commit an earlier tick amended and then never pushed -- the tick
        # died, or its push failed -- already ends in this pull request's
        # reference. The retry publishes that very commit: nothing is amended,
        # the head is not read again, and the subject never carries the
        # number twice.
        gh, issue = self._seeded()
        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(),
            push_branch=True,
            head_shas=[SHA_RECOVERED, documenting_support.SHA_UNREFERENCED],
            commit_message=f"docs: recovered notes (#{self.pr_number})\n",
            branch_ahead_behind=(1, 0),
        )

        mocks[documenting_support.AMEND_COMMIT_MESSAGE].assert_not_called()
        self.assertEqual(mocks[documenting_support.HEAD_SHA].call_count, 1)
        self.assertEqual(
            mocks[PUSH_BRANCH].call_args.kwargs[documenting_support.REVISION],
            SHA_RECOVERED,
        )
        self.assertIn((self.issue_number, IN_REVIEW), gh.label_history)
        self.assertEqual(
            gh.pinned_data(self.issue_number).get(DOCS_CHECKED_SHA), SHA_RECOVERED,
        )

    def test_a_head_moved_after_the_probe_refuses(self) -> None:
        # The ahead/behind probe fetched the branch, proved a recovered docs
        # commit waiting on top of the remote tip, and handed that tip on: it
        # is what this push replaces. Somebody landed on the pull request
        # between the probe and the push -- read afresh at the gate, their head
        # becomes the lease and the force-push overwrites it with a commit
        # proved against the head it used to be on.
        gh, issue = self._seeded()
        gh.get_pr(self.pr_number).head.sha = MOVED_PUBLICATION

        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(),
            push_branch=True,
            head_shas=[SHA_RECOVERED],
            branch_ahead_behind=(1, 0),
        )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)
        state = gh.pinned_data(self.issue_number)
        self.assertTrue(state.get(AWAITING_HUMAN))

    def test_recovery_push_failure_parks_push_failed(self) -> None:
        gh, issue = self._seeded()
        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(),
            push_branch=False,
            # The recovery branch falls through to the unified
            # commit/dirty/push block, which reads `after_sha`.
            head_shas=[SHA_RECOVERED],
            branch_ahead_behind=(1, 0),
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)
        self.assertNotIn((self.issue_number, VALIDATING), gh.label_history)
        state = gh.pinned_data(self.issue_number)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PARK_PUSH_FAILED)

    def test_dirty_recovery_parks_without_push(self) -> None:
        # A previous tick committed docs AND left some files
        # uncommitted, then crashed. The recovery branch must NOT push:
        # the push would publish an incomplete branch (the dirty files
        # would silently disappear from what the reviewer agent sees).
        gh, issue = self._seeded()
        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(),
            push_branch=True,
            dirty_files=["docs/dirty.md"],
            head_shas=[SHA_RECOVERED],
            branch_ahead_behind=(1, 0),
        )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)
        self.assertNotIn((self.issue_number, VALIDATING), gh.label_history)
        state = gh.pinned_data(self.issue_number)
        self.assertTrue(state.get(AWAITING_HUMAN))
        last_comment = gh.posted_comments[-1][1]
        self.assertIn(UNCOMMITTED_CHANGE, last_comment)
        self.assertIn("docs/dirty.md", last_comment)

    def _recovered_messages(self) -> tuple[str, ...]:
        """The messages a stranded docs commit reaches this tick carrying."""
        issue_reference = f" (#{self.issue_number})"
        pr_reference = f" (#{self.pr_number})"
        return (
            "docs: recovered notes\n",
            f"docs: recovered notes{issue_reference}\n",
            f"docs: recovered notes{issue_reference}{pr_reference}\n",
        )

    def _recovered_tick(self, commit_message: str):
        """One tick over a docs commit an earlier tick left on the branch."""
        gh, issue = self._seeded()
        return gh, self._run_documenting(
            gh,
            issue,
            run_agent=_agent(),
            push_branch=True,
            # The recovered commit is read once, and HEAD once more to prove
            # it stands on the replacement the amendment handed back.
            head_shas=[documenting_support.SHA_UNREFERENCED, SHA_RECOVERED],
            commit_message=commit_message,
            branch_ahead_behind=(1, 0),
        )
