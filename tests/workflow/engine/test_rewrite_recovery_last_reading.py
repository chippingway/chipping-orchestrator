# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What another road writes right behind a dormant recovery's last proof, retirement, or record, kept on its state.

The guarded recovery case (`guarded_recovery_support`): issue #7's run settled and its finish killed before its
announcement, the recovery context read off the comment handed straight to the dormant reset record
(`rewrite_recovery_parks.records_the_reset`), the proof before a park, or the hold. Another road writes right as the
record's proof of the run's moved report answers -- a newer run recorded pending on the run's binding, or the revision
floor raised alone -- right as its retirement over a checkout gone answers, a usage total added to, or right behind a
hold's record with nothing left to prove, a fresh attempt pinned or a usage total added to. The comment read last is
laid over the tick's state (`rewrite_recovery_rereads.lays_what_moved`), so that state written whole behind puts none
of it back, and the pending successor holds the reset, the fresh attempt the hold. On a state alone, what the tick
staged itself is kept over another road's move of it. Nothing is run again, pushed, or launched.
"""
from __future__ import annotations

import json
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_parks as _parks,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_recovery_rereads import lays_what_moved
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_evidence_test_support as fixtures,
    rewrite_finish_git_support as git_support,
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

# What a write behind a hold's record is measured on: the usage total, the attempt's anchor, and the gate's record.
_HELD = (_USAGE, readings.KEY_PENDING_PUSH, _GATE)

# Right behind the reset record's proof answering, behind its retirement over a checkout gone answering, and behind
# the hold's record, the first edit carrying the gate's record.
_BEHIND_THE_PROOF = handoff.Boundary("behind the reset proof", "retires_unproved", lambda *_called, **_options: True)
_BEHIND_THE_RETIREMENT = handoff.Boundary(
    "behind the retirement", "lands_the_retirement", lambda *_called, **_options: True,
)
_BEHIND_THE_HOLD = handoff.Boundary(
    "behind the hold's record", "edit_pinned_state", lambda _issue, staged, **_options: staged.get(_GATE) is not None,
)

# The comment read afresh behind a hold's record, and the first reading a proof before a park takes.
_AT_THE_REREAD = handoff.Boundary("at the reread behind the record", "durable_comment", lambda *_called: True)
_AT_THE_FIRST_READ = handoff.Boundary("at the proof's first reading", "read_pinned_state", lambda *_called: True)


def _adds(case, field: str, more: int) -> None:
    """Add `more` to the counter `case`'s comment carries under `field`, as another road would."""
    state = case.gh.read_pinned_state(case.issue)
    state.set(field, (state.get(field) or 0) + more)
    case.gh.write_pinned_state(case.issue, state)


def _writes(case, fields: dict) -> None:
    """Write each of `fields` over `case`'s comment as it stands, as another road would."""
    state = case.gh.read_pinned_state(case.issue)
    for field, written in fields.items():
        state.set(field, written)
    case.gh.write_pinned_state(case.issue, state)


def _holds_retired(case) -> tuple:
    """Settle `case`'s run, kill its finish, and retire it as another road would, then stage the gate's record on a
    context read off the comment; the head, the run, and that context."""
    head, run = case.settles_then_dies()
    state = case.gh.read_pinned_state(case.issue)
    case.assertTrue(_settlement.retire_current_evidence(state))
    case.gh.write_pinned_state(case.issue, state)
    context = guarded.recovery_context(case)
    context.state.set(_GATE, head)
    return head, run, context


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

    def test_a_write_behind_a_hold_record(self) -> None:
        # The run already retired, the hold has nothing left to prove; right behind its record another road pins a
        # fresh attempt, or adds 2 of usage. The hold reads the comment afresh behind its record and lays what moved
        # over the tick's state: the fresh attempt holds the caller, the tick's state withheld, so writing it whole puts
        # nothing back over that attempt; the usage lets the hold go on, and writing the state whole keeps it.
        for replaces in (True, False):
            with self.subTest(replaces=replaces):
                self.setUp()
                context, behind = self._holds_over_nothing(replaces=replaces)
                holds = _BEHIND_THE_HOLD.moving(self.gh.edit_pinned_state, behind)
                with patch.object(self.gh, _BEHIND_THE_HOLD.step, holds):
                    self.assertEqual(_parks.lands_a_hold(context), not replaces)
                self.assertEqual(context.state.withheld, replaces)
                written = self.pinned_fields(*_HELD)
                self.gh.write_pinned_state(self.issue, context.state)
                self.assertEqual(self.pinned_fields(*_HELD), written)

    def _holds_over_nothing(self, *, replaces: bool) -> tuple:
        """Settle the run, kill its finish, and retire it as another road would, then stage the gate's record on a
        context read off the comment; that context, and the write another road makes behind the hold's record -- a
        fresh attempt pinned where `replaces`, 2 of usage added otherwise."""
        head, _run, context = _holds_retired(self)
        if replaces:
            return context, partial(self._replaces_the_attempt, head)
        return context, partial(_adds, self, _USAGE, 2)

    def _replaces_the_attempt(self, head: str) -> None:
        """Clear the attempt and pin a fresh one on `head` in its place, as another road would."""
        state = self.gh.read_pinned_state(self.issue)
        _attempts._clears_the_attempt(state)
        pinned = fixtures.attempt_record(head, head, git_support.PR_NUMBER, git_support.REVIEWING, head)
        for field, pinned_value in pinned.items():
            state.set(field, pinned_value)
        self.gh.write_pinned_state(self.issue, state)

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


class RereadHoldTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """What a hold's or a proof's readings show holds or proves, however soon another road puts back what they read."""

    def test_movement_behind_the_record_is_retired(self) -> None:
        # The run settled current, the comment read afresh behind the hold's record has the run's report moved, put
        # back right behind that reading: the hold proves the run again with that movement before it answers, so it is
        # invalidated whole, and the next proof, over the report put back, keeps nothing current.
        head, run = self.settles_then_dies()
        context = guarded.recovery_context(self)
        context.state.set(_GATE, head)
        report = self.pinned_fields(_REPORT)[0]
        rereads = _AT_THE_REREAD.racing(
            _parks.durable_comment,
            partial(_writes, self, {_REPORT: {**report, _REVISION: report[_REVISION] + 1}}),
            partial(_writes, self, {_REPORT: report}),
        )
        with patch.object(_parks, _AT_THE_REREAD.step, rereads):
            self.assertTrue(_parks.lands_a_hold(context))
        self.assertTrue(self.proves())
        self.assert_invalidated(run)

    def test_a_successor_the_record_took_in_holds(self) -> None:
        # The run already retired, another road records a newer run pending on its binding after the tick read the
        # comment, under a receipt the attempt does not name, and the hold's record takes it in as it lands: the
        # comment read afresh behind the record carries a successor the tick never held, so the hold holds, the tick's
        # state withheld, and that successor stands pending with the floor it raised.
        run, context = _holds_retired(self)[1:]
        newer = settled.records_a_newer_run(self, binding=run.binding)
        self.assertFalse(_parks.lands_a_hold(context))
        self.assertTrue(context.state.withheld)
        self.assertEqual(readings.pinned_records(self)[0], newer)
        self.assertEqual(self.pinned_fields(readings.KEY_REVISION_FLOOR), (newer.revision,))

    def test_a_replacement_in_the_proof_holds(self) -> None:
        # Another road pins the landed head as a fresh anchor as the proof before a park first reads the comment, and
        # puts the attempt back right behind that reading: the proof read another attempt in place of the one it
        # recovers, so it holds, the tick's state withheld, however that attempt stands again by its last reading.
        head = self.settles_then_dies()[0]
        context = guarded.recovery_context(self)
        standing = self.pinned_fields(readings.KEY_PENDING_PUSH)[0]
        reads = _AT_THE_FIRST_READ.racing(
            self.gh.read_pinned_state,
            partial(_writes, self, {readings.KEY_PENDING_PUSH: head}),
            partial(_writes, self, {readings.KEY_PENDING_PUSH: standing}),
        )
        with patch.object(self.gh, _AT_THE_FIRST_READ.step, reads):
            self.assertFalse(_parks.proves_before_a_park(context))
        self.assertTrue(context.state.withheld)
        self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (standing,))


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
