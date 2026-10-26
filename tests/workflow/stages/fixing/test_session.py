# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing session behavior."""

from __future__ import annotations

import unittest

from tests.workflow.stages.fixing import fixing_test_support as support

IssueScenario = support.IssueScenario

ALICE = support.ALICE
AWAITING_HUMAN = support.AWAITING_HUMAN
COMMAND_COMMENT_ID = support.COMMAND_COMMENT_ID
CONTINUE_COMMAND = support.CONTINUE_COMMAND
DAVE = support.DAVE
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
DOCUMENTING = support.DOCUMENTING
EARLIER_PENDING_FIX_AT_TS = support.EARLIER_PENDING_FIX_AT_TS
FRESH_SESSION = support.FRESH_SESSION
FakeComment = support.FakeComment
FakeUser = support.FakeUser
ISSUE = support.ISSUE
PARK_AGENT_SILENT = support.PARK_AGENT_SILENT
PARK_REASON = support.PARK_REASON
PENDING_FIX_AT = support.PENDING_FIX_AT
PENDING_FIX_ISSUE_MAX_ID = support.PENDING_FIX_ISSUE_MAX_ID
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PROVIDER_OVERLOAD_MESSAGE = support.PROVIDER_OVERLOAD_MESSAGE
PROVIDER_UNAVAILABLE_PHRASE = support.PROVIDER_UNAVAILABLE_PHRASE
PUSHED_FIX_MESSAGE = support.PUSHED_FIX_MESSAGE
PUSHED_MESSAGE = support.PUSHED_MESSAGE
RESUME_SESSION_ID = support.RESUME_SESSION_ID
RUN_AGENT = support.RUN_AGENT
SESSION_LIMIT_MESSAGE = support.SESSION_LIMIT_MESSAGE
SESSION_LIMIT_PHRASE = support.SESSION_LIMIT_PHRASE
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
TRIGGER_ID = support.TRIGGER_ID
VALIDATING = support.VALIDATING
_StrandedFixingFixtureMixin = support._StrandedFixingFixtureMixin
_agent = support._agent
config = support.config
datetime = support.datetime
dev_task_section = support.dev_task_section
patch = support.patch
posted_comment_contains = support.posted_comment_contains
timedelta = support.timedelta
timezone = support.timezone


# Each final message a CLI hands back that is NOT the dev's own words, with
# the exit code it arrives on and the phrase its park comment is recognized by.
# A quota notice exits cleanly (the session is healthy, the account is out);
# a provider refusal exits dirty.
_NOT_THE_DEVS_WORDS = (
    (SESSION_LIMIT_MESSAGE, 0, SESSION_LIMIT_PHRASE),
    (PROVIDER_OVERLOAD_MESSAGE, 1, PROVIDER_UNAVAILABLE_PHRASE),
)


def _assert_retryable_limit_park(
    test_case,
    scenario,
    pinned_state,
    hitl_comment_text,
    park_phrase,
) -> None:
    test_case.assertTrue(pinned_state.get(AWAITING_HUMAN))
    test_case.assertEqual(
        pinned_state.get(PARK_REASON),
        PARK_AGENT_SILENT,
    )
    test_case.assertNotIn(
        (ISSUE, VALIDATING),
        scenario.github.label_history,
    )
    test_case.assertIn(park_phrase, hitl_comment_text)
    test_case.assertIn(CONTINUE_COMMAND, hitl_comment_text)
    test_case.assertNotIn(
        "needs your input to proceed",
        hitl_comment_text,
    )
    # The bookmarks the replay rebuilds the batch from survive the park: only
    # a pushed fix retires them.
    test_case.assertIsNotNone(pinned_state.get(PENDING_FIX_AT))
    test_case.assertEqual(
        pinned_state.get(PENDING_FIX_ISSUE_MAX_ID),
        TRIGGER_ID,
    )


def _assert_limit_retry_result(test_case, scenario) -> None:
    test_case._mocks[RUN_AGENT].assert_called_once()
    test_case._agent_call = test_case._mocks[RUN_AGENT].call_args
    test_case.assertIsNone(
        test_case._agent_call.kwargs["options"].resume_session_id,
    )
    test_case.assertIn(
        "please fix the flaky test",
        test_case._agent_call.args[1],
    )
    # The preserved feedback is what the dev is asked to act on. The bare
    # command that asked for the retry is not: it is a control signal, and the
    # replay renders whatever it is handed as PR feedback to implement.
    test_case.assertNotIn(
        CONTINUE_COMMAND,
        dev_task_section(test_case._agent_call.args[1]),
    )
    test_case.assertFalse(
        posted_comment_contains(
            scenario.github,
            "needs your actual guidance",
        ),
    )
    test_case.assertIn(
        (ISSUE, VALIDATING),
        scenario.github.label_history,
    )
    final = scenario.github.pinned_data(ISSUE)
    test_case.assertFalse(final.get(AWAITING_HUMAN))
    test_case.assertIsNone(final.get(PARK_REASON))
    # Kept out of the task, still consumed: the watermark advances past the
    # command comment so it does not re-fire on the next tick.
    test_case.assertGreaterEqual(
        final.get(PR_LAST_COMMENT_ID),
        COMMAND_COMMENT_ID,
    )


def _park_then_continue(test_case, failed_message, exit_code, park_phrase) -> None:
    """Tick 1 parks on `failed_message`; tick 2's bare continue retries it."""
    long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    trigger = FakeComment(
        id=TRIGGER_ID,
        body="please fix the flaky test",
        user=FakeUser(ALICE),
        created_at=long_ago,
    )
    scenario = IssueScenario(
        *test_case._seed(pr=test_case._open_pr(), issue_comments=[trigger]),
    )

    # --- Tick 1: the failed resume parks retryably ------------------------
    with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
        test_case._run_fixing(
            scenario.github,
            scenario.issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message=failed_message,
                exit_code=exit_code,
            ),
            head_shas=(SHA_BEFORE, SHA_BEFORE),
        )

    hitl_comment_text = "\n".join(body for _, body in scenario.github.posted_comments)
    _assert_retryable_limit_park(
        test_case,
        scenario,
        scenario.github.pinned_data(ISSUE),
        hitl_comment_text,
        park_phrase,
    )

    # --- Tick 2: `/orchestrator continue` retries, does not refuse --------
    # Stamped NOW, inside the quiet window `IN_REVIEW_DEBOUNCE_SECONDS` holds
    # ordinary feedback for: an accepted continue is a deliberate operator
    # signal and skips the wait, so the retry runs on this tick.
    scenario.issue.comments.append(
        FakeComment(
            id=COMMAND_COMMENT_ID,
            body=CONTINUE_COMMAND,
            user=FakeUser(DAVE),
            created_at=datetime.now(timezone.utc),
        ),
    )
    with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
        test_case._mocks = test_case._run_fixing(
            scenario.github,
            scenario.issue,
            run_agent=_agent(
                session_id=FRESH_SESSION,
                last_message=PUSHED_FIX_MESSAGE,
            ),
            head_shas=(SHA_BEFORE, SHA_AFTER),
        )

    _assert_limit_retry_result(test_case, scenario)


class FixingSilentSessionRecoveryTest(
    unittest.TestCase,
    _StrandedFixingFixtureMixin,
):
    def test_agent_silent_failure_parks_in_fixing(self) -> None:
        # Dev returned empty `last_message` and no commit. The handler
        # routes through `_on_question`'s silent-failure branch, parks
        # with `park_reason=PARK_AGENT_SILENT`, and the silent-park
        # counter ticks so a future resume can drop a poisoned session.
        # Label MUST stay at `fixing`.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please fix the import order",
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(*self._seed(pr=pr, issue_comments=[comment]))

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message="",
                    exit_code=1,
                ),
                head_shas=(SHA_BEFORE, SHA_BEFORE),
            )

        pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PARK_REASON), PARK_AGENT_SILENT)
        self.assertNotIn((ISSUE, VALIDATING), scenario.github.label_history)
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)
        # Silent-park streak counter ticked so the next resume can
        # drop the poisoned session after the configured threshold.
        self.assertGreaterEqual(
            int(pinned_data.get("silent_park_count") or 0),
            1,
        )

    def test_not_the_devs_words_continue_retries(
        self,
    ) -> None:
        # #705 / #1426 regression: a quota notice and a provider refusal both
        # arrive as a normal FINAL message (non-empty `last_message`) during a
        # fixing dev-resume, so reading that field as the agent's words posts
        # either as "agent needs your input". Both must park as a RETRYABLE
        # session failure (`agent_silent`), NOT a real question
        # (`park_reason=None`) -- otherwise the bare `/orchestrator continue`
        # the park asks for is refused as "needs your actual guidance".
        for failed_message, exit_code, park_phrase in _NOT_THE_DEVS_WORDS:
            with self.subTest(park_phrase=park_phrase):
                _park_then_continue(self, failed_message, exit_code, park_phrase)

    def test_restart_resumes_feedback_from_watermarks(
        self,
    ) -> None:
        # Crash/restart contract: the orchestrator has no in-memory
        # state across ticks, so a `fixing` issue with pending feedback
        # in pinned state must drive the rescan entirely off the
        # persisted watermarks + bookmarks. Simulate it by leaving the
        # `pending_fix_*` bookmarks recorded by a prior in_review tick
        # but starting with no transient state (no `awaiting_human`,
        # no in-flight session); the rescan finds the triggering
        # comment past `pr_last_comment_id`, debounce expires, and the
        # dev resumes -- exactly as if the handler had never run before.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        comment = FakeComment(
            id=TRIGGER_ID,
            body="please fix the off-by-one",
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=pr,
                issue_comments=[comment],
                # Bookmarks left by in_review when it routed; transient
                # state cleared as if the process just started up.
                extra_state={
                    AWAITING_HUMAN: False,
                    PENDING_FIX_AT: EARLIER_PENDING_FIX_AT_TS,
                    PENDING_FIX_ISSUE_MAX_ID: TRIGGER_ID,
                },
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        self._mocks[RUN_AGENT].assert_called_once()
        # The followup quotes the triggering comment, proving the
        # rescan re-derived the unread feedback from the persisted
        # watermarks rather than relying on in-memory state.
        self._agent_call = self._mocks[RUN_AGENT].call_args
        prompt = self._agent_call.args[1]
        self.assertIn("please fix the off-by-one", prompt)
        # Push succeeded -> validating directly (the reviewer
        # re-evaluates the new head next tick); bookmarks cleared.
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        self.assertIsNone(self._pinned_data.get(PENDING_FIX_AT))
        self.assertIsNone(self._pinned_data.get(PENDING_FIX_ISSUE_MAX_ID))
