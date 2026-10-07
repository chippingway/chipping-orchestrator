# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The recovery of a push an interrupted tick already landed, through the per-tick refresh and the workflow's own road.

Nothing is pushed a second time: the git owner observes where the remote has
the branch, and a landing it finds standing is handed to the one finish every
landing gets. Each case reads back what GitHub was left with: PR #42's head,
the label, the pinned record, the notices and events, the pushes made, and
what the next tick does.
"""
from __future__ import annotations

import unittest

from orchestrator.git.base_sync import landed_recovery as _landed_recovery
from tests.git.base_sync import refresh_test_support as base
from tests.git.base_sync.candidate_reads_support import _checkout_carries
from tests.git.base_sync.report_debt_test_support import owed
from tests.workflow.engine import (
    rewrite_landed_test_support as landed,
    rewrite_publication_moves as moves,
    rewrite_publication_test_support as world,
    rewrite_retry_test_support as retry,
)

# The park every landing this road may not finish takes, with HEAD and the anchor kept.
HELD_FOR_A_HUMAN = (True, retry.PARK_PUSH_FAILED)

# Why a head nothing this attempt wrote vouches for is not finished.
UNPROVEN_FOREIGN = _landed_recovery._UNPROVEN_LANDING.format(published=world.FOREIGN)

# Each landing the pinned comment does not account for: what the comment says
# beside the attempt, the records written over it, the paths the checkout
# carries uncommitted, and the reason the park it takes names.
UNACCOUNTED = (
    (
        "a mark naming another head",
        {landed.KEY_ANNOUNCED: world.FOREIGN}, (), (), _landed_recovery._FOREIGN_MARK,
    ),
    (
        "a record naming another head",
        {retry.KEY_REWRITE_SHA: world.FOREIGN}, (), (),
        _landed_recovery._UNPROVEN_LANDING.format(published=landed.REPLAY),
    ),
    (
        "a verdict beside uncommitted work",
        {}, (landed.a_verdict_settled_onto_the_replay,), ("scratch.txt",), _landed_recovery._LOOSE_TREE,
    ),
)


def _taken_over(case) -> None:
    """The checkout and PR #42 moved together onto somebody else's head."""
    case.world.head = world.FOREIGN
    moves.PullRequestOn(world.FOREIGN)(case)


class LandedPushTest(landed.LandedCase):
    """A push the remote already carries is finished once, with nothing sent again."""

    def test_a_lost_answer_is_not_pushed_again(self) -> None:
        # The dead tick's push reached PR #42 and its answer never came back.
        # The landing is observed rather than pushed again, announced as one
        # found standing, and the tick after has no anchor left to answer.
        self._ticks()
        self._ticks()

        self._assert_finished()
        self.assertIn(landed.FOUND_NOTICE, self.gh.posted_pr_comments[-1][1])

    def test_a_remote_moved_since_finishes_nothing(self) -> None:
        # The fetch read PR #42 on the replay, and the observation behind it
        # finds somebody's push there instead: nothing is said, routed, or
        # reset, and the attempt stands for the next tick, which classifies
        # the remote as it then finds it.
        self.world.reads_first(world.FOREIGN)

        self._ticks()

        self._assert_held()
        self._ticks()
        self._assert_finished()

    def test_a_base_that_moved_again_is_rebased_on(self) -> None:
        # The base advanced past the landed replay again: the finish announces
        # the landing with the base it fell behind, routes nothing, and the
        # same tick rebases the replay and publishes what that leaves, leased
        # to the head PR #42 stands on. The debt follows the head pushed last.
        self._ticks(lag=landed.LAG)
        self._ticks()

        self.assertEqual(self.world.pushes, [landed.REBASED_ON])
        self.assertEqual(retry.head(self.gh), landed.NEXT)
        self.assertEqual(self.gh.label_history, [(retry.ISSUE, retry.LABEL_VALIDATING)])
        self.assertEqual(retry.attempt(self.gh), retry.RETIRED)
        self.assertEqual(retry.said(self.gh), landed.SAID_FOUND_THEN_REBASED)
        notices = self.gh.posted_pr_comments
        self.assertIn(landed.ADVANCED_NOTICE, notices[0][1])
        durable = self.gh.pinned_data(retry.ISSUE)
        rebased = owed(landed.ANCHOR, landed.NEXT)
        self.assertEqual(durable.get(retry.KEY_REWRITE_DEBT), rebased)


    def test_a_taken_over_branch_says_nothing(self) -> None:
        # The fetch classified PR #42 and the checkout on the replay, and both
        # were moved onto somebody else's head together before the checkout
        # was read as the candidate. An attempt that recorded only its terms,
        # beside a transfer settled onto the replay, vouches for the replay
        # alone: nothing is said, routed, or retired for the head that took its
        # place, and the next tick classifies that head afresh -- as a landing
        # nothing this attempt vouches for, which parks.
        self._fresh(**{retry.KEY_REWRITE_SHA: None})
        self._carries(landed.a_verdict_settled_onto_the_replay)

        with world.races_the_reading(self, _taken_over):
            self._ticks()

        self._assert_held(standing=world.FOREIGN)
        self._ticks(world.FOREIGN)
        self._assert_held(parked=HELD_FOR_A_HUMAN, standing=world.FOREIGN)
        self.assertIn(UNPROVEN_FOREIGN, self.gh.posted_comments[-1][1])


class InterruptedFinishTest(landed.LandedCase):
    """A recovery's finish lost past its notice resumes into one route, said again only where nothing recorded it."""

    def test_each_window_resumes_into_one_route(self) -> None:
        for window, loses, mark, said in landed.WINDOWS:
            with self.subTest(window):
                self._fresh()
                with loses(self), self.assertRaises(RuntimeError):
                    self._ticks()
                durable = self.gh.pinned_data(retry.ISSUE)
                self.assertEqual(durable.get(landed.KEY_ANNOUNCED), mark)

                self._ticks()
                self._ticks()

                self._assert_finished(said)

    def test_an_announced_park_spends_its_reply(self) -> None:
        # An earlier finish announced the replay and its debt and was parked
        # before its route; the reply that releases the park brings the
        # recovery back to finish only the route, and the finish spends it.
        self._fresh(**{
            landed.KEY_ANNOUNCED: landed.REPLAY,
            retry.KEY_REWRITE_DEBT: owed(landed.ANCHOR, landed.REPLAY),
            retry.KEY_AWAITING_HUMAN: True,
            retry.KEY_PARK_REASON: retry.PARK_PUSH_FAILED,
        })
        reply = self._replies()

        self._ticks()

        self._assert_finished(retry.SAID_NOTHING)
        self.assertEqual(retry.parked(self.gh), (False, None))
        self.assertEqual(retry.watermark(self.gh), reply)


class RefusedLandingTest(landed.LandedCase):
    """A landing the pinned comment does not account for is parked where it stands, and said nothing about."""

    def test_another_publication_s_attempt_parks(self) -> None:
        self._fresh(**{landed.KEY_REWRITE_PR: base.PR_NUMBER + 1})

        self._ticks()

        self._assert_held(parked=(True, "auto_base_rebase_failed"))

    def test_an_unaccounted_landing_parks(self) -> None:
        # Each is named on the park the human is asked to reconcile.
        for described, state, records, uncommitted, why in UNACCOUNTED:
            with self.subTest(described):
                self._fresh(**state)
                self._carries(*records)
                _checkout_carries(self, *uncommitted)

                self._ticks()

                self._assert_held(parked=HELD_FOR_A_HUMAN)
                self.assertIn(why, self.gh.posted_comments[-1][1])

    def test_a_lost_transfer_report_is_made_once(self) -> None:
        # The settlement landed and the record the sinks are owed did not: it
        # is made from the proof the comment kept, which goes with it, and the
        # landing is finished once.
        self._carries(landed.a_verdict_settled_onto_the_replay)

        self._ticks()
        self._ticks()

        self._assert_finished()
        reported = [event for event in self.gh.recorded_events if event.get("event") == "late_transfer"]
        self.assertEqual(len(reported), 1)


if __name__ == "__main__":
    unittest.main()
