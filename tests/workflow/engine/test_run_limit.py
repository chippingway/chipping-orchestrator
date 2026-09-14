# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The park a spent lifetime agent-run ledger leaves, and what it says once.

Four things are pinned here, each one a promise the hold above this owner is
written on: a park that is durable and stable before a word of it is said, a
sentence scoped to the exhaustion it explains, that sentence owed until the
thread is shown to carry it, and a park that says nothing new on the ticks
after the one that took it -- neither to the thread nor to the budget stream,
which is told about a lifetime ending once because a lifetime ends once.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.engine import run_limit as _run_limit
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.engine import (
    run_budget_test_support as budget,
    run_limit_case as _limit_case,
    run_limit_seeds as _limit_seeds,
    run_limit_test_support as support,
)

_MESSAGE = "message"

# A reading no sentence written for the full allowance is about: the ceiling a
# human moved, and the runs an issue spent under it.
_WIDENED = 80

_SPENT_UNDER_IT = 80

_SENTENCE = "spent it all"

# What a hand edit, an older binary, or a truncated write can leave where a
# whole obligation record belongs. The counts are part of that record rather
# than decoration: a sentence with no reading behind it is one nothing can
# hold up against the ledger.
_UNREADABLE_NOTICES = (
    _SENTENCE,
    {},
    {_MESSAGE: _SENTENCE},
    {_MESSAGE: "", "allowance": 50, "spent": 50},
    {_MESSAGE: _SENTENCE, "allowance": "50", "spent": 50},
    {_MESSAGE: _SENTENCE, "allowance": 50, "spent": -1},
    None,
    [_SENTENCE],
)


class StandingParkTest(unittest.TestCase):
    """What makes this park recognizable to the tick after it."""

    def test_both_halves_are_asked(self) -> None:
        # The flag alone is every stage's park and the reason alone outlives
        # a park something has already taken down, so neither answers here.
        for fields in (
            {},
            {_limit_seeds.AWAITING_HUMAN: True},
            {_limit_seeds.PARK_REASON: _run_limit.PARK_AGENT_RUN_LIMIT},
            {_limit_seeds.AWAITING_HUMAN: True, _limit_seeds.PARK_REASON: "retry_cap"},
        ):
            with self.subTest(fields=fields):
                self.assertFalse(
                    _run_limit._park_stands(_limit_seeds.state_with(**fields)),
                )

    def test_the_pair_is_the_park(self) -> None:
        self.assertTrue(_run_limit._park_stands(_limit_seeds.parked_state()))


class ParkStagingTest(unittest.TestCase):
    """The durable half, and the sentence recorded beside it."""

    def test_a_first_refusal_stages_park_and_sentence(self) -> None:
        state = _limit_seeds.state_with()

        self.assertTrue(_run_limit._stage_park(state, _limit_seeds.ledger()))

        self.assertTrue(state.get(_limit_seeds.AWAITING_HUMAN))
        self.assertEqual(
            state.get(_limit_seeds.PARK_REASON), _run_limit.PARK_AGENT_RUN_LIMIT,
        )
        staged = support.owed(state)
        self.assertEqual(staged.message, support.notice_text())
        self.assertEqual(staged.allowance, _limit_seeds.ALLOWANCE)
        self.assertEqual(staged.spent, _limit_seeds.ALLOWANCE)

    def test_an_announced_park_owes_nothing_more(self) -> None:
        # The repeat this protocol exists to stop: the ledger is re-read on
        # every tick that reaches a spawn, so nothing else would stop it.
        state = _limit_seeds.parked_state()

        self.assertFalse(_run_limit._stage_park(state, _limit_seeds.ledger()))

        self.assertNotIn(support.NOTICE, state.data)

    def test_an_unsaid_sentence_is_kept_verbatim(self) -> None:
        # The thread is searched for exactly the text the park recorded, so a
        # sentence reworded between the post and the write that records it
        # would find nothing and be said a second time.
        state = _limit_seeds.parked_state(owing=True)
        state.get(support.NOTICE)[_MESSAGE] = _SENTENCE

        self.assertTrue(_run_limit._stage_park(state, _limit_seeds.ledger()))

        self.assertEqual(support.owed(state).message, _SENTENCE)

    def test_another_readings_sentence_is_replaced(self) -> None:
        # It quotes an allowance or a spend the issue has moved off, and a
        # human shown those numbers is being asked about a state that is over.
        state = _limit_seeds.parked_state(owing=True)
        widened = _limit_seeds.ledger(allowance=_WIDENED, used=_SPENT_UNDER_IT)

        self.assertTrue(_run_limit._stage_park(state, widened))

        self.assertEqual(
            support.owed(state).message,
            support.notice_text(allowance=_WIDENED, used=_SPENT_UNDER_IT),
        )

    def test_an_unreadable_obligation_owes_nothing(self) -> None:
        # An issue recorded before this field existed, and a hand-edited one,
        # leave a park that says nothing rather than a tick that raises.
        for recorded in _UNREADABLE_NOTICES:
            with self.subTest(recorded=recorded):
                state = _limit_seeds.parked_state(**{support.NOTICE: recorded})

                self.assertIsNone(support.owed(state))
                self.assertFalse(
                    _run_limit._stage_park(state, _limit_seeds.ledger()),
                )


class ParkExhaustedTest(_limit_case._ParkCase):
    """The composition: persist the whole park, then say it once."""

    def test_the_park_is_durable_before_a_word_of_it(self) -> None:
        # A notice on a thread no pinned state backs is one nothing would
        # reconcile, and the next tick would run the issue again beneath a
        # comment saying it had stopped.
        state = _limit_seeds.state_with()

        with (
            patch.object(self.gh, "comment", side_effect=RuntimeError("nope")),
            self.assertRaises(RuntimeError),
        ):
            self._park(state)

        recorded = self.gh.pinned_data(support.ISSUE_NUMBER)
        self.assertTrue(recorded[_limit_seeds.AWAITING_HUMAN])
        self.assertEqual(
            recorded[_limit_seeds.PARK_REASON], _run_limit.PARK_AGENT_RUN_LIMIT,
        )
        self.assertEqual(
            recorded[support.NOTICE][_MESSAGE], support.notice_text(),
        )

    def test_a_first_refusal_says_it_once(self) -> None:
        state = _limit_seeds.state_with()

        self._park(state)

        posted = self.gh.posted_comments[-1][1]
        self.assertIn(config.HITL_MENTIONS, posted)
        self.assertIn(support.notice_text(), posted)
        self.assertNotIn(support.NOTICE, state.data)
        self.assertEqual(support.phases(self.gh), [support.DELIVERED])

    def test_a_later_tick_says_and_writes_nothing(self) -> None:
        # A park already standing and already explained is re-taken silently,
        # and recorded as standing so it is not read as a workflow that
        # stopped for no reason.
        self._park(_limit_seeds.parked_state())

        self.assertEqual(self.gh.posted_comments, [])
        self.assertEqual(self.gh.write_state_calls, 0)
        self.assertEqual(support.phases(self.gh), [support.STANDING])

    def test_a_notice_the_thread_has_is_not_repeated(self) -> None:
        # The pinned write that failed after a post that landed claims the
        # opposite of what the issue holds, and the issue cannot be wrong.
        self.issue.comments.append(FakeComment(
            id=support.WATERMARK,
            body=f"{config.HITL_MENTIONS} {support.notice_text()}",
            user=FakeUser(support.BOT_LOGIN),
        ))
        state = _limit_seeds.parked_state(owing=True)

        self._park(state)

        self.assertEqual(self.gh.posted_comments, [])
        self.assertNotIn(support.NOTICE, state.data)
        self.assertEqual(support.phases(self.gh), [support.RECONCILED])

    def test_an_unreadable_thread_is_said_nothing(self) -> None:
        # The sentence the thread may already carry is exactly the one about
        # to go out, so the park stands and the notice stays owed.
        state = _limit_seeds.state_with()

        with patch.object(
            self.gh, "comments_after", side_effect=RuntimeError("502"),
        ):
            self._park(state)

        self.assertEqual(self.gh.posted_comments, [])
        self.assertIn(support.NOTICE, state.data)
        self.assertEqual(support.phases(self.gh), [])


class ParkRecordTest(_limit_case._ParkCase):
    """What the shared budget stream is told about a lifetime ending.

    Once per park, on the write that makes it durable: a park is met again by
    every launch the issue has left, so a record per meeting would report one
    ending as a stream of them.
    """

    def test_the_tick_that_takes_the_park_records_it(self) -> None:
        # The one budget transition a park is: the launch the ceiling turned
        # away, with the reading the refusal was made on under it.
        self._park(_limit_seeds.state_with())

        recorded = budget.audited(self.gh)[0]
        self.assertEqual(recorded[budget.PHASE], budget.EXHAUSTED)
        self.assertEqual(recorded[budget.USED], _limit_seeds.ALLOWANCE)
        self.assertEqual(recorded[budget.REMAINING], 0)
        self.assertEqual(recorded[budget.REASON], budget.ALLOWANCE_SPENT)

    def test_a_park_owing_its_sentence_records_none(self) -> None:
        # The sentence is re-said because the thread was never told, but the
        # lifetime ended on the tick that took the park -- and it ends once.
        self._park(_limit_seeds.owing_park())

        self.assertEqual(len(self.gh.posted_comments), 1)
        self.assertEqual(budget.audited(self.gh), [])


class NoticeDeliveryTest(unittest.TestCase):
    """Saying what a park is for, exactly once per park."""

    def setUp(self) -> None:
        client, issue = support.issue_and_client()
        self.gh = client
        self.issue = issue
        self.state = _limit_seeds.parked_state(owing=True)

    def test_delivery_says_it_once_and_records_it(self) -> None:
        said = _run_limit._deliver_notice(self.gh, self.issue, self.state)

        self.assertTrue(said)
        self.assertNotIn(support.NOTICE, self.state.data)
        # The shared park clears the reason by contract, and the response
        # boundary a reply is measured against moves past the mention.
        self.assertEqual(
            self.state.get(_limit_seeds.PARK_REASON),
            _run_limit.PARK_AGENT_RUN_LIMIT,
        )
        self.assertEqual(
            self.state.get(support.LAST_ACTION_COMMENT_ID),
            self.gh.latest_comment_id(self.issue),
        )
        self.assertEqual(support.phases(self.gh), [support.DELIVERED])

    def test_a_settled_obligation_says_nothing(self) -> None:
        _run_limit._deliver_notice(self.gh, self.issue, self.state)

        self.assertFalse(
            _run_limit._deliver_notice(self.gh, self.issue, self.state),
        )
        self.assertEqual(len(self.gh.posted_comments), 1)

    def test_a_refused_post_leaves_the_sentence_owed(self) -> None:
        # The obligation is dropped by the post that discharges it, so a
        # comment GitHub refused is retried rather than lost.
        with (
            patch.object(self.gh, "comment", side_effect=RuntimeError("nope")),
            self.assertRaises(RuntimeError),
        ):
            _run_limit._deliver_notice(self.gh, self.issue, self.state)

        self.assertIn(support.NOTICE, self.state.data)
        self.assertEqual(support.phases(self.gh), [])


class NoticeReconciliationTest(unittest.TestCase):
    """A sentence the thread already carries is not said a second time."""

    def test_a_posted_notice_is_recorded_not_repeated(self) -> None:
        gh, state, reading = self._reconcile(
            FakeComment(
                id=support.WATERMARK + 5,
                body=f"@ops {support.notice_text()}",
                user=FakeUser(support.BOT_LOGIN),
            ),
        )

        self.assertIs(reading, _run_limit.NoticeReading.SAID)
        self.assertEqual(gh.posted_comments, [])
        self.assertNotIn(support.NOTICE, state.data)
        # Repaired to the comment that carried it -- the id the write that
        # failed was going to move the watermark to.
        self.assertEqual(
            state.get(support.LAST_ACTION_COMMENT_ID), support.WATERMARK + 5,
        )
        self.assertEqual(support.phases(gh), [support.RECONCILED])

    def test_a_notice_below_the_watermark_is_stale(self) -> None:
        # A sentence from an episode that COMPLETED sits at or below the mark
        # its own post moved, and cannot answer for a later park.
        gh, state, reading = self._reconcile(
            FakeComment(
                id=support.WATERMARK - 5,
                body=support.notice_text(),
                user=FakeUser(support.BOT_LOGIN),
            ),
        )

        self.assertIs(reading, _run_limit.NoticeReading.UNSAID)
        self.assertIn(support.NOTICE, state.data)
        self.assertEqual(support.phases(gh), [])

    def test_an_outsiders_copy_is_no_receipt(self) -> None:
        # The sentence is plain text on a public thread. Read from anybody, a
        # copy of it would mark the notice said, drag the watermark past
        # whatever was written under it, and leave the human never told.
        gh, state, reading = self._reconcile(
            FakeComment(
                id=support.WATERMARK + 5,
                body=support.notice_text(),
                user=FakeUser(support.OUTSIDER),
            ),
        )

        self.assertIs(reading, _run_limit.NoticeReading.UNSAID)
        self.assertIn(support.NOTICE, state.data)
        self.assertEqual(
            state.get(support.LAST_ACTION_COMMENT_ID), support.WATERMARK,
        )
        self.assertEqual(support.phases(gh), [])

    def test_an_unreadable_thread_is_not_a_miss(self) -> None:
        # A request that failed inside the window where the sentence is
        # already on the thread reads as absent unless it says otherwise, and
        # a caller told "absent" posts the duplicate this protocol stops.
        gh, issue = support.issue_and_client()
        state = _limit_seeds.parked_state(owing=True)

        with patch.object(gh, "comments_after", side_effect=RuntimeError("502")):
            reading = _run_limit._reconcile_notice(gh, issue, state)

        self.assertIs(reading, _run_limit.NoticeReading.UNREADABLE)
        self.assertIn(support.NOTICE, state.data)

    def test_an_obligation_nobody_holds_is_said(self) -> None:
        gh, issue = support.issue_and_client()

        reading = _run_limit._reconcile_notice(
            gh, issue, _limit_seeds.parked_state(),
        )

        self.assertIs(reading, _run_limit.NoticeReading.SAID)
        self.assertEqual(support.phases(gh), [])

    def _reconcile(self, *comments):
        gh, issue = support.issue_and_client(*comments)
        state = _limit_seeds.parked_state(owing=True, **{
            support.LAST_ACTION_COMMENT_ID: support.WATERMARK,
        })
        reading = _run_limit._reconcile_notice(gh, issue, state)
        return gh, state, reading


class NoticeReplayTest(unittest.TestCase):
    """The retry the durable half of a park earns.

    Nothing below the hold runs, so a sentence a refused post or an
    unreadable thread left owed would be owed for as long as the issue is
    parked -- which, on a lifetime total, is for good.
    """

    def setUp(self) -> None:
        client, issue = support.issue_and_client()
        self.gh = client
        self.issue = issue

    def test_an_owed_sentence_is_said_and_recorded(self) -> None:
        state = _limit_seeds.parked_state(owing=True)

        self.assertTrue(
            _run_limit._replay_owed_notice(self.gh, self.issue, state),
        )

        posted = self.gh.posted_comments[-1][1]
        self.assertIn(support.notice_text(), posted)
        # The write is taken here rather than left to a caller that is about
        # to return without dispatching anything at all.
        recorded = self.gh.pinned_data(support.ISSUE_NUMBER)
        self.assertNotIn(support.NOTICE, recorded)
        self.assertEqual(support.phases(self.gh), [support.DELIVERED])

    def test_nothing_owed_and_no_park_replay_nothing(self) -> None:
        for state in (_limit_seeds.parked_state(), _limit_seeds.state_with()):
            with self.subTest(state=state.data):
                self.assertFalse(
                    _run_limit._replay_owed_notice(self.gh, self.issue, state),
                )

        self.assertEqual(self.gh.posted_comments, [])
        self.assertEqual(self.gh.write_state_calls, 0)

    def test_an_unreadable_thread_is_left_owed(self) -> None:
        state = _limit_seeds.parked_state(owing=True)

        with patch.object(
            self.gh, "comments_after", side_effect=RuntimeError("502"),
        ):
            replayed = _run_limit._replay_owed_notice(
                self.gh, self.issue, state,
            )

        self.assertFalse(replayed)
        self.assertEqual(self.gh.posted_comments, [])
        self.assertEqual(self.gh.write_state_calls, 0)
        self.assertIn(support.NOTICE, state.data)


if __name__ == "__main__":
    unittest.main()
