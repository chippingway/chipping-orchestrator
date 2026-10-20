# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence the configuration moved past is invalidated by the recovery, never held over or routed as current.

A recovery settled the landed head's captured run and died at its relabel,
behind its announcement. The configured command then moves: on its own, or
while the next recovery publishes a newer transaction another road recorded
for the same head -- which that move abandons, spending a revision past the
run. Either way the settled run answers for a configuration nobody runs any
more, so it is no last word the route may be held over, which would hold it
for good behind that revision: it is invalidated into history, whole, beside
the abandoned transaction and under the revision floor that transaction
raised, and the head is routed once to the fresh reviewer, who owes the
evidence. Nothing is announced again, nothing runs again, nothing is pushed,
and no developer is launched, however often the recovery polls.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import verification_record_state as _record_state
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheCall

_MOVED_COMMAND = "echo changed"


def _reconfigures(case: support.CapturedRunCase) -> None:
    """Configure another verification command for `case`."""
    case.configures(_MOVED_COMMAND)


def _records_newer(case: support.CapturedRunCase, captured):
    """Record a newer transaction for `captured`'s head, as another road would; that transaction."""
    state = case.gh.read_pinned_state(case.issue)
    newer = _record_state.mint_pending_evidence(state, git_support.ISSUE, captured.binding, captured.commands)
    case.assertTrue(_record_state.record_pending_evidence(state, newer))
    case.gh.write_pinned_state(case.issue, state)
    return newer


def _forgets_the_receipt(case: support.CapturedRunCase) -> None:
    """Blank the receipt on `case`'s attempt, as an attempt from before it existed carries none."""
    state = case.gh.read_pinned_state(case.issue)
    state.set(readings.KEY_EVIDENCE_RECEIPT, None)
    case.gh.write_pinned_state(case.issue, state)


# Whether the attempt carries the receipt its finish put on it, or none at all.
_ATTEMPTS = (("receipted", True), ("from before the receipt", False))


class StaleSettlementRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A settled run the configuration moved past is invalidated and the head routed, with nothing made again."""

    def test_an_abandoned_successor_routes(self) -> None:
        # The configuration moves as the newer transaction's artifact is
        # posted: that transaction is abandoned, and the settled run beside
        # it -- under the moved configuration too -- is invalidated rather
        # than held over the revision the newer one spent.
        head, captured = self._settles_and_dies()
        newer = _records_newer(self, captured)
        posts = _RacesPastTheCall(self.gh.publish_verification_artifact, 1, partial(_reconfigures, self))
        self.enterContext(patch.object(self.gh, support.POST, posts))

        self._polls()

        retired = ((captured.receipt, readings.INVALIDATED), (newer.receipt, readings.ABANDONED))
        self._assert_invalidated_and_routed(head, retired, newer.revision)
        self.assertEqual(self.posted(newer), [newer.commands])

    def test_a_settled_run_reconfigured_routes(self) -> None:
        # The configuration moves with nothing recorded beside the settled
        # run: it is invalidated, and the head routed with nothing run --
        # also for an attempt from before the receipt existed, whose settled
        # run says on its own that this landing captured one.
        for attempt, receipted in _ATTEMPTS:
            with self.subTest(attempt=attempt):
                self.setUp()
                head, captured = self._settles_and_dies()
                if not receipted:
                    _forgets_the_receipt(self)
                _reconfigures(self)

                self._polls()

                retired = ((captured.receipt, readings.INVALIDATED),)
                self._assert_invalidated_and_routed(head, retired, captured.revision)

    def _settles_and_dies(self) -> tuple:
        """Capture the run, then have a recovery settle and announce it and die at its relabel; head and run."""
        head, captured = self.captures()
        self.dies_at(support.RELABEL, self.recovers)
        self.assertEqual(readings.pinned_records(self)[1].receipt, captured.receipt)
        return head, captured

    def _polls(self) -> None:
        """Three whole recoveries, one after another."""
        self.recovers()
        self.recovers()
        self.recovers()

    def _assert_invalidated_and_routed(self, head: str, retired: tuple, floor: int) -> None:
        """Nothing pending or current, `retired` behind the evidence the rewrite moved past, the floor at `floor`.

        The head routed once, its attempt retired and announced once, with
        the command run once -- by the finish that captured the run -- and
        nothing pushed or launched.
        """
        history = (*git_support.invalidated(self), *retired)
        self.assertEqual(readings.pinned_records(self), (None, None, history))
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], floor)
        self.assert_recovered(head)
        self.assertEqual(self.runs(), 1)


if __name__ == "__main__":
    unittest.main()
