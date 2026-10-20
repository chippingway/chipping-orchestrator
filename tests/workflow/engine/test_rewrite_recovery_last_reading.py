# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What another road writes right behind the dormant reset record's last proof or retirement, kept on the tick's state.

The guarded recovery case (`guarded_recovery_support`): issue #7's run settled and its finish killed before its
announcement, the recovery context read off the comment handed straight to the dormant reset record
(`rewrite_recovery_parks.records_the_reset`) or to the proof before a park. Another road writes right as the record's
proof of the run's moved report answers -- a newer run recorded pending on the run's binding, or the revision floor
raised alone -- or right as its retirement over a checkout gone answers, a usage total added to. The comment the record
reads last is laid over the tick's state (`rewrite_recovery_rereads.lays_what_moved`), so that state written whole
behind puts none of it back, and the pending successor holds the reset. On a state alone, what the tick staged itself
is kept over another road's move of it. Nothing is run again, pushed, or launched.
"""
from __future__ import annotations

import json
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_parks as _parks,
)
from orchestrator.workflow.engine.rewrite_recovery_rereads import lays_what_moved
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
)

# The run's report record and the revision another road moves it to; the record a newer run stands pending in; the
# usage total the tick and another road add to; and where the checkout goes.
_REPORT = "developer_report_current"
_REVISION = "revision"
_PENDING = "verification_evidence_pending"
_USAGE = "issue_total_tokens"
_AWAY = "checkout-away"

# A record the gate stages on the tick's state, which another road spells its own way.
_GATE = "late_gate_hold"

# What another road's write is measured on behind the record: the revision floor, and the pending record beside it.
_FLOOR_AND_PENDING = (readings.KEY_REVISION_FLOOR, _PENDING)

# Right behind the reset record's proof answering, and behind its retirement over a checkout gone answering.
_BEHIND_THE_PROOF = handoff.Boundary("behind the reset proof", "retires_unproved", lambda *_called, **_options: True)
_BEHIND_THE_RETIREMENT = handoff.Boundary(
    "behind the retirement", "lands_the_retirement", lambda *_called, **_options: True,
)


def _adds(case, field: str, more: int) -> None:
    """Add `more` to the counter `case`'s comment carries under `field`, as another road would."""
    state = case.gh.read_pinned_state(case.issue)
    state.set(field, (state.get(field) or 0) + more)
    case.gh.write_pinned_state(case.issue, state)


class LastReadingTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """What the reset record reads last is laid over the tick's state, a pending successor holding the reset."""

    def test_a_write_behind_the_reset_proof_is_kept(self) -> None:
        # The record reads the run's report moved and its proof retires the run; right as that proof answers another
        # road records a newer run pending on the run's binding, or raises the revision floor alone. The record reads
        # it last and lays it over the tick's state, so that state written whole behind keeps the floor and the
        # successor, which -- under a receipt the attempt does not name -- holds the reset, the tick's state withheld.
        for pends in (True, False):
            with self.subTest(pending=pends):
                self.setUp()
                context, behind = self._moves_the_report(pends=pends)
                proof = _BEHIND_THE_PROOF.moving(_retirement.retires_unproved, behind)
                with patch.object(_retirement, "retires_unproved", proof):
                    self.assertEqual(_parks.records_the_reset(context), not pends)
                self.assertEqual(context.state.withheld, pends)
                written = self.pinned_fields(*_FLOOR_AND_PENDING)
                self.gh.write_pinned_state(self.issue, context.state)
                self.assertEqual(self.pinned_fields(*_FLOOR_AND_PENDING), written)

    def test_usage_behind_a_lost_checkout_is_kept(self) -> None:
        # The tick stages 5 of usage over a checkout gone, landed in a write of its own ahead of the retirement; right
        # as that retirement answers another road adds 2 and the checkout is put back. The proof goes on, the record
        # having laid that total over the tick's state, so the state written whole behind keeps both.
        self.settles_then_dies()
        context = guarded.recovery_context(self)
        counted = context.state.get(_USAGE) or 0
        context.state.set(_USAGE, counted + 5)
        self._wt.rename(self._wt.parent / _AWAY)
        retires = _BEHIND_THE_RETIREMENT.moving(_parks.lands_the_retirement, self._adds_and_returns)
        with patch.object(_parks, "lands_the_retirement", retires):
            self.assertTrue(_parks.proves_before_a_park(context))
        self.gh.write_pinned_state(self.issue, context.state)
        self.assertEqual(self.pinned_fields(_USAGE), (counted + 7,))

    def _moves_the_report(self, *, pends: bool) -> tuple:
        """Settle the run and kill its finish, read the recovery context off the comment, and move the run's report as
        another road would; that context, and the write another road makes behind the reset proof -- a newer run
        recorded pending on the run's binding where `pends`, the revision floor raised alone otherwise."""
        run = self.settles_then_dies()[1]
        context = guarded.recovery_context(self)
        report = self.pinned_fields(_REPORT)[0]
        state = self.gh.read_pinned_state(self.issue)
        state.set(_REPORT, {**report, _REVISION: report[_REVISION] + 1})
        self.gh.write_pinned_state(self.issue, state)
        if pends:
            return context, partial(settled.records_a_newer_run, self, binding=run.binding)
        return context, partial(_adds, self, readings.KEY_REVISION_FLOOR, 1)

    def _adds_and_returns(self) -> None:
        """Add 2 to the usage the comment carries, as another road would, and put the checkout back."""
        _adds(self, _USAGE, 2)
        (self._wt.parent / _AWAY).rename(self._wt)


class LaysWhatMovedTest(unittest.TestCase):
    """On a state alone: another road's moves laid over it, the tick's own staging kept."""

    def test_the_ticks_staging_is_kept(self) -> None:
        # Another road adds to the usage, raises the floor, and spells the gate's record its own way: the usage and the
        # floor are laid over the state and taken in as read, the gate's record the tick staged is kept for the write
        # behind to refuse as the conflict it is, and only a move of a field held holds the caller.
        moved = {_USAGE: 7, _GATE: "another road's", readings.KEY_REVISION_FLOOR: 3}
        for held in ((), (readings.KEY_REVISION_FLOOR,)):
            with self.subTest(held=held):
                state = PinnedState(comment_id=1, state_data={_USAGE: 5, _GATE: None}, parsed=True)
                _commit.takes_in(state, dict(state.data))
                state.set(_GATE, "the tick's")
                reading = PinnedState(comment_id=1, state_data=moved, parsed=True)
                self.assertEqual(lays_what_moved(state, reading, held), bool(held))
                self.assertEqual(state.data, {**moved, _GATE: "the tick's"})
                self.assertEqual(json.loads(state.synced), {**moved, _GATE: None})


if __name__ == "__main__":
    unittest.main()
