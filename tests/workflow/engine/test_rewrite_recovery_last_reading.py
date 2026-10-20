# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What another road writes right behind a dormant recovery's last proof, retirement, or record, kept on its state.

The guarded recovery case (`guarded_recovery_support`): issue #7's run settled and its finish killed unannounced, the
context read off the comment handed straight to the dormant reset record, proof before a park, hold, or park. Whatever
another road writes behind them -- a successor, a floor, usage, a fresh attempt, the run put back, the report moved and
put back, a checkout lost or read absent -- is laid over the tick's state (`rewrite_recovery_rereads`), retired, or
outranked, or holds the caller with its state withheld; on a state alone, what the tick staged is kept. Nothing is run
again, pushed, or launched.
"""
from __future__ import annotations

import json
import unittest
from contextlib import ExitStack
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.git.base_sync import attempts as _attempts, rewrite_facts as _rewrite_facts, snapshot as _snapshot
from orchestrator.github.pinned_state import PinnedEdit, PinnedState
from orchestrator.workflow.engine import (
    owed_events as _owed_events,
    pinned_commit as _commit,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_parks as _parks,
    verification_proof as _proof,
    verification_settlement_state as _settlement,
    verification_world as _world,
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
_CURRENT = "verification_evidence_current"
_USAGE = "issue_total_tokens"
_AWAY = "checkout-away"

# A record the gate stages on the tick's state, which another road spells its own way.
_GATE = "late_gate_hold"

# What another road's write is measured on behind the record: the revision floor, and the pending record beside it.
_FLOOR_AND_PENDING = (readings.KEY_REVISION_FLOOR, _PENDING)

# What a write behind a hold's record is measured on: the usage total, the attempt's anchor, and the gate's record.
_HELD = (_USAGE, readings.KEY_PENDING_PUSH, _GATE)

# Right behind the reset record's proof answering, and behind its retirement over a checkout gone answering; and the
# first edit carrying the gate's record -- a hold's record, or a reset's blank sent with it.
_BEHIND_THE_PROOF = handoff.Boundary("behind the reset proof", "retires_unproved", lambda *_called, **_options: True)
_BEHIND_THE_RETIREMENT = handoff.Boundary(
    "behind the retirement", "lands_the_retirement", lambda *_called, **_options: True,
)
_THE_GATED_RECORD = handoff.Boundary(
    "at the gate's record", "edit_pinned_state", lambda _issue, staged, **_options: staged.get(_GATE) is not None,
)

# The park's record that releases the attempt, the first edit carrying no anchor.
_BEHIND_THE_RELEASE = handoff.Boundary(
    "behind the releasing park's record", "edit_pinned_state",
    lambda _issue, staged, **_options: not staged.get(readings.KEY_PENDING_PUSH),
)

# How another road races the reading behind a hold's record: the report moved, beside a newer run, or the run restored.
_MOVED, _SUCCEEDED, _RESTORED = "moved", "succeeded", "restored"

# The comment read afresh behind a hold's record, and the first reading a proof before a park takes.
_AT_THE_REREAD = handoff.Boundary("at the reread behind the record", "durable_comment", lambda *_called: True)
_AT_THE_FIRST_READ = handoff.Boundary("at the proof's first reading", "read_pinned_state", lambda *_called: True)

# The readiness proof's word on the checkout the evidence names.
_AT_THE_WORLD = handoff.Boundary("at the readiness proof's world", "world_verdict", lambda *_called: True)


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


def _gated(case, *, retired: bool = True) -> tuple:
    """Settle `case`'s run, kill its finish, and retire it as another road would where `retired`, then stage the gate's
    record on a context read off the comment; the head, the run, and that context."""
    head, run = case.settles_then_dies()
    state = case.gh.read_pinned_state(case.issue)
    case.assertTrue(not retired or _settlement.retire_current_evidence(state))
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
                holds = _THE_GATED_RECORD.moving(self.gh.edit_pinned_state, behind)
                with patch.object(self.gh, _THE_GATED_RECORD.step, holds):
                    self.assertEqual(_parks.lands_a_hold(context), not replaces)
                self.assertEqual(context.state.withheld, replaces)
                written = self.pinned_fields(*_HELD)
                self.gh.write_pinned_state(self.issue, context.state)
                self.assertEqual(self.pinned_fields(*_HELD), written)

    def _holds_over_nothing(self, *, replaces: bool) -> tuple:
        """Settle the run, kill its finish, and retire it as another road would, then stage the gate's record on a
        context read off the comment; that context, and the write another road makes behind the hold's record -- a
        fresh attempt pinned where `replaces`, 2 of usage added otherwise."""
        head, _run, context = _gated(self)
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
        # back right behind -- beside a newer run settled on the run's binding there, or, the hold's own proof having
        # retired the run over that move, the run and report written back instead. The hold proves that reading again,
        # a successor on its own binding, a run its history retired as moved: the next proof keeps nothing current.
        for mode in (_MOVED, _SUCCEEDED, _RESTORED):
            with self.subTest(mode=mode):
                self.setUp()
                run, context = _gated(self, retired=False)[1:]
                with patch.object(_parks, _AT_THE_REREAD.step, self._rereads(mode, run)):
                    self.assertTrue(_parks.lands_a_hold(context))
                self.assertTrue(self.proves())
                self.assertIsNone(readings.pinned_records(self)[1])
                if mode != _SUCCEEDED:
                    self.assert_invalidated(run)

    def test_a_successor_the_record_took_in_holds(self) -> None:
        # The run already retired, another road records a newer run pending on its binding after the tick read the
        # comment, under a receipt the attempt does not name, and the hold's record takes it in as it lands: the
        # comment read afresh behind the record carries a successor the tick never held, so the hold holds, the tick's
        # state withheld, and that successor stands pending with the floor it raised.
        run, context = _gated(self)[1:]
        newer = settled.records_a_newer_run(self, binding=run.binding)
        self.assertFalse(_parks.lands_a_hold(context))
        self.assertTrue(context.state.withheld)
        self.assertEqual(readings.pinned_records(self)[0], newer)
        self.assertEqual(self.pinned_fields(readings.KEY_REVISION_FLOOR), (newer.revision,))

    def test_a_run_put_back_behind_a_releasing_park(self) -> None:
        # The git owner's abort resets the checkout and parks, the park's record releasing the attempt and retiring the
        # run beside it; right behind that record another road writes the run back and puts the checkout back on the
        # head. The park's own write spent a revision past the run, so with no attempt left to guard it the run stands
        # outranked, and the readiness proof of the comment as it stands refuses it.
        head, run = self.settles_then_dies()
        releases = _BEHIND_THE_RELEASE.moving(
            self.gh.edit_pinned_state, partial(self._puts_the_run_back, self.pinned_fields(_CURRENT)[0], head),
        )
        with patch.object(self.gh, _BEHIND_THE_RELEASE.step, releases):
            _snapshot._abort_recovery_unverified(guarded.recovery_context(self), "fetch failed")
        fresh = self.gh.read_pinned_state(self.issue)
        self.assertIsNone(fresh.get(readings.KEY_PENDING_PUSH))
        self.assertEqual(readings.pinned_records(self)[1], run)
        reading = _proof.ProofReading(self.gh, self._spec, self.issue, fresh)
        self.assertFalse(_proof.current_evidence_verdict(reading).proved)

    def test_a_false_answer_stays_withheld(self) -> None:
        # The reset's blank, over the run's report moved, or the hold's record, the report moving as it goes out, is
        # sent with its answer lost; the proof behind retires the run only past two unread edits, another road adding
        # 2 of usage right behind it. Or, over the report moved, the blank lands, or the hold's proof goes first, and
        # the run is retired at once, the comment unreadable right behind that usage. The caller answers False, its
        # state withheld still, so no write of it puts that usage back.
        for asks, lost in product((_parks.records_the_reset, _parks.lands_a_hold), (True, False)):
            with self.subTest(asks=asks.__name__, lost=lost):
                self.setUp()
                context = _gated(self, retired=False)[2]
                report = self.pinned_fields(_REPORT)[0]
                self._moved = {_REPORT: {**report, _REVISION: report[_REVISION] + 1}}
                self._losing = lost
                self._unread = 2 if lost else 0
                self._unreadable = set() if lost else {self.issue.number}
                if asks is _parks.records_the_reset or not lost:
                    _writes(self, self._moved)
                with patch.object(self.gh, "edit_pinned_state", partial(self._loses, self.gh.edit_pinned_state)):
                    self.assertFalse(asks(context))
                self.gh.pinned_failures.unreadable.clear()
                self.assertTrue(context.state.withheld)
                self.assertEqual(self.pinned_fields(_USAGE), (2,))

    def _rereads(self, mode: str, run):
        """The reading behind the hold's record, raced as `mode` says: the report moved and put back behind, beside a
        newer run settled on `run`'s binding; or that report moved ahead of the hold, the run and report put back."""
        written = self.pinned_fields(_REPORT, _CURRENT)
        moved = {**written[0], _REVISION: written[0][_REVISION] + 1}
        ahead = partial(_writes, self, {_REPORT: moved})
        live = _parks.durable_comment
        if mode == _RESTORED:
            ahead = partial(_writes, self, dict(zip((_REPORT, _CURRENT), written)))
            _writes(self, {_REPORT: moved})
        if mode == _SUCCEEDED:
            newer = partial(settled.records_a_newer_run, self, settles=True, binding=run.binding)
            live = _AT_THE_REREAD.racing(live, newer, partial(_writes, self, {}))
        return _AT_THE_REREAD.racing(
            live, ahead, partial(_writes, self, {_REPORT: written[0]}),
        )

    def _loses(self, live, issue, staged, **options):
        """`live`, the strict edit: the first carrying the gate's record lost unsent, the report moved right then; the
        first two retiring the run left unread, where lost; 2 of usage added right behind the next, the comment left
        unreadable behind that where nothing was lost."""
        retires = options["over"].get(_CURRENT) and not staged.get(_CURRENT)
        if self._losing and staged.get(_GATE):
            self._losing = False
            _writes(self, self._moved)
            return PinnedEdit.UNCONFIRMED
        if retires and self._unread:
            self._unread -= 1
            return PinnedEdit.UNREAD
        answered = live(issue, staged, **options)
        if retires and self._unread == 0:
            self._unread = -1
            _adds(self, _USAGE, 2)
            self.gh.pinned_failures.unreadable.update(self._unreadable)
        return answered

    def _puts_the_run_back(self, record: dict, head: str) -> None:
        """Write `record` back as the current one, as another road would, and put the checkout back on `head`."""
        _writes(self, {_CURRENT: record})
        self._git("reset", "--quiet", "--hard", head, cwd=self._wt)


class LossInTheProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """Another attempt, or a checkout gone or read absent, in the proof, however soon it is back: held, or owed."""

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

    def test_a_replacement_then_a_loss_holds(self) -> None:
        # Another road pins the landed head as a fresh anchor as the proof first reads the comment, and puts the
        # attempt back right behind that reading; the checkout then goes under the proof's next reading of it, back
        # right behind. The loss is recorded first, owed by the attempt, and the attempt the proof read in place of its
        # own still holds it, the tick's state withheld.
        head = self.settles_then_dies()[0]
        context = guarded.recovery_context(self)
        self._standing = self.pinned_fields(readings.KEY_PENDING_PUSH)[0]
        self._armed = False
        reads = _AT_THE_FIRST_READ.racing(
            self.gh.read_pinned_state, partial(_writes, self, {readings.KEY_PENDING_PUSH: head}), self._arms,
        )
        checkout = partial(self._loses_once_armed, _rewrite_facts._reads_the_checkout)
        with (
            patch.object(self.gh, _AT_THE_FIRST_READ.step, reads),
            patch.object(_rewrite_facts, "_reads_the_checkout", checkout),
        ):
            self.assertFalse(_parks.proves_before_a_park(context))
        self.assertTrue(context.state.withheld)
        self.assertTrue(_owed_events.loss_owed(context))
        self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (self._standing,))

    def test_a_checkout_read_absent_stays_owed(self) -> None:
        # The readiness proof finds the checkout gone from this host, put back right behind that reading, and every
        # write is refused: the attempt owes that loss from the moment the proof reads it, so the next proof, its
        # writes landing over the checkout back, still retires the run whole.
        run = self.settles_then_dies()[1]
        context = guarded.recovery_context(self)
        world = _AT_THE_WORLD.racing(_world.world_verdict, *self._goes_and_returns())
        refusing = patch.object(self.gh.pinned_failures, "refused", {self.issue.number})
        with refusing, patch.object(_world, _AT_THE_WORLD.step, world):
            self.assertFalse(self.proves())
        self.assertTrue(_owed_events.loss_owed(context))
        self.assertTrue(self.proves())
        self.assert_invalidated(run)

    def _arms(self) -> None:
        """Put the attempt's anchor back as another road would, arming the checkout's loss behind it."""
        _writes(self, {readings.KEY_PENDING_PUSH: self._standing})
        self._armed = True

    def _loses_once_armed(self, live, *args, **kwargs):
        """`live`, a reading of the checkout, taken with the checkout gone from disk the first time once armed, and the
        checkout put back right behind it."""
        if not self._armed:
            return live(*args, **kwargs)
        self._armed = False
        goes, returns = self._goes_and_returns()
        with ExitStack() as back:
            back.callback(returns)
            goes()
            return live(*args, **kwargs)

    def _goes_and_returns(self) -> tuple:
        """Taking the checkout away from disk, and putting it back."""
        away = self._wt.parent / _AWAY
        return partial(self._wt.rename, away), partial(away.rename, self._wt)


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
