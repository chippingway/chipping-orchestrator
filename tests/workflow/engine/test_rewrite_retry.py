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
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement import additions as _measurement
from tests.git.base_sync.candidate_reads_support import _checkout_carries
from tests.git.base_sync.gate_reads_support import _oversized_count
from tests.workflow.engine import (
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

# A ceiling the oversized count crosses.
CEILING = 5


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

    def test_an_oversized_replay_is_never_pushed(self) -> None:
        # An ordinary replay is measured like any other push onto an open pull
        # request: over the ceiling, the gate hands the issue to an
        # adjudication with the replay standing, and nothing is pushed,
        # announced, or routed to review.
        with patch.object(config, "MAX_ADDED_LINES", CEILING), patch.object(
            _measurement, "_count_added_lines", _oversized_count(),
        ):
            self._ticks()

        self.assertEqual(self.world.pushes, [])
        self.assertEqual(retry.head(self.gh), retry.ANCHOR)
        self.assertEqual(self.gh.label_history, [(retry.ISSUE, retry.LABEL_DECOMPOSING)])
        attempt = retry.attempt(self.gh)
        self.assertEqual(attempt[retry.KEY_PENDING_PUSH], retry.ANCHOR)
        self.assertEqual(attempt[retry.KEY_REWRITE_SHA], retry.REPLAY)
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

if __name__ == "__main__":
    unittest.main()
