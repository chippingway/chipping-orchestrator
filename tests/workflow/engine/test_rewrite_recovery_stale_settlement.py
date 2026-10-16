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

The evidence phase of a finish held to the dormant settled-evidence policy,
asked directly (`settled_finish_support`), invalidates the run the same way
before the head is decided afresh; where that invalidation cannot land -- the
comment full -- it holds instead, the movement recorded by blanking the
attempt's base tip, rather than taking the run as current; and where another
road records a newer transaction right behind that invalidation, the phase
reads it afresh and holds over it rather than deciding the head again.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    rewrite_finish_readiness as _readiness,
    rewrite_finish_settlement as _settlement_step,
    verification_record_state as _record_state,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
)
from tests.workflow.interleaving import _RacesPastTheCall, _RacesPastTheStep

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


def _with_its_answer(finish):
    """`finish`, beside what its evidence phase answers (`rewrite_finish_settlement.resolves`)."""
    return finish, _settlement_step.resolves(finish)


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


class SettledStaleSettlementTest(settled.SettledRunCase, unittest.TestCase):
    """The dormant evidence phase invalidates a run the configuration moved past, or holds where that cannot land."""

    def test_a_reconfigured_run_is_invalidated(self) -> None:
        # A recovery settled and announced the run and died at its relabel,
        # and the configuration then moves: the phase invalidates the run
        # whole with nothing run again, and lets the route go on -- or, the
        # comment full, holds with the run current and its base tip blanked.
        for full, answer in ((False, None), (True, FinishOutcome.HELD)):
            with self.subTest(full=full):
                self.setUp()
                head, captured = self.captures()
                self.dies_at(support.RELABEL, self.recovers)
                settled.charges(self)
                _reconfigures(self)
                if full:
                    finish_moves.fills_the_comment(self)

                self.assertEqual(self.resolves(head), answer)

                self.assert_phase_left(head)
                self._assert_retired(captured, full)

    def test_a_successor_behind_it_holds(self) -> None:
        # As above, but right behind the write invalidating the run, before
        # it returns, another road records a newer transaction of the head:
        # the phase reads the comment afresh behind that write and holds, the
        # run invalidated whole and the successor owed as recorded -- in the
        # finish's state too -- rather than deciding the head afresh over it.
        head, captured = self.captures()
        self.dies_at(support.RELABEL, self.recovers)
        settled.charges(self)
        _reconfigures(self)

        finish = self._holds_over_a_successor(head, captured)

        self.assert_phase_left(head)
        self._assert_owed_beside(captured, finish)

    def _holds_over_a_successor(self, head: str, captured):
        """The phase over `head`'s finish, HELD over a successor recorded right behind its invalidation; the finish."""
        arrives = _RacesPastTheStep(_readiness.invalidates, partial(_records_newer, self, captured))
        with patch.object(_readiness, "invalidates", arrives):
            finish, answer = self.asks_dormant(_with_its_answer, head)
        self.assertEqual(answer, FinishOutcome.HELD)
        return finish

    def _assert_owed_beside(self, captured, finish) -> None:
        """`captured` invalidated whole, nothing current, and the successor pending -- in `finish`'s state too."""
        pending, current, history = readings.pinned_records(self)
        self.assertIsNone(current)
        self.assertEqual(history[-1], (captured.receipt, readings.INVALIDATED))
        self.assertIsNotNone(pending)
        self.assertEqual(_record_state.read_pending_evidence(finish.state), pending)

    def _assert_retired(self, captured, full: bool) -> None:
        """`captured` current beside a blanked base tip where `full`, invalidated whole otherwise."""
        pending, current, history = readings.pinned_records(self)
        self.assertIsNone(pending)
        if full:
            self.assertEqual(current.receipt, captured.receipt)
            self.assertIsNone(readings.pinned(self)[readings.KEY_REWRITE_BASE])
            return
        self.assertIsNone(current)
        self.assertEqual(history[-1], (captured.receipt, readings.INVALIDATED))


if __name__ == "__main__":
    unittest.main()
