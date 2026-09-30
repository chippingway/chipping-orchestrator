# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The replies an adjudication owes a whole quote, and what repays them.

A question's answer is consumed before the adjudication it reopens passes its
spawn gates, and that adjudication reads the thread through a bounded excerpt
of its tail. So the answer is recorded as owed: quoted whole to every late run
until one has answered it, whether the run was the one reopened, one a later
continue bought after a gate refused the first, or a developer revision. A run
its timeout killed, or one whose CLI stopped on its quota, answered nothing,
so it stays owed to the retry.
"""
from __future__ import annotations

from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.late_split import state as _late_state
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition
from tests.workflow.fixtures import _iso_hours_ago
from tests.workflow.stages.decomposition import late_content_support as _support
from tests.workflow.stages.decomposition.late_content_replies import human_comment, reply
from tests.workflow.stages.decomposition.late_revision_support import (
    ACKNOWLEDGED,
    DEV_PIN,
    DEV_QUESTION,
    QUOTA_EXIT,
    QUOTA_NOTICE,
    UNCHANGED,
    RevisionCase,
)
from tests.workflow.stages.decomposition.late_run_support import agent_reply
from tests.workflow.stages.decomposition.late_test_support import KEYS, late_generation

KEY_OWED_REPLIES = "late_owed_replies"

INSTRUCTION = "keep the retry flag, but move it under the importer section"

# Background past what a prompt's thread excerpt holds, so an excerpt of the
# thread's tail loses whatever came before it in the same comment.
BACKGROUND_WORDS = 700

BACKGROUND = "background " * BACKGROUND_WORDS

LONG_ANSWER = f"{INSTRUCTION}\n\n{BACKGROUND}"

MAX_RETRIES = "MAX_RETRIES_PER_DAY"

PARK_RETRY_CAP = "retry_cap"

# A spawn budget spent to its last slot, so the adjudication an answer
# reopens is refused at its gate.
SPENT = 2

# An earlier reply the generation still owes, carried on the thread it came
# from and counted into the baseline that consumed it.
OWED_ID = 7

# A human's answer to the question a developer parked on.
SECOND_ANSWER = "keep the old column for one release"

# Every run that comes back having answered nothing: killed at its timeout,
# stopped by its CLI on the account's quota, with the notice or without it, or
# refused by its provider.
_UNANSWERED = (
    ("a timeout", {"timed_out": True}, ""),
    ("a silent quota stop", {"exit_code": QUOTA_EXIT}, ""),
    ("a quota notice", {"exit_code": QUOTA_EXIT}, QUOTA_NOTICE),
    ("a provider refusal", {}, "API Error: 429 Too Many Requests"),
)


class OwedAnswerTest(RevisionCase):
    """A long answer reaches the adjudication it was consumed for, whole."""

    def test_a_long_answer_is_quoted_whole(self) -> None:
        self._seed(**_support.ASKED_STATE)
        reply(self.issue, LONG_ANSWER)

        _outcome, spawn = self._run()

        spawn.assert_called_once()
        self.assertIn(INSTRUCTION, spawn.call_args.args[1])
        self.assertNotIn(KEY_OWED_REPLIES, self._pinned())

    def test_a_refused_rerun_keeps_it_owed(self) -> None:
        # The answer is consumed, and the rerun it bought is refused at the
        # budget: no run read a word of it, so it stays owed.
        answer = self._refused_over_a_long_answer()

        pinned = self._pinned()
        self.assertEqual(pinned[KEYS.park_reason], PARK_RETRY_CAP)
        self.assertEqual(pinned[KEY_OWED_REPLIES], [answer.id])

    def test_the_run_a_continue_buys_repays_it(self) -> None:
        self._refused_over_a_long_answer()
        reply(self.issue, _support.BARE_CONTINUE)

        _outcome, spawn = self._run()

        spawn.assert_called_once()
        self.assertIn(INSTRUCTION, spawn.call_args.args[1])
        self.assertNotIn(KEY_OWED_REPLIES, self._pinned())

    def test_no_answer_leaves_it_owed_to_the_retry(self) -> None:
        # Nothing was recorded over the answer, so the retry the park earns
        # is quoted it whole again, and only the verdict that retry records
        # repays it.
        for shape, ended, said in _UNANSWERED:
            with self.subTest(run=shape):
                self._unanswered_over_a_long_answer(agent_reply(said, **ended))

                _outcome, spawn = self._run()

                spawn.assert_called_once()
                self.assertIn(INSTRUCTION, spawn.call_args.args[1])
                self.assertNotIn(KEY_OWED_REPLIES, self._pinned())

    def _unanswered_over_a_long_answer(self, ended) -> None:
        """Answer a question, then have the run it reopens answer nothing."""
        self._seed(**_support.ASKED_STATE)
        answer = reply(self.issue, LONG_ANSWER)
        parked, _spawn = self._run(ended)
        self.assertEqual(parked.disposition, _LateDisposition.PARKED)
        self.assertEqual(self._pinned()[KEY_OWED_REPLIES], [answer.id])

    def _refused_over_a_long_answer(self):
        """Answer a question at a spent budget, so the rerun is refused."""
        capped = patch.object(config, MAX_RETRIES, SPENT)
        capped.start()
        self.addCleanup(capped.stop)
        self._seed(**_support.ASKED_STATE, **{
            KEYS.retry_count: SPENT, KEYS.retry_window: _iso_hours_ago(1),
        })
        answer = reply(self.issue, LONG_ANSWER)
        _outcome, spawn = self._run()
        spawn.assert_not_called()
        return answer


class OwedReplyTest(RevisionCase):
    """Whatever runs first over an owed reply reads it, and nothing reuses past it."""

    def test_a_revision_repays_it(self) -> None:
        self._owing(**DEV_PIN)
        reply(self.issue)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        self.assertIn(INSTRUCTION, spawn.call_args.args[1])
        self.assertNotIn(KEY_OWED_REPLIES, self._pinned())

    def test_an_unanswering_revision_leaves_it(self) -> None:
        # The worktree the run left is still reconciled, but the run was
        # killed or never started work, so the reply stays owed to the next.
        for shape, ended, said in _UNANSWERED:
            with self.subTest(run=shape):
                self._owing(**DEV_PIN)
                reply(self.issue)

                outcome, spawn = self._revise(reply=agent_reply(said, **ended))

                self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
                self.assertIn(INSTRUCTION, spawn.call_args.args[1])
                self.assertEqual(self._pinned()[KEY_OWED_REPLIES], [OWED_ID])

    def test_a_parked_revision_leaves_it(self) -> None:
        # A question over an unchanged commit answers nothing: the park it
        # takes keeps the reply owed, and the developer run the human's answer
        # buys is quoted it whole again and repays it.
        self._owing(**DEV_PIN)
        reply(self.issue)
        parked, _spawn = self._revise(
            reply=DEV_QUESTION, seed=UNCHANGED, measurement=ACKNOWLEDGED,
        )
        self.assertEqual(parked.disposition, _LateDisposition.PARKED)
        self.assertEqual(self._pinned()[KEY_OWED_REPLIES], [OWED_ID])
        reply(self.issue, SECOND_ANSWER)

        outcome, spawn = self._revise()

        self.assertEqual(outcome.disposition, _LateDisposition.REVISED)
        self.assertIn(INSTRUCTION, spawn.call_args.args[1])
        self.assertNotIn(KEY_OWED_REPLIES, self._pinned())

    def test_a_recorded_answer_is_not_reused_over_it(self) -> None:
        # An answer taken before the reply was read is not one taken over
        # it, so the adjudication is paid for again rather than reused.
        self._owing(**_support.RECORDED_SINGLE)

        _outcome, spawn = self._run()

        spawn.assert_called_once()
        self.assertIn(INSTRUCTION, spawn.call_args.args[1])

    def _owing(self, **state) -> None:
        """A generation that still owes one long reply, already consumed."""
        owed = human_comment(OWED_ID, LONG_ANSWER)
        github, issue = _support.late_issue(
            comments=(owed,),
            generation=late_generation(owed_replies=(OWED_ID,)),
            **state,
        )
        self.github = github
        self.issue = issue
        self.assertEqual(
            _late_state.read_late_generation(
                github.read_pinned_state(issue),
            ).owed_replies,
            (OWED_ID,),
        )
