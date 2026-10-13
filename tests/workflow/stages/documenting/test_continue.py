# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from contextlib import ExitStack
from unittest.mock import patch

from orchestrator import config
from tests.support import agy_stream as stream
from tests.workflow.agent_failure_values import AGY_TERMINAL_ERROR, agy_responded
from tests.workflow.fixtures import (
    MEASURED_CANDIDATE_SHA,
    _agent,
)
from tests.workflow.session_limit_parks import assert_session_limit_park
from tests.workflow.stages.documenting import (
    documenting_test_support as documenting_support,
)
from tests.workflow.stages.documenting.documenting_assertion_test_support import (
    _agent_prompt,
    _issue_comment_text,
)

# --- Workflow labels this stage routes between --------------------------
from tests.workflow.stages.documenting.documenting_scenario_test_support import (
    EARLIER_GUIDANCE,
    FRESH_SESSION,
    PINNED_IN_CHECKOUT,
    QUOTA_ISSUE_BODY,
    QUOTA_ISSUE_NUMBER,
    SHA_STOPPED,
    _AgyContinueDocumentingFixture,
    _ContinueDocumentingFixture,
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


class HandleDocumentingContinueCommandTest(unittest.TestCase, _ContinueDocumentingFixture):
    """`/orchestrator continue` on a parked `documenting` issue is an operator
    command, not requirements drift (issue #729, the #717 shape). A retryable
    session-failure park reruns the docs pass without the spurious "issue body
    changed; routing back to `validating`" notice; a park needing a real answer
    refuses."""

    def test_bare_continue_reruns_without_drift(self) -> None:
        # The #717 shape: parked `agent_silent` docs pass, human posts exactly
        # `/orchestrator continue`. The docs pass reruns (full documentation
        # prompt) with no "issue body changed" / "routing back to validating"
        # notice, and the issue is NOT rerouted to `validating`.
        gh, issue = self._seed(
            CONTINUE_ISSUE_NUMBER,
            park_reason=PARK_AGENT_SILENT,
        )

        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="docs: documented the flag",
            ),
            push_branch=True,
            head_shas=[SHA_BEFORE, SHA_AFTER],
            branch_ahead_behind=(0, 0),
        )

        # The docs pass reran on the full documentation prompt.
        mocks[RUN_AGENT].assert_called_once()
        prompt = _agent_prompt(mocks)
        self.assertIn("DOCS: NO_CHANGE", prompt)
        # No drift notice, and no reroute to validating.
        comment_text = _issue_comment_text(gh, CONTINUE_ISSUE_NUMBER)
        self.assertNotIn(USER_CONTENT_CHANGED, comment_text)
        self.assertNotIn("routing back to", comment_text)
        self.assertNotIn(
            (CONTINUE_ISSUE_NUMBER, VALIDATING),
            gh.label_history,
        )
        # The commit advanced the issue to in_review; command consumed.
        self.assertIn((CONTINUE_ISSUE_NUMBER, IN_REVIEW), gh.label_history)
        self.assertEqual(
            gh.pinned_data(CONTINUE_ISSUE_NUMBER).get(LAST_ACTION_COMMENT_ID),
            CONTINUE_COMMENT_ID,
        )

    def test_bare_continue_on_question_park_refuses(self) -> None:
        # A real docs-agent question parks with `park_reason=None`. A
        # content-free continue carries no answer, so refuse and stay parked
        # -- no docs rerun, no reroute.
        gh, issue = self._seed(QUESTION_CONTINUE_ISSUE_NUMBER, park_reason=None)

        mocks = self._run_documenting(
            gh,
            issue,
            run_agent=_agent(),
            branch_ahead_behind=(0, 0),
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertIn(
            "needs your actual guidance",
            _issue_comment_text(gh, QUESTION_CONTINUE_ISSUE_NUMBER),
        )
        self.assertNotIn(
            (QUESTION_CONTINUE_ISSUE_NUMBER, VALIDATING),
            gh.label_history,
        )
        self.assertNotIn(
            (QUESTION_CONTINUE_ISSUE_NUMBER, IN_REVIEW),
            gh.label_history,
        )
        self.assertTrue(gh.pinned_data(QUESTION_CONTINUE_ISSUE_NUMBER).get(AWAITING_HUMAN))


# The pinned fields a quota continuation is read back by.
AGENT_RUNS_USED = "agent_runs_used"
DEV_SESSION_ID = "dev_session_id"
PARK_RUN_LIMIT = "agent_run_limit"
# What the full documentation prompt carries beside the marker contract: the
# issue's requirements and the guidance its thread already held.
FULL_DOCS_CONTEXT = (QUOTA_ISSUE_BODY, EARLIER_GUIDANCE, "DOCS: NO_CHANGE")


# The pinned record an Antigravity docs launch lands ahead of the run.
LAUNCHED_DOCS_SHA = "docs_launched_sha"
# Passes a live pause stopped after each committed: one whose terminal
# succeeded, and one an error terminal no quota named failed.
PAUSED_SUCCESS = agy_responded("Documented --dry-run in the README.")
PAUSED_FAILURE = agy_responded("Documented --dry-run in the README.", error=AGY_TERMINAL_ERROR)

# The holds a pass that failed can return under: an operator's pause, alone and
# with every edit made once the agent spawned refused.
PAUSED_HOLDS = ("_paused_meanwhile", "_refused_under_pause")

# The holds a quota stop's tick can run under, each leaving no park behind it:
# an operator's pause the run returns to, and a retirement edit GitHub refuses.
HOLDS = ("_paused_meanwhile", "_retirement_refused")

# The launch the stopped pass resumed the pinned conversation with, and the
# fresh one its continue opens: both under the pinned command, in one checkout.
STOPPED_LAUNCH = (stream.SESSION_ID, *PINNED_IN_CHECKOUT)
FRESH_LAUNCH = (None, *PINNED_IN_CHECKOUT)


def _launches(run_agent) -> list:
    """The conversation, backend, worktree, and arguments each launch was made with, in order."""
    launches = []
    for launch in run_agent.call_args_list:
        backend, _, worktree = launch.args
        conversation = launch.kwargs.get("resume_session_id")
        launches.append((conversation, backend, worktree, launch.kwargs.get("extra_args")))
    return launches


class _ContinueAssertions(_AgyContinueDocumentingFixture):
    """What the ticks of one Antigravity docs issue are read back by."""

    def _assert_waits_for_continue(self, gh, run_agent, parked) -> None:
        """The tick after a held stop launched and published nothing, and parked for a continue."""
        self.assertEqual(run_agent.call_count, 1)
        parked[PUSH_BRANCH].assert_not_called()
        self.assertEqual(gh.label_history, [])
        state = self._pinned(gh)
        self.assertEqual(
            {key: state.get(key) for key in (DOCS_VERDICT, AWAITING_HUMAN, PARK_REASON)},
            {DOCS_VERDICT: None, AWAITING_HUMAN: True, PARK_REASON: PARK_AGENT_SILENT},
        )
        self.assertIn("/orchestrator continue", _issue_comment_text(gh, QUOTA_ISSUE_NUMBER))

    def _assert_documented(self, gh, run_agent, resumed, pinned=FRESH_SESSION) -> None:
        """The continued pass ran on the full docs prompt, published the stopped pass's commit, and advanced.

        `pinned` is the conversation the issue is left pinned to: the fresh one
        unless named.
        """
        for context in FULL_DOCS_CONTEXT:
            self.assertIn(context, run_agent.call_args.args[1])
        self.assertEqual(resumed[PUSH_BRANCH].call_args.kwargs[documenting_support.REVISION], SHA_DOCS)
        self.assertEqual(gh.label_history, [(QUOTA_ISSUE_NUMBER, IN_REVIEW)])
        self.assertEqual(
            self._ledger(gh), {DOCS_VERDICT: VERDICT_UPDATED, DEV_SESSION_ID: pinned, AGENT_RUNS_USED: 2},
        )

    def _ledger(self, gh) -> dict:
        """The verdict, pinned conversation, and lifetime run count on the issue's pinned comment."""
        state = self._pinned(gh)
        return {key: state.get(key) for key in (DOCS_VERDICT, DEV_SESSION_ID, AGENT_RUNS_USED)}

    def _pinned(self, gh) -> dict:
        """The issue's pinned comment as it reads now."""
        return gh.pinned_data(QUOTA_ISSUE_NUMBER)


class DocumentingQuotaContinueTest(unittest.TestCase, _ContinueAssertions):
    """A docs pass a quota stopped resumes only on a continue, in a fresh conversation over the same checkout."""

    def test_continue_documents_fresh(self) -> None:
        # The stopped pass committed, and nothing of it is published: it parks
        # as the session limit with its conversation retired, and a tick that
        # reads no reply launches nothing and writes nothing. The continue
        # after the reset reruns the full docs prompt in a fresh conversation,
        # in the same checkout under the pinned Antigravity command though the
        # configured one moved, charged to the same lifetime run ledger. Only
        # that pass, which succeeds, publishes the stopped pass's commit and
        # advances.
        gh, issue, run_agent = self._stopped()
        assert_session_limit_park(self, gh, QUOTA_ISSUE_NUMBER)
        self.assertEqual(gh.label_history, [])
        parked = self._pinned(gh)
        self.assertEqual(
            self._ledger(gh), {DOCS_VERDICT: None, DEV_SESSION_ID: None, AGENT_RUNS_USED: 1},
        )
        self.assertIsNone(parked.get(LAUNCHED_DOCS_SHA), "the park answers for the launch")

        self._tick(gh, issue, run_agent)
        self.assertEqual(self._pinned(gh), parked)

        self._continue(gh, issue)
        # The rerun commits nothing of its own, and the stopped pass's commit
        # goes out as the replacement its subject is amended into.
        with self._configured_elsewhere():
            resumed = self._tick(gh, issue, run_agent, head_shas=(SHA_STOPPED, SHA_STOPPED, SHA_DOCS))

        self.assertEqual(_launches(run_agent), [STOPPED_LAUNCH, FRESH_LAUNCH])
        self._assert_documented(gh, run_agent, resumed)

    def test_held_stop_waits_for_continue(self) -> None:
        # The quota stop's tick is held -- an operator paused the issue while
        # the pass ran, or GitHub refused the edit that would land the
        # retirement -- so it writes no park and leaves the commit ahead of
        # the pull request. The next tick does not publish that commit as
        # recovered work: the issue still owes a fresh conversation, so it
        # parks, launching nothing, for a continue. That continue reruns the
        # full docs prompt in a fresh conversation, and only its success
        # publishes the commit and advances.
        for hold in HOLDS:
            with self.subTest(hold=hold):
                gh, issue, run_agent = self._stopped(getattr(self, hold))
                self.assertEqual((gh.label_history, gh.posted_comments), ([], []))

                self._assert_waits_for_continue(gh, run_agent, self._tick(gh, issue, run_agent))

                self._continue(gh, issue)
                resumed = self._tick(gh, issue, run_agent, head_shas=(SHA_STOPPED, SHA_STOPPED, SHA_DOCS))
                self.assertEqual(_launches(run_agent), [STOPPED_LAUNCH, FRESH_LAUNCH])
                self._assert_documented(gh, run_agent, resumed)

    def test_held_stop_without_commit_waits(self) -> None:
        # GitHub refused the edit that would land the quota's retirement, and
        # the stopped pass committed nothing, so the branch stays level with
        # its pull request. The next tick still launches nothing: the record
        # the launch landed stands, so it parks for a continue, which reruns
        # the pass in a fresh conversation once the retirement lands ahead of
        # its plan.
        gh, issue, run_agent = self._stopped(self._retirement_refused, head_shas=(SHA_BEFORE,))

        waited = self._tick(gh, issue, run_agent, head_shas=(SHA_BEFORE,), ahead=0)
        self._assert_waits_for_continue(gh, run_agent, waited)

        self._continue(gh, issue)
        self._tick(gh, issue, run_agent, head_shas=(SHA_BEFORE,), ahead=0)
        self.assertEqual(_launches(run_agent), [STOPPED_LAUNCH, FRESH_LAUNCH])
        self.assertEqual(gh.label_history, [(QUOTA_ISSUE_NUMBER, IN_REVIEW)])
        self.assertEqual(
            self._ledger(gh), {DOCS_VERDICT: VERDICT_NO_CHANGE, DEV_SESSION_ID: FRESH_SESSION, AGENT_RUNS_USED: 2},
        )

    def test_unrecorded_launch_is_not_made(self) -> None:
        # GitHub refuses every edit, the record a launch lands ahead of the
        # run among them, so the tick launches nothing and leaves nothing to
        # read. The next tick, which GitHub answers, makes that launch.
        gh, issue, run_agent = self._stopped(self._edits_refused)
        self.assertEqual(run_agent.call_count, 0)
        self.assertEqual(gh.posted_comments, [])
        self.assertIsNone(self._pinned(gh).get(LAUNCHED_DOCS_SHA))

        self._tick(gh, issue, run_agent, head_shas=(SHA_BEFORE, SHA_STOPPED, SHA_DOCS), ahead=0)
        self.assertEqual(_launches(run_agent), [STOPPED_LAUNCH])
        assert_session_limit_park(self, gh, QUOTA_ISSUE_NUMBER)

    def test_spent_budget_refuses_continue(self) -> None:
        # The retirement buys a fresh conversation, not a fresh allowance: with
        # the issue's lifetime runs spent by the stopped pass, the continue
        # launches nothing, publishes nothing, and parks on the run limit.
        gh, issue, run_agent = self._stopped()
        self._continue(gh, issue)

        with patch.object(config, "MAX_AGENT_RUNS_PER_ISSUE", 1):
            refused = self._tick(gh, issue, run_agent)

        self.assertEqual(run_agent.call_count, 1)
        refused[PUSH_BRANCH].assert_not_called()
        self.assertEqual(gh.label_history, [])
        state = self._pinned(gh)
        self.assertEqual(
            {key: state.get(key) for key in (AWAITING_HUMAN, PARK_REASON, AGENT_RUNS_USED)},
            {AWAITING_HUMAN: True, PARK_REASON: PARK_RUN_LIMIT, AGENT_RUNS_USED: 1},
        )

    def _edits_refused(self, gh):
        """GitHub refusing every pinned-comment edit on the issue, from the start of the tick."""
        return patch.object(gh.pinned_failures, "refused", {QUOTA_ISSUE_NUMBER})


class DocumentingPausedPassTest(unittest.TestCase, _ContinueAssertions):
    """What the tick after a live pause makes of the pass the pause stopped."""

    def test_paused_success_publishes_next_tick(self) -> None:
        # An operator paused the issue while a pass ran, committed, and
        # succeeded, so its tick wrote nothing of it: the next tick publishes
        # the commit as recovered work, with no agent run, and advances.
        gh, issue, run_agent = self._stopped(self._paused_meanwhile, stop=PAUSED_SUCCESS)
        self.assertIsNone(self._pinned(gh).get(LAUNCHED_DOCS_SHA))

        published = self._tick(gh, issue, run_agent)

        self.assertEqual(run_agent.call_count, 1)
        self.assertEqual(published[PUSH_BRANCH].call_args.kwargs[documenting_support.REVISION], SHA_DOCS)
        self.assertEqual(gh.label_history, [(QUOTA_ISSUE_NUMBER, IN_REVIEW)])

    def test_paused_failure_waits_for_continue(self) -> None:
        # The same pause over a pass an error terminal no quota named failed
        # after it committed -- with GitHub taking edits, and refusing every
        # one made once the agent spawned. Either way its tick posts nothing,
        # parks nothing, and needs no write: the record its launch landed
        # ahead of the run stands. The next tick parks instead of publishing,
        # launching nothing, and drops that record in the park's own write.
        # The continue resumes the conversation no quota retired, and only its
        # success publishes the commit and advances.
        for hold in PAUSED_HOLDS:
            with self.subTest(hold=hold):
                gh, issue, run_agent = self._stopped(getattr(self, hold), stop=PAUSED_FAILURE)
                self.assertEqual(gh.posted_comments, [])
                self.assertEqual(self._pinned(gh).get(LAUNCHED_DOCS_SHA), SHA_BEFORE)

                self._assert_waits_for_continue(gh, run_agent, self._tick(gh, issue, run_agent))
                self.assertIsNone(self._pinned(gh).get(LAUNCHED_DOCS_SHA))

                self._continue(gh, issue)
                resumed = self._tick(gh, issue, run_agent, head_shas=(SHA_STOPPED, SHA_STOPPED, SHA_DOCS))
                self.assertEqual(_launches(run_agent), [STOPPED_LAUNCH, STOPPED_LAUNCH])
                self._assert_documented(gh, run_agent, resumed, pinned=stream.SESSION_ID)

    def _refused_under_pause(self, gh) -> ExitStack:
        """An operator's pause the run returns to, with every edit made once the agent spawned refused."""
        hold = ExitStack()
        hold.enter_context(self._paused_meanwhile(gh))
        hold.enter_context(self._retirement_refused(gh))
        return hold
