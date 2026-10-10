# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The retry of a replay an interrupted tick never published, through the per-tick refresh and the workflow's recovery.

The recovery classifies the checkout against the remote its fetch verified,
the gate rules on the candidate before anything is pushed, the git owner
publishes exactly that candidate under the anchor's lease -- or refuses what
moved since it was read -- and a landing is handed to the one finish every
landing gets. Each case reads back what GitHub was left with: PR #42's head,
the label, the pinned record, the notices and events, the pushes made, and
what the next tick does.
"""
from __future__ import annotations

import unittest

from tests.git.base_sync.candidate_reads_support import _checkout_carries
from tests.workflow.engine import (
    rewrite_gate_holds_support as holds,
    rewrite_publication_moves as moves,
    rewrite_publication_test_support as world,
    rewrite_retry_test_support as retry,
)

# What moves after the gate measured the replay and before the git owner reads
# it again for its push, and where PR #42 is left standing.
MOVES = (
    ("work landing on the checkout", moves.lands_on_the_checkout, retry.ANCHOR),
    ("a base ref repointed", moves.REWOUND, retry.ANCHOR),
    ("somebody's push to the branch", moves.PUSHED_OVER, world.FOREIGN),
    ("a remote that stops answering", moves.silences_the_remote, retry.ANCHOR),
)


class RetriedReplayTest(retry.RetryCase):
    """A replay the record names, over a remote still on the anchor, published once and finished once."""

    def test_the_replay_is_pushed_once_and_finished(self) -> None:
        self.retry_ticks_twice()

        self.assertEqual(self.world.pushes, [retry.RETRIED])
        self._assert_finished()

    def test_a_lost_answer_is_not_pushed_again(self) -> None:
        # The push reached the remote and git answered a failure: read again,
        # the remote stands on the replay, so the landing is finished as the
        # push this tick made rather than rolled back off a branch carrying it.
        self.world.answered = False

        self.retry_ticks_twice()

        self.assertEqual(self.world.pushes, [retry.RETRIED])
        self._assert_finished()

    def retry_ticks_twice(self) -> None:
        """The tick that retries, and the one after it, which has no anchor left to answer."""
        self._ticks()
        self._ticks()


class RefusedRetryTest(retry.RetryCase):
    """A replay the git owner will not publish, and one the gate will not let through."""

    def test_what_moved_since_the_gate_is_refused(self) -> None:
        # Nothing is sent over a checkout, a base, or a remote that moved after
        # the measurement, nor over a remote nobody can read: the checkout goes
        # back onto its anchor and the issue parks for a human.
        for moved, move, left_on in MOVES:
            with self.subTest(moved):
                self._fresh()

                with world.races_the_reread(self, move):
                    self._ticks()

                self.assertEqual(self.world.pushes, [])
                self._assert_rolled_back(left_on)

    def test_a_dirty_checkout_is_reset_and_cleaned(self) -> None:
        # The leftovers would ride the push, so the checkout is put back onto
        # its anchor and cleaned before anything is measured or sent.
        _checkout_carries(self, "scratch.py")

        self._ticks()

        self.assertEqual(self.world.pushes, [])
        self._assert_rolled_back(retry.ANCHOR, retry.PARK_DIRTY)
        self.assertTrue(self.git.ran(retry.CLEAN))

    def test_only_an_adjudication_takes_the_attempt(self) -> None:
        # An ordinary replay is measured like any other push onto an open pull
        # request: past the ceiling, the gate hands the issue to an
        # adjudication with the replay standing and unreset, nothing is pushed,
        # announced, or routed to review, and the attempt goes to the live
        # generation with it. A count nobody can pin parks instead, so the
        # retried attempt stays pinned for the reply that brings it back.
        for count, relabelled, left, parked in holds.HOLDS:
            with self.subTest(count.__name__):
                self._fresh()

                with count():
                    self._ticks()

                self.assertEqual(self.world.pushes, [])
                self.assertEqual(self.gh.label_history, list(relabelled))
                self.assertEqual(holds.left_with(self.gh), left)
                self.assertEqual(retry.parked(self.gh), parked)
                self.assertFalse(self.git.ran(retry.RESET_ONTO_THE_ANCHOR))
                self.assertEqual(retry.said(self.gh), retry.SAID_NOTHING)

    def test_a_refused_reset_keeps_the_attempt(self) -> None:
        # The lease is rejected and the reset that would undo the replay is
        # refused, so the branch may still be standing on it: the anchor and
        # the record naming the replay are kept, and the issue parks.
        self._rejected_under_a_refused_reset()

        self.assertEqual(self.world.pushes, [retry.RETRIED])
        self.assertEqual(retry.head(self.gh), retry.ANCHOR)
        self.assertEqual(retry.parked(self.gh), (True, retry.PARK_PUSH_FAILED))
        attempt = retry.attempt(self.gh)
        self.assertEqual(attempt[retry.KEY_PENDING_PUSH], retry.ANCHOR)
        self.assertEqual(attempt[retry.KEY_REWRITE_SHA], retry.REPLAY)
        self.assertEqual(retry.said(self.gh), retry.SAID_NOTHING)

    def test_a_reply_retries_the_kept_attempt(self) -> None:
        # Nothing moves until a human replies. The reply brings the recovery
        # back, the same replay is pushed again under the same lease, and the
        # finish spends the reply along with the park it answered.
        self._rejected_under_a_refused_reset()
        self._ticks()
        self.assertEqual(self.world.pushes, [retry.RETRIED])

        self._repaired()
        reply = self._replies()
        self._ticks()

        self.assertEqual(self.world.pushes, [retry.RETRIED, retry.RETRIED])
        self._assert_finished()
        spent = (retry.parked(self.gh), retry.watermark(self.gh))
        self.assertEqual(spent, ((False, None), reply))

    def _rejected_under_a_refused_reset(self) -> None:
        """Run the retry against a lease the remote rejects, and a reset git refuses."""
        self.world.rejects = True
        self.git.refuses_reset = True
        self._ticks()

    def _repaired(self) -> None:
        """The remote takes the lease again, and git resets."""
        self.world.rejects = False
        self.git.refuses_reset = False


class HandedOverReplyTest(retry.RetryCase):
    """The reply that brought a parked attempt back, where the gate hands its replay to an adjudication."""

    def test_the_gate_spends_only_a_retry(self) -> None:
        # A reply that only asked for the retry is the attempt's, recorded read
        # in the gate's own write -- the one that takes its park down -- so no
        # crash leaves it waiting for the adjudication as guidance. A reply
        # that says more is left unread, for the adjudication to hand on.
        for body, spent in holds.REPLIES:
            with self.subTest(body):
                self._fresh(awaiting_human=True, park_reason=retry.PARK_PUSH_FAILED)
                holds.covers_the_thread(self.gh)
                reply = holds.replies(self, body)
                before = holds.read_through(self.gh)

                with holds.oversized():
                    self._ticks()

                read = (reply, holds.baseline_through(self.gh, reply)) if spent else before
                self.assertEqual(holds.left_with(self.gh), (None, None, retry.REPLAY))
                self.assertEqual(holds.read_through(self.gh), read)


if __name__ == "__main__":
    unittest.main()
