# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run's recovery over a checkout whose head could not be proved, held for another proof.

A checkout read on another head than the landed one is movement under the run
the evidence write captured, and abandons it. One whose head the proof could
not name -- read for the recovery's candidate, or again by the last word behind
the run's proof -- read nothing move: the recovery holds the route with the run
still recorded, and the next recovery, reading the checkout on the head, routes
that very run with its own transcript and tested and source provenance.
Nothing runs, pushes, or announces again, and no developer is launched.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.git.publication.probes import _BranchDivergence
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

_CHECKOUT_READ = "_reads_the_checkout"

# Which of a recovery's checkout readings proves no head, numbered in the order
# the recovery takes them: the one its candidate is read with, and the last
# word's, behind the captured run's proof.
_UNPROVED_READINGS = (("the candidate's", 1), ("the last word's", 2))


def _unproved_at(original, failing: int, calls: list, *args):
    """Answer `original`, except that reading number `failing` proves no head, as a failed head proof reads."""
    reading = original(*args)
    calls.append(reading)
    if len(calls) != failing:
        return reading
    return replace(reading, head="", tree="", base=_BranchDivergence())


class UnreadCheckoutRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A captured run is held over a checkout nobody could read, then routed as recorded with nothing run again."""

    def test_an_unread_checkout_holds_the_run(self) -> None:
        # Whichever reading fails, the route is held for the checkout that
        # could not be read, with the captured run still pending rather than
        # abandoned. Read on the head again, the run -- its transcript, and the
        # commit and source it was tested on -- is routed exactly as recorded.
        for reading, failing in _UNPROVED_READINGS:
            with self.subTest(reading=reading):
                head, captured = self._holds_over_an_unread_checkout(failing)

                self.recovers()

                self.assertEqual(
                    (readings.pinned_records(self), self.runs()),
                    ((captured, None, git_support.invalidated(self)), 1),
                )
                self.assert_recovered(head)

    def _holds_over_an_unread_checkout(self, failing: int) -> tuple:
        """A fresh case's captured run, recovered with checkout reading number `failing` proving no head.

        The head and the run, once that recovery held the route over the
        unread checkout with the run still pending.
        """
        self.setUp()
        head = self.lands_a_reviewed_rebase()
        self.dies_routing(partial(self.finishes, head))
        captured = readings.pinned_records(self)[0]
        unproved = partial(_unproved_at, getattr(rewrite_facts, _CHECKOUT_READ), failing, [])
        with (
            patch.object(rewrite_facts, _CHECKOUT_READ, side_effect=unproved),
            self.assertLogs("orchestrator.workflow", "WARNING") as logged,
        ):
            self.recovers()
            self.assertIn("could not be proved", str(logged.output))
        self.assert_held(captured)
        return head, captured


if __name__ == "__main__":
    unittest.main()
