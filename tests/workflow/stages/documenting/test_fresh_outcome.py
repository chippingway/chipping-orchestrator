# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.publication.commits import _Amendment
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
    _lifecycle_events,
    _pr_comment_text,
)
from tests.workflow.stages.documenting.documenting_test_support import (
    _FreshDocumentingFixture,
)

DOCUMENTING = "workflow:documenting"
IN_REVIEW = "in_review"
LATE_APPROVED_SHA = "late_approved_sha"

# --- The reference a published docs commit's subject is amended to end in --
AMEND_COMMIT_MESSAGE = documenting_support.AMEND_COMMIT_MESSAGE
COMMIT_MESSAGE = documenting_support.COMMIT_MESSAGE
COUNT_ADDED_LINES = documenting_support.COUNT_ADDED_LINES
HEAD_SHA = documenting_support.HEAD_SHA
PARK_SUBJECT_AMEND_FAILED = documenting_support.PARK_SUBJECT_AMEND_FAILED
PR_REF_IN_SUBJECT = documenting_support.PR_REF_IN_SUBJECT
REVISION = documenting_support.REVISION
SETTLED_DOCS_SHA = documenting_support.SETTLED_DOCS_SHA
SHA_UNREFERENCED = documenting_support.SHA_UNREFERENCED
SQUASH_ON_APPROVAL = documenting_support.SQUASH_ON_APPROVAL
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


class HandleDocumentingFreshOutcomeTest(
    unittest.TestCase,
    _FreshDocumentingFixture,
):
    """A docs agent run on a PR that already has commits."""

    def test_docs_commit_pushed_advances_to_in_review(self) -> None:
        gh, issue = self._seeded()
        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="docs: updated README",
            ),
            push_branch=True,
            # before_sha + after_sha
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=(0, 0),
        )

        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        # The agent is spawned with the dev session id locked in.
        _, call_kwargs = mocks[RUN_AGENT].call_args
        self.assertEqual(call_kwargs.get("resume_session_id"), DEV_SESSION)
        mocks[PUSH_BRANCH].assert_called_once()
        self.assertIn((self.issue_number, IN_REVIEW), gh.label_history)
        # The size gate approves the docs commit before it goes out and
        # records it as one still owed a push; the push that lands pays that
        # debt. Left standing it would freeze this branch out of the pre-tick
        # base refresh with nothing coming back to drop it.
        self.assertIsNone(
            gh.pinned_data(self.issue_number).get(LATE_APPROVED_SHA),
        )

    def test_lifecycle_events_carry_review_round(self) -> None:
        # Documenting runs once per reviewer-approval handoff between
        # approval and `in_review`. The pinned `review_round` at the time
        # of approval (0 on the first approval, higher after fix loops)
        # must ride along on the spawn / exit audit events (and the
        # analytics record), so a downstream consumer can tell which
        # reviewer round the docs pass belonged to.
        gh, issue = self._seeded(review_round=2)
        self._run_documenting(
            gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="docs: updated README",
            ),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=(0, 0),
        )
        lifecycle = _lifecycle_events(gh, "documenting")
        self.assertEqual(len(lifecycle), 2)
        for event in lifecycle:
            self.assertEqual(event.get(REVIEW_ROUND), 2)

        state = gh.pinned_data(self.issue_number)
        self.assertEqual(state.get(DOCS_VERDICT), VERDICT_UPDATED)
        self.assertEqual(state.get(DOCS_CHECKED_SHA), SHA_AFTER)
        # A PR-conversation announcement is posted so reviewers see the
        # docs commit in context.
        self.assertIn(":books: documenting pass", _pr_comment_text(gh))

    def test_no_change_marker_advances_without_push(self) -> None:
        gh, issue = self._seeded()
        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message=("Inspected diff; no user-facing change.\nDOCS: NO_CHANGE"),
            ),
            push_branch=True,
            # before + after both same -> no commit.
            head_shas=[SHA_BEFORE, SHA_BEFORE],
            branch_ahead_behind=(0, 0),
        )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertIn((self.issue_number, IN_REVIEW), gh.label_history)
        state = gh.pinned_data(self.issue_number)
        self.assertEqual(state.get(DOCS_VERDICT), VERDICT_NO_CHANGE)
        self.assertIn("no docs changes required", _pr_comment_text(gh))

    def test_no_commit_or_marker_parks_as_question(self) -> None:
        gh, issue = self._seeded()
        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="should I touch docs/architecture.md too?",
            ),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_BEFORE],
            branch_ahead_behind=(0, 0),
        )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)
        self.assertNotIn((self.issue_number, VALIDATING), gh.label_history)
        state = gh.pinned_data(self.issue_number)
        self.assertTrue(state.get(AWAITING_HUMAN))
        # The verdict is NOT recorded -- the agent did not give one.
        self.assertNotIn(DOCS_VERDICT, state)
        last_comment = gh.posted_comments[-1][1]
        self.assertIn("agent needs your input", last_comment)
        self.assertIn(DOCS_ARCHITECTURE, last_comment)

    def test_silent_run_parks_as_agent_silent(self) -> None:
        # No commits, no message -- treat as a poisoned-session silent
        # crash like the implementing/validating handlers do.
        gh, issue = self._seeded()
        self._run_documenting(
            gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="",
                exit_code=2,
            ),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_BEFORE],
            branch_ahead_behind=(0, 0),
        )

        state = gh.pinned_data(self.issue_number)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PARK_AGENT_SILENT)
        self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)
        self.assertNotIn((self.issue_number, VALIDATING), gh.label_history)

    def test_timeout_parks_with_agent_timeout(self) -> None:
        gh, issue = self._seeded()
        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(session_id=DEV_SESSION, timed_out=True),
            push_branch=True,
            head_shas=[SHA_BEFORE],
            branch_ahead_behind=(0, 0),
        )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)
        self.assertNotIn((self.issue_number, VALIDATING), gh.label_history)
        state = gh.pinned_data(self.issue_number)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PARK_AGENT_TIMEOUT)
        self.assertIn("agent timed out", gh.posted_comments[-1][1])



# A head somewhere other than the replacement HEAD was just moved onto:
# something landed on the checkout after the swap.
SHA_ELSEWHERE = "5ca1ab1e" * 5

# Each way the reference could fail to reach a committed subject: a message
# that did not read, a replacement git would not create, a checkout that moved
# off the docs commit before HEAD could be swapped onto its replacement -- the
# race the replacement is bound against -- and a HEAD that, read back after the
# swap, is not standing on the replacement or could not be read at all.
UNREFERENCED_FAILURES = (
    {"commit_message": None},
    {"amended_commit": _Amendment(error="fatal: could not write the object")},
    {"amended_commit": _Amendment(moved=True, error="cannot lock ref 'HEAD'")},
    {"head_shas": [SHA_BEFORE, SHA_UNREFERENCED, SHA_ELSEWHERE]},
    {"head_shas": [SHA_BEFORE, SHA_UNREFERENCED, ""]},
)

# The reference a fresh pass's pull request is named by in a subject.
PR_REFERENCE = f" (#{_FreshDocumentingFixture.pr_number})"

# The reference the issue this pass documents would be named by. The pull
# request's own body links that issue, so a published subject carrying it
# names one thing twice.
ISSUE_REFERENCE = f" (#{_FreshDocumentingFixture.issue_number})"

# Subjects a pass committed carrying the tracked issue's number -- copied out
# of recent history by the agent, or left beside this request's own reference
# where a developer commit and an earlier publication each wrote half -- and
# the one line they are all published under.
ISSUE_BEARING_MESSAGES = (
    f"docs: explain flag X{ISSUE_REFERENCE}\n",
    f"docs: explain flag X{ISSUE_REFERENCE}{PR_REFERENCE}\n",
    f"docs: explain flag X{PR_REFERENCE}{ISSUE_REFERENCE}\n",
)
PUBLISHED_MESSAGE = f"docs: explain flag X{PR_REFERENCE}\n"

# Messages a pass committed, and what the replacement is handed for each: the
# subject's own text rewritten and every other character left as written, or
# None where the subject already carries the reference and nothing is amended.
SUBJECT_REWRITES = (
    (
        "docs: explain flag X\r\n\r\nWhy it exists.\r\n",
        f"docs: explain flag X{PR_REFERENCE}\r\n\r\nWhy it exists.\r\n",
    ),
    (
        "docs: explain flag X\n\nWhy\rit exists.\n",
        f"docs: explain flag X{PR_REFERENCE}\n\nWhy\rit exists.\n",
    ),
    (f"docs: explain flag X{PR_REFERENCE}\r\n\r\nWhy it exists.\r\n", None),
)


class PullRequestReferenceTest(unittest.TestCase, _FreshDocumentingFixture):
    """The subject a fresh docs commit is published under."""

    def test_published_under_the_pr_reference(self) -> None:
        # The docs commit lands on the base exactly as it is published, so it
        # is replaced by one whose subject names the pull request before
        # anything names the commit. The replacement is bound to the commit
        # this pass read rather than to HEAD, and what is pushed and stamped is
        # the replacement, never the commit the agent made. The body goes back
        # as written, and the switch that keeps a developer's own history
        # intact does not reach it -- this commit is the orchestrator's to
        # publish.
        for squash_on_approval in (True, False):
            with (
                self.subTest(squash_on_approval=squash_on_approval),
                patch.object(config, SQUASH_ON_APPROVAL, squash_on_approval),
            ):
                gh, mocks = self._committed_pass(
                    commit_message="docs: explain flag X\n\nWhy it exists.\n",
                )

                _assert_referenced_publication(
                    self,
                    mocks,
                    self._pinned(gh),
                    (
                        SHA_UNREFERENCED,
                        f"docs: explain flag X (#{self.pr_number})\n\nWhy it exists.\n",
                    ),
                    SHA_AFTER,
                )

    def test_switched_off_publishes_as_made(self) -> None:
        # `PR_REF_IN_SUBJECT=off` publishes the commit the agent made: no
        # message is read, nothing is amended, and the head is read only the
        # two times a pass takes to tell whether it committed.
        with patch.object(config, PR_REF_IN_SUBJECT, False):
            gh, mocks = self._committed_pass(head_shas=[SHA_BEFORE, SHA_AFTER])

        mocks[COMMIT_MESSAGE].assert_not_called()
        mocks[AMEND_COMMIT_MESSAGE].assert_not_called()
        self.assertEqual(mocks[HEAD_SHA].call_count, 2)
        self.assertEqual(mocks[PUSH_BRANCH].call_args.kwargs[REVISION], SHA_AFTER)
        self.assertIn((self.issue_number, IN_REVIEW), gh.label_history)

    def test_unreferenced_subject_never_published(self) -> None:
        # Where the reference could not be put on the subject, the issue parks
        # before the size gate is entered: nothing is measured or pushed --
        # neither the docs commit nor anything a moved checkout now stands on.
        for failure in UNREFERENCED_FAILURES:
            with self.subTest(**failure):
                gh, mocks = self._committed_pass(**failure)

                mocks[COUNT_ADDED_LINES].assert_not_called()
                mocks[PUSH_BRANCH].assert_not_called()
                self.assertNotIn((self.issue_number, IN_REVIEW), gh.label_history)
                state = self._pinned(gh)
                self.assertTrue(state.get(AWAITING_HUMAN))
                self.assertEqual(state.get(PARK_REASON), PARK_SUBJECT_AMEND_FAILED)
                self.assertIsNone(state.get(SETTLED_DOCS_SHA))

    def test_only_the_subject_text_changes(self) -> None:
        # Everything but the subject's own text goes back as it was written:
        # a CR LF ending on the subject line and in the body, and a carriage
        # return inside it, are kept rather than normalized -- and a subject
        # already carrying the reference is not amended again, whatever line
        # ending follows it.
        for message, amended in SUBJECT_REWRITES:
            with self.subTest(message=message):
                _gh, mocks = self._committed_pass(commit_message=message)

                if amended is None:
                    mocks[AMEND_COMMIT_MESSAGE].assert_not_called()
                    continue
                self.assertEqual(
                    mocks[AMEND_COMMIT_MESSAGE].call_args.args[2], amended,
                )

    def test_the_tracked_issue_is_not_published(self) -> None:
        # The issue number is the same link spelled from the wrong side: the
        # pull request's body already names the issue. So a docs subject
        # carrying it is amended down to this request's reference alone,
        # wherever in the trailing run it sits -- and the amendment is the one
        # a subject that already reads that way does not get.
        for message in ISSUE_BEARING_MESSAGES:
            with self.subTest(message=message):
                _gh, mocks = self._committed_pass(commit_message=message)

                self.assertEqual(
                    mocks[AMEND_COMMIT_MESSAGE].call_args.args[2],
                    PUBLISHED_MESSAGE,
                )

    def _pinned(self, gh) -> dict:
        """What the pinned comment says once the pass has finished."""
        return gh.pinned_data(self.issue_number)

    def _committed_pass(self, **run_options):
        """A docs agent that ran on a branch in sync and committed.

        Its head is read before the run, after it, and once more after the
        amendment, where it stands on the replacement.
        """
        run_options.setdefault(
            "head_shas", [SHA_BEFORE, SHA_UNREFERENCED, SHA_AFTER],
        )
        gh, issue = self._seeded()
        return gh, self._run_documenting(
            gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="docs: updated README",
            ),
            push_branch=True,
            branch_ahead_behind=(0, 0),
            **run_options,
        )
