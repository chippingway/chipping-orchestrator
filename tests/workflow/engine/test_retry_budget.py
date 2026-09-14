# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The shared spawn budget: what it decides, and what an empty one parks on.

Four things are pinned here, each one a promise a stage's gate is written on:
a decision that posts nothing and writes nothing it was not allowed to, a park
that is durable and stable, a sentence owed until the thread is shown to carry
it, and one explicit way to buy another attempt.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.engine import (
    retry_budget as _retry_budget,
    retry_notices as _retry_notices,
    retry_values as _retry_values,
)
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.engine import retry_budget_test_support as support
from tests.workflow.fixtures import _iso_hours_ago

# A count outside the range a continuation writes, and what it still buys: one
# attempt at most, and nothing at all where the number itself is nonsense.
_OUT_OF_RANGE_GRANTS = ((2, [True, False]), (-1, [False, False]))


class RetryDecisionTest(unittest.TestCase):
    """What the gate answers, and what it may write while answering."""

    def test_an_unbounded_cap_keeps_no_accounting(self) -> None:
        # An operator who turns the budget off leaves no counters behind for
        # the one who turns it back on.
        state = support.state_with()

        decision = support.decide(state, cap=0)

        self.assertTrue(decision.allowed)
        self.assertEqual(state.data, {})

    def test_the_first_attempt_opens_the_window(self) -> None:
        state = support.state_with()

        decision = support.decide(state)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.spent, 1)
        self.assertEqual(state.get(support.RETRY_COUNT), 1)
        self.assertEqual(
            decision.window_start, state.get(support.RETRY_WINDOW_START),
        )

    def test_an_exhausted_budget_writes_nothing(self) -> None:
        # The refusal is the caller's to act on: a tick that dies between this
        # answer and the park's own write leaves the budget as it was.
        opened = _iso_hours_ago(1)
        state = support.state_with(
            retry_count=support.CAP, retry_window_start=opened,
        )

        decision = support.decide(state)

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.cap, support.CAP)
        self.assertEqual(decision.stage, support.STAGE)
        self.assertEqual(
            state.data,
            {"retry_count": support.CAP, "retry_window_start": opened},
        )

    def test_an_elapsed_window_reopens_unparked(self) -> None:
        state = support.state_with(
            retry_count=support.CAP,
            retry_window_start=_iso_hours_ago(support.ELAPSED_HOURS),
        )

        decision = support.decide(state)

        self.assertTrue(decision.allowed)
        self.assertEqual(state.get(support.RETRY_COUNT), 1)

    def test_an_unreadable_window_reopens(self) -> None:
        # Absent, hand-edited, and offset-free stamps all read as no window at
        # all rather than raising inside the tick that asked.
        for stamp in (None, "", "yesterday", 17, "2026-09-02T10:00:00"):
            with self.subTest(stamp=stamp):
                state = support.state_with(
                    retry_count=support.CAP, retry_window_start=stamp,
                )

                decision = support.decide(state)

                self.assertTrue(decision.allowed)
                self.assertEqual(state.get(support.RETRY_COUNT), 1)

    def test_an_unbounded_pass_drops_stale_counters(self) -> None:
        # Turning the budget off is not a pause on the window: what it finds
        # is dropped as it passes, so turning it back on opens a fresh one
        # rather than refusing out of a count charged under a setting that has
        # been changed twice since.
        budget = support.state_with()

        under_cap = [
            support.decide(budget).allowed for _ in range(support.CAP + 1)
        ]
        under_none = support.decide(budget, cap=0).allowed
        dropped = dict(budget.data)

        self.assertEqual(under_cap, [True, True, True, False])
        self.assertTrue(under_none)
        self.assertEqual(dropped, {})
        self.assertTrue(support.decide(budget).allowed)


class StandingParkTest(unittest.TestCase):
    """What a park nobody has answered outlives.

    The gate asks it first, ahead of the cap and ahead of the window, because
    every other way past it is one no human took.
    """

    def test_it_outlives_its_own_window(self) -> None:
        # The notice asked for a human. The clock is not one, so a park a day
        # old is still exhausted and its window is left untouched.
        opened = _iso_hours_ago(support.ELAPSED_HOURS)
        state = support.parked_state(retry_window_start=opened)

        decision = support.decide(state)

        self.assertFalse(decision.allowed)
        self.assertEqual(state.get(support.RETRY_COUNT), support.CAP)
        self.assertEqual(state.get(support.RETRY_WINDOW_START), opened)

    def test_it_outlives_an_unbounded_cap(self) -> None:
        # Turning the budget off is a setting change, not the continuation
        # the notice asked for, so the park refuses ahead of the cap.
        state = support.parked_state(retry_window_start=_iso_hours_ago(1))

        decision = support.decide(state, cap=0)

        self.assertFalse(decision.allowed)
        self.assertEqual(state.get(support.RETRY_COUNT), support.CAP)

    def test_another_stage_park_is_not_this_one(self) -> None:
        # Only this park suspends renewal. An issue waiting on an agent's
        # question waits on a reply, not on a budget somebody has to lift.
        state = support.state_with(
            awaiting_human=True,
            park_reason=support.AGENT_QUESTION,
            retry_count=support.CAP,
            retry_window_start=_iso_hours_ago(support.ELAPSED_HOURS),
        )

        self.assertTrue(support.decide(state).allowed)


class RetryCapParkTest(unittest.TestCase):
    """What a refused tick stages, and what a standing park stops it staging."""

    def test_a_first_refusal_stages_park_and_sentence(self) -> None:
        state = support.state_with(
            retry_count=support.CAP, retry_window_start=_iso_hours_ago(1),
        )

        owes = support.staged_park(state)

        self.assertTrue(owes)
        self.assertTrue(state.get(support.AWAITING_HUMAN))
        self.assertEqual(
            state.get(support.PARK_REASON), _retry_values.PARK_RETRY_CAP,
        )
        self.assertEqual(
            state.get(_retry_values.RETRY_CAP_STAGE), support.STAGE,
        )
        sentence = support.owed(state)
        self.assertIn(
            f"hit retry cap ({support.CAP}/day) for {support.STAGE}", sentence,
        )
        self.assertIn(state.get(support.RETRY_WINDOW_START), sentence)

    def test_an_announced_park_owes_nothing_more(self) -> None:
        # The budget is re-decided every eligible tick; without this the same
        # sentence reaches the same thread once a poll until a human arrives.
        state = support.parked_state(retry_window_start=_iso_hours_ago(1))

        owes = support.staged_park(state)

        self.assertFalse(owes)
        self.assertIsNone(support.owed(state))
        self.assertTrue(state.get(support.AWAITING_HUMAN))

    def test_an_unsaid_sentence_is_kept_verbatim(self) -> None:
        # A flag is not a receipt, so the sentence stays owed -- and it stays
        # the one the park was taken with. The thread is searched for exactly
        # that text, so a refusal arriving under another stage or a retuned
        # cap would otherwise find nothing, say it twice, and attribute the
        # park to a stage that never took it.
        state = support.parked_state(
            retry_window_start=_iso_hours_ago(1),
            retry_cap_notice=support.NOTICE,
        )

        owes = support.staged_park(state, stage=support.OTHER_STAGE, cap=9)

        self.assertTrue(owes)
        self.assertEqual(support.owed(state), support.NOTICE)
        self.assertEqual(
            state.get(_retry_values.RETRY_CAP_STAGE), support.STAGE,
        )

    def test_a_park_with_no_stage_takes_this_one(self) -> None:
        # A park nobody can name is worse than one named late: an issue parked
        # before the field existed is repaired rather than left unattributed.
        state = support.parked_state(
            retry_cap_stage=None, retry_cap_notice=support.NOTICE,
        )

        support.staged_park(state, stage=support.OTHER_STAGE)

        self.assertEqual(
            state.get(_retry_values.RETRY_CAP_STAGE), support.OTHER_STAGE,
        )

    def test_an_unreadable_sentence_owes_nothing(self) -> None:
        for sentence in (None, "", 7, {"message": "said"}):
            with self.subTest(sentence=sentence):
                hand_edited = support.parked_state(retry_cap_notice=sentence)

                self.assertIsNone(support.owed(hand_edited))


class NoticeDeliveryTest(unittest.TestCase):
    """Saying what a park is for, exactly once per park."""

    def setUp(self) -> None:
        client, issue = support.issue_and_client()
        self.gh = client
        self.issue = issue
        self.state = support.parked_state(retry_cap_notice=support.NOTICE)

    def test_delivery_says_it_once_and_records_it(self) -> None:
        said = _retry_notices._deliver_notice(self.gh, self.issue, self.state)

        self.assertTrue(said)
        posted = self.gh.posted_comments[-1][1]
        self.assertIn(config.HITL_MENTIONS, posted)
        self.assertIn(support.NOTICE, posted)
        self.assertIsNone(support.owed(self.state))
        # The shared park clears the reason by contract, and the response
        # boundary a reply is measured against moves past the mention.
        self.assertEqual(
            self.state.get(support.PARK_REASON), _retry_values.PARK_RETRY_CAP,
        )
        self.assertEqual(
            self.state.get(support.LAST_ACTION_COMMENT_ID),
            self.gh.latest_comment_id(self.issue),
        )
        self.assertEqual(support.phases(self.gh), ["delivered"])

    def test_a_settled_obligation_says_nothing(self) -> None:
        _retry_notices._deliver_notice(self.gh, self.issue, self.state)

        self.assertFalse(
            _retry_notices._deliver_notice(self.gh, self.issue, self.state),
        )
        self.assertEqual(len(self.gh.posted_comments), 1)

    def test_a_refused_post_leaves_the_sentence_owed(self) -> None:
        # The obligation is dropped by the post that discharges it, so a
        # comment GitHub refused is retried rather than lost.
        with (
            patch.object(self.gh, "comment", side_effect=RuntimeError("nope")),
            self.assertRaises(RuntimeError),
        ):
            _retry_notices._deliver_notice(self.gh, self.issue, self.state)

        self.assertIsNotNone(support.owed(self.state))
        self.assertEqual(support.phases(self.gh), [])


class NoticeReconciliationTest(unittest.TestCase):
    """A sentence the thread already carries is not said a second time."""

    def test_a_posted_notice_is_recorded_not_repeated(self) -> None:
        gh, state, reading = self._reconcile(
            FakeComment(
                id=support.WATERMARK + 5,
                body=f"@ops {support.NOTICE}",
                user=FakeUser(support.BOT_LOGIN),
            ),
        )

        self.assertIs(reading, _retry_values.NoticeReading.SAID)
        self.assertEqual(gh.posted_comments, [])
        self.assertIsNone(support.owed(state))
        # Repaired to the comment that carried it -- the id the write that
        # failed was going to move the watermark to.
        self.assertEqual(
            state.get(support.LAST_ACTION_COMMENT_ID), support.WATERMARK + 5,
        )
        self.assertEqual(support.phases(gh), ["reconciled"])

    def test_a_notice_below_the_watermark_is_stale(self) -> None:
        # A sentence from an episode that COMPLETED sits at or below the mark
        # its own post moved, and cannot answer for a later park.
        gh, state, reading = self._reconcile(
            FakeComment(
                id=support.WATERMARK - 5,
                body=support.NOTICE,
                user=FakeUser(support.BOT_LOGIN),
            ),
        )

        self.assertIs(reading, _retry_values.NoticeReading.UNSAID)
        self.assertIsNotNone(support.owed(state))
        self.assertEqual(support.phases(gh), [])

    def test_an_outsiders_copy_is_no_receipt(self) -> None:
        # The sentence is plain text on a public thread. Read from anybody, a
        # copy of it would mark the notice said, drag the watermark past
        # whatever was written under it, and leave the human never told.
        gh, state, reading = self._reconcile(
            FakeComment(
                id=support.WATERMARK + 5,
                body=support.NOTICE,
                user=FakeUser(support.OUTSIDER),
            ),
        )

        self.assertIs(reading, _retry_values.NoticeReading.UNSAID)
        self.assertIsNotNone(support.owed(state))
        self.assertEqual(
            state.get(support.LAST_ACTION_COMMENT_ID), support.WATERMARK,
        )
        self.assertEqual(support.phases(gh), [])

    def test_an_unreadable_thread_is_not_a_miss(self) -> None:
        # A request that failed inside the window where the sentence is
        # already on the thread reads as absent unless it says otherwise, and
        # a caller told "absent" posts the duplicate this protocol stops.
        gh, issue = support.issue_and_client()
        state = support.parked_state(retry_cap_notice=support.NOTICE)

        with patch.object(gh, "comments_after", side_effect=RuntimeError("502")):
            reading = _retry_notices._reconcile_notice(gh, issue, state)

        self.assertIs(reading, _retry_values.NoticeReading.UNREADABLE)
        self.assertIsNotNone(support.owed(state))

    def _reconcile(self, *comments):
        gh, issue = support.issue_and_client(*comments)
        state = support.parked_state(
            retry_cap_notice=support.NOTICE,
            last_action_comment_id=support.WATERMARK,
        )
        reading = _retry_notices._reconcile_notice(gh, issue, state)
        return gh, state, reading


class ContinuationTest(unittest.TestCase):
    """The one renewal there is, and how much of the budget it buys."""

    def test_a_continuation_clears_the_park(self) -> None:
        gh, issue = support.issue_and_client()
        state = support.parked_state(
            retry_window_start=_iso_hours_ago(1),
            retry_cap_notice=support.NOTICE,
        )

        with patch.object(config, "MAX_RETRIES_PER_DAY", support.CAP):
            _retry_budget._grant_continuation(gh, issue, state)
        allowed = [support.decide(state).allowed for _ in range(2)]

        self.assertFalse(state.get(support.AWAITING_HUMAN))
        self.assertIsNone(state.get(support.PARK_REASON))
        self.assertNotIn(_retry_values.RETRY_CAP_STAGE, state.data)
        self.assertNotIn(_retry_values.RETRY_CAP_NOTICE, state.data)
        self.assertEqual(gh.posted_comments, [])
        # One attempt, not a fresh day of them: the second is refused again.
        self.assertEqual(allowed, [True, False])
        # Emitted while the park it retires can still name its stage.
        self.assertEqual(support.phases(gh), ["continued"])
        self.assertEqual(gh.recorded_events[0]["stage"], support.STAGE)

    def test_one_attempt_whatever_the_cap_becomes(self) -> None:
        # The attempt is stored as itself rather than as a counter to compare
        # against the setting later, so a budget an operator turns off between
        # the word and the spawn cannot swallow it and a widened one cannot
        # multiply it.
        for cap in (0, support.CAP, support.CAP + 2):
            with self.subTest(cap=cap):
                gh, issue = support.issue_and_client()
                state = support.parked_state(
                    retry_window_start=_iso_hours_ago(1),
                )

                with patch.object(
                    config, "MAX_RETRIES_PER_DAY", support.CAP,
                ):
                    _retry_budget._grant_continuation(gh, issue, state)
                allowed = [
                    support.decide(state, cap=cap).allowed for _ in range(3)
                ]

                self.assertEqual(allowed, [True, False, False])
                self.assertEqual(state.get(support.CONTINUED), 0)

    def test_an_unreadable_grant_hands_out_nothing(self) -> None:
        # Read against a record shaped like a fresh renewal, which is the one
        # that would give it away: the field is THERE, so this issue runs on
        # grants, and a value nothing can read proves no attempt. Fallen
        # through to the setting it would answer with a whole window's worth
        # of spawns -- or with every spawn where the budget is off -- off the
        # strength of something somebody typed.
        for granted in (True, "1", "false", []):
            with self.subTest(granted=granted):
                edited = support.state_with(
                    retry_cap_continued=granted,
                    retry_count=0,
                    retry_window_start=_iso_hours_ago(2),
                )

                self.assertFalse(support.decide(edited).allowed)
                self.assertFalse(support.decide(edited, cap=0).allowed)

    def test_a_cleared_grant_runs_on_the_budget(self) -> None:
        # The other half of it: absence is the one reading that means "no
        # grant", and the reset a publication writes spells that as null, so
        # an issue that shipped is answered by the configured budget again
        # rather than held to a regime nobody is in.
        for cleared in ({}, {support.CONTINUED: None}):
            with self.subTest(cleared=cleared):
                shipped = support.state_with(**cleared)

                self.assertTrue(support.decide(shipped).allowed)

    def test_a_grant_out_of_range_still_buys_one(self) -> None:
        # The field decides how many spawns are handed out, so no edit of it
        # hands out a second: a bigger number buys the one attempt a
        # continuation buys, and a negative buys nothing.
        for granted, bought in _OUT_OF_RANGE_GRANTS:
            with self.subTest(granted=granted):
                edited = support.state_with(
                    retry_cap_continued=granted,
                    retry_count=0,
                    retry_window_start=_iso_hours_ago(2),
                )

                self.assertEqual(
                    [support.decide(edited).allowed for _ in range(2)], bought,
                )


if __name__ == "__main__":
    unittest.main()
