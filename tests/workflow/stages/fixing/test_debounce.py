# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing debounce behavior."""

from __future__ import annotations

import unittest

from orchestrator.workflow.stages.fixing import feedback as _feedback, models as _models
from tests.workflow.stages.fixing import fixing_test_support as support
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
)

IssueScenario = support.IssueScenario

ALICE = support.ALICE
AGENT_RUN_CHARGE_WRITES = support.AGENT_RUN_CHARGE_WRITES
AWAITING_HUMAN = support.AWAITING_HUMAN
CONTINUE_WORD = support.CONTINUE_WORD
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_AGENT = support.DEV_AGENT
DEV_SESSION = support.DEV_SESSION
EARLIER_PENDING_FIX_AT_TS = support.EARLIER_PENDING_FIX_AT_TS
EVENT_AGENT_SPAWN = support.EVENT_AGENT_SPAWN
FIXING = support.FIXING
FOLLOWUP_ID = support.FOLLOWUP_ID
STAGE_FIXING = support.STAGE_FIXING
FakeComment = support.FakeComment
FakePRReview = support.FakePRReview
FakeUser = support.FakeUser
INITIAL_PR_COMMENT_WATERMARK = support.INITIAL_PR_COMMENT_WATERMARK
IN_REVIEW = support.IN_REVIEW
ISSUE = support.ISSUE
PARK_REASON = support.PARK_REASON
PENDING_FIX_AT = support.PENDING_FIX_AT
PENDING_FIX_AT_TS = support.PENDING_FIX_AT_TS
PENDING_FIX_ISSUE_MAX_ID = support.PENDING_FIX_ISSUE_MAX_ID
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PUSHED_FIX_MESSAGE = support.PUSHED_FIX_MESSAGE
PUSH_BRANCH = support.PUSH_BRANCH
RESUME_SESSION_ID = support.RESUME_SESSION_ID
REVIEW_SUMMARY_FEEDBACK_ID = support.REVIEW_SUMMARY_FEEDBACK_ID
ROLE_DEVELOPER = support.ROLE_DEVELOPER
RUN_AGENT = support.RUN_AGENT
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
SHA_SAME = support.SHA_SAME
TRIGGER_ID = support.TRIGGER_ID
_FixingFixtureMixin = support._FixingFixtureMixin
_agent = support._agent
config = support.config
datetime = support.datetime
now_utc = support.now_utc
patch = support.patch
posted_comment_contains = support.posted_comment_contains
timedelta = support.timedelta
timezone = support.timezone


FEEDBACK_BODY = "rename foo to bar"
_INTERRUPTED_SIGTERM_EXIT = -15
_INTERRUPTED_FIX_RUNS = (
    _agent(
        session_id=DEV_SESSION,
        interrupted=True,
        last_message="partial fix before the shutdown SIGTERM",
    ),
    _agent(
        session_id=DEV_SESSION,
        interrupted=True,
        exit_code=_INTERRUPTED_SIGTERM_EXIT,
        unfinished_steps=("run_command",),
        last_message="partial fix before the shutdown SIGTERM",
    ),
)

# The window the helper-level cases below are measured against: each dates its
# items relative to this rather than carrying a duration of its own.
GATE_WINDOW_SECONDS = 900


def _comment(comment_id: int, created_at) -> FakeComment:
    return FakeComment(id=comment_id, body=FEEDBACK_BODY, created_at=created_at)


def _batch(issue_thread=(), review_summaries=()) -> _models._FixingFeedback:
    """A rescan result carrying only the surfaces a case needs."""
    return _models._FixingFeedback(
        issue_thread=list(issue_thread),
        pr_conversation=[],
        review_comments=[],
        review_summaries=list(review_summaries),
    )


def _window_cases() -> dict:
    """Batches the gate answers for, paired with the answer each one earns."""
    now = now_utc()
    settled = now - timedelta(seconds=GATE_WINDOW_SECONDS * 2)
    return {
        "nothing unread": (_batch(), False),
        "one settled comment": (_batch([_comment(TRIGGER_ID, settled)]), False),
        "one fresh comment": (_batch([_comment(TRIGGER_ID, now)]), True),
        # The freshest item decides, wherever the batch lists it.
        "a fresh comment behind a settled one": (
            _batch([_comment(TRIGGER_ID, now), _comment(FOLLOWUP_ID, settled)]),
            True,
        ),
        # A review summary stamps `submitted_at` where a comment stamps
        # `created_at`, so the newest-item read spans both spellings.
        "a fresh review summary": (
            _batch(
                [_comment(TRIGGER_ID, settled)],
                [FakePRReview(
                    id=REVIEW_SUMMARY_FEEDBACK_ID,
                    body=FEEDBACK_BODY,
                    submitted_at=now,
                )],
            ),
            True,
        ),
        # An item that cannot say when it landed cannot say the batch is still
        # settling, so it never holds the resume.
        "an undated comment": (_batch([_comment(TRIGGER_ID, None)]), False),
    }


class QuietWindowGateTest(unittest.TestCase):
    """The gate one tick asks before it spends a dev session on a batch."""

    def test_freshest_item_decides_the_window(self) -> None:
        with patch.object(config, DEBOUNCE_CONFIG, GATE_WINDOW_SECONDS):
            for case, (feedback, expected) in _window_cases().items():
                with self.subTest(case=case):
                    self.assertIs(
                        _feedback._fixing_debounce_open(feedback, None), expected,
                    )

    def test_replay_batch_skips_the_window(self) -> None:
        # An accepted `/orchestrator continue` is a deliberate operator signal
        # rather than chatter, so the preserved batch resumes the dev on the
        # same feedback the window would otherwise still be holding.
        feedback = _batch([_comment(TRIGGER_ID, now_utc())])
        with patch.object(config, DEBOUNCE_CONFIG, GATE_WINDOW_SECONDS):
            self.assertTrue(_feedback._fixing_debounce_open(feedback, None))
            self.assertFalse(
                _feedback._fixing_debounce_open(feedback, feedback.all_items),
            )


class FixingDebounceAndAckTest(unittest.TestCase, _FixingFixtureMixin):
    def test_debounce_window_does_not_resume(self) -> None:
        # Triggering comment is fresh (created `now`); IN_REVIEW_DEBOUNCE_SECONDS
        # has not elapsed, so the handler must NOT resume the dev. No agent
        # spawn, no label change, watermarks untouched.
        now = datetime.now(timezone.utc)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please tighten the docstring",
            user=FakeUser(ALICE),
            created_at=now,
        )
        pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(),
            )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(scenario.github.label_history, [])
        # Watermark not advanced past the triggering comment yet.
        self.assertEqual(
            scenario.github.pinned_data(ISSUE).get(PR_LAST_COMMENT_ID),
            INITIAL_PR_COMMENT_WATERMARK,
        )
        self.assertFalse(scenario.github.pinned_data(ISSUE).get(AWAITING_HUMAN))

    def test_fixing_past_debounce_resumes_dev(self) -> None:
        # Triggering comment is older than the debounce window; the handler
        # builds a `_build_pr_comment_followup` prompt and resumes the dev
        # via `_resume_dev_with_text`.
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="rename foo to bar",
            user=FakeUser(ALICE),
            created_at=old,
        )
        self._pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=self._pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_FIX_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        self._mocks[RUN_AGENT].assert_called_once()
        self._call_args = self._mocks[RUN_AGENT].call_args
        # `run_agent(backend, prompt, cwd, **kwargs)`.
        backend = self._call_args.args[0]
        self._prompt = self._call_args.args[1]
        # Followup prompt quotes the human's comment so the dev sees what
        # to fix.
        self.assertIn("rename foo to bar", self._prompt)
        self.assertIn("PR comments", self._prompt)
        # Dev session resumed (not a fresh spawn) on the locked backend.
        self.assertEqual(
            self._call_args.kwargs.get(RESUME_SESSION_ID),
            DEV_SESSION,
        )
        self.assertEqual(backend, DEV_AGENT)
        # A fixing-stage retry attributes the developer run to `fixing`: the
        # issue is genuinely labeled `fixing` on this fresh fetch, so the
        # label-derived stage (no explicit override needed here) is correct.
        dev_spawns = [
            event
            for event in scenario.github.recorded_events
            if event["event"] == EVENT_AGENT_SPAWN and event.get("agent_role") == ROLE_DEVELOPER
        ]
        self.assertEqual(len(dev_spawns), 1)
        self.assertEqual(dev_spawns[0]["stage"], STAGE_FIXING)

    # --- ACK fast path ----------------------------------------------------

    def test_no_commit_ack_returns_to_in_review(self) -> None:
        # in_review route: the dev makes no commit and ends with the
        # `ACK: <reason>` marker (the PR feedback carried no actionable
        # change). The handler returns to `in_review` (re-arming the
        # ready-ping) WITHOUT parking in `fixing`.
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body=CONTINUE_WORD,
            user=FakeUser(ALICE),
            created_at=old,
        )
        pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=(
                        "The branch already satisfies the comment.\n\nACK: nothing to fix; 'continue' names no defect"
                    ),
                ),
                head_shas=(SHA_SAME, SHA_SAME),  # no new commit
                # The branch this ack vouches for: the checkout standing
                # exactly where the remote pull-request branch is, which is
                # what the fast path proves before it hands the round back.
                fetched_branch_tip=SHA_SAME,
            )

        self.assertIn((ISSUE, IN_REVIEW), scenario.github.label_history)
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertFalse(self._pinned_data.get(AWAITING_HUMAN))
        self.assertIsNone(self._pinned_data.get(PENDING_FIX_AT))
        self._mocks[PUSH_BRANCH].assert_not_called()
        # An FYI quoting the ack reason is posted on the issue thread.
        self.assertTrue(
            posted_comment_contains(scenario.github, "no change"),
        )

    def test_no_commit_without_ack_still_parks(self) -> None:
        # A no-commit reply WITHOUT the marker is a genuine question and
        # must still park awaiting human until a fresh human reply arrives.
        # The reason stays cleared, which is what makes a bare
        # `/orchestrator continue` refuse rather than retry over words
        # nobody answered.
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please reconsider the approach",
            user=FakeUser(ALICE),
            created_at=old,
        )
        pr = self._open_pr()
        gh, issue = self._seed(pr=pr, issue_comments=[comment])

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                gh,
                issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message="Which trade-off do you prefer, A or B?",
                ),
                head_shas=(SHA_SAME, SHA_SAME),
            )

        self.assertNotIn((ISSUE, IN_REVIEW), gh.label_history)
        self.assertTrue(gh.pinned_data(ISSUE).get(AWAITING_HUMAN))
        self.assertIsNone(gh.pinned_data(ISSUE).get(PARK_REASON))

    def test_interrupted_no_commit_resume_is_ignored(self) -> None:
        # A shutdown-killed (interrupted) resume that produced no commit
        # must be ignored entirely: the handler bails WITHOUT persisting, so
        # the delivery settlement, bookmark clear, and awaiting_human
        # reset never reach GitHub. The next tick re-feeds the same comment
        # to a fresh dev session. Distinct from a no-commit no-ACK reply,
        # which parks awaiting_human via `_on_question`. Both clean
        # interruptions and signal kills with partial steps are ignored.
        for run_case in _INTERRUPTED_FIX_RUNS:
            with self.subTest(run=run_case):
                comment = FakeComment(
                    id=TRIGGER_ID,
                    body="please tighten the error handling",
                    user=FakeUser(ALICE),
                    created_at=datetime.now(timezone.utc) - timedelta(hours=1),
                )
                pr = self._open_pr()
                scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))

                with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
                    mocks = self._run_fixing(
                        scenario.github,
                        scenario.issue,
                        run_agent=run_case,
                        head_shas=(SHA_SAME, SHA_SAME),  # no new commit
                    )

                self.assertEqual(only_prompt(mocks), pr_feedback_prompt((comment,)))
                mocks[PUSH_BRANCH].assert_not_called()
                self.assertEqual(
                    scenario.github.write_state_calls, AGENT_RUN_CHARGE_WRITES,
                )
                self.assertEqual(scenario.github.label_history, [])
                self.assertEqual(scenario.github.posted_comments, [])
                self._pinned_data = scenario.github.pinned_data(ISSUE)
                self.assertEqual(
                    self._pinned_data.get(PR_LAST_COMMENT_ID),
                    INITIAL_PR_COMMENT_WATERMARK,
                )
                self.assertEqual(self._pinned_data.get(PENDING_FIX_AT), PENDING_FIX_AT_TS)
                self.assertEqual(self._pinned_data.get(PENDING_FIX_ISSUE_MAX_ID), TRIGGER_ID)
                self.assertFalse(self._pinned_data.get(AWAITING_HUMAN))

    def test_interrupted_with_new_commit_is_ignored(self) -> None:
        # An interrupted resume that DID advance HEAD must also be ignored:
        # `_handle_dev_fix_result` refuses to publish an interrupted run, so
        # if the handler did not bail here it would settle the batch as
        # delivered and write state while the local commit sits unpushed --
        # consuming the feedback and leaving the next tick with no feedback
        # and a PR head missing the fix. The guard must therefore fire for
        # the new-commit case too; the commit stays on disk for a later clean
        # run to republish via the stranded-fix tail.
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please tighten the error handling",
            user=FakeUser(ALICE),
            created_at=old,
        )
        pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    interrupted=True,
                    last_message="committed a partial fix before the SIGTERM",
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),  # HEAD advanced
            )

        self.assertEqual(only_prompt(mocks), pr_feedback_prompt((comment,)))
        # The interrupted commit is NOT pushed and nothing is consumed.
        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(
            scenario.github.write_state_calls, AGENT_RUN_CHARGE_WRITES,
        )
        self.assertEqual(scenario.github.label_history, [])
        self.assertEqual(scenario.github.posted_comments, [])
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertEqual(
            self._pinned_data.get(PR_LAST_COMMENT_ID),
            INITIAL_PR_COMMENT_WATERMARK,
        )
        self.assertEqual(self._pinned_data.get(PENDING_FIX_AT), PENDING_FIX_AT_TS)
        self.assertEqual(self._pinned_data.get(PENDING_FIX_ISSUE_MAX_ID), TRIGGER_ID)
        self.assertFalse(self._pinned_data.get(AWAITING_HUMAN))

    def test_no_ack_in_review_park_stays_parked(self) -> None:
        # Regression: a no-commit no-ACK reply parks via `_on_question`
        # (park_reason=None) on the first tick AND leaves the worktree
        # matching the PR head. The next tick must keep the issue parked
        # awaiting a human reply -- a real dev question is the same shape
        # as a "nothing to fix" remark by inspection, so auto-routing
        # back to `in_review` would silently bypass the HITL contract.
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body=CONTINUE_WORD,
            user=FakeUser(ALICE),
            created_at=old,
        )
        pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=pr,
                issue_comments=[comment],
                extra_state={
                    # The in_review handler sets this when it routes fresh PR
                    # feedback into `fixing`; it discriminates the in_review
                    # route from the validating `CHANGES_REQUESTED` route.
                    PENDING_FIX_AT: EARLIER_PENDING_FIX_AT_TS,
                    PENDING_FIX_ISSUE_MAX_ID: TRIGGER_ID,
                    # Already parked from a prior tick whose dev resume produced
                    # no commit and no ACK marker (the `_on_question` shape).
                    AWAITING_HUMAN: True,
                    PARK_REASON: None,
                    # Watermark already past the triggering comment so the
                    # rescan finds no new feedback.
                    PR_LAST_COMMENT_ID: TRIGGER_ID,
                },
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(),
            )

        self.assertNotIn((ISSUE, IN_REVIEW), scenario.github.label_history)
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertTrue(self._pinned_data.get(AWAITING_HUMAN))
        # Bookmarks left intact for the eventual human-reply re-entry.
        self.assertEqual(self._pinned_data.get(PENDING_FIX_AT), EARLIER_PENDING_FIX_AT_TS)
        # The handler short-circuits at the awaiting-human + no-new-feedback
        # gate -- no dev resume, no push.
        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
