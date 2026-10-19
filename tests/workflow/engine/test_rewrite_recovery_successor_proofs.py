# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A dormant recovery proof that proves every run standing for the landed head, a successor in the run's place included.

The guarded recovery case (`guarded_recovery_support`): issue #7's rebased
head reviewed and its run settled -- or only captured -- under the anchor, and
the finish killed short of its route, so the attempt stands. The recovery
context read off the comment is handed straight to the dormant guarded park,
or to the proof before a park that keeps the attempt
(`rewrite_recovery_parks`), as a recovery road would.

- The park's notice raises behind report 3 settled under the run, and right
  behind the reconciliation's reading another road settles a newer run in the
  run's place and puts report 2 back. The movement already read under the
  run cannot invalidate it over a comment that no longer carries it, so the
  newer run is proved on its own binding before the error goes on:
  invalidated whole where it is bound to report 3, kept current where it is
  bound to report 2.
- The very reading the proof takes of the comment carries a newer run
  settled in the place of the run it holds -- settled, or only captured --
  beside a blank of the base tip, put back right behind: that blank moves the
  newer run, which is invalidated whole. So it does where that reading is the
  one the proof takes behind two invalidations of the run, which cannot land
  over the newer run standing in its place. So it does where that reading is
  one the run's own retirement takes over movement already read under it --
  the last word of a captured run's abandonment, the invalidation of a
  settled one -- or the comment the strict edit of that invalidation finds
  moved under it.
- A run is read beside a blank of the base tip in the very reading its proof
  takes -- its own record taken off beside it, or not -- put back right
  behind: that blank moves the run, a captured one abandoned whole and a
  settled one invalidated whole.
- So does a blank read only after the run's own proof answered, or only by
  its record's commit (`LateMovementTest`): a captured run its proof kept,
  read beside it in the reading the settled proof's reconciliation takes
  behind, is proved again and abandoned whole, before a park or a hold's
  record, so the next tick settles nothing; and a settled run, read beside it
  in the reading a hold's record refused for room takes to say whether the
  comment moved, is invalidated whole, nothing of the tick's state written.
  So is a captured run read outranked by a revision spent past it in the
  proof's own reading, the floor put back right behind: it is abandoned whole.
  And a newer run another road settles right as the reset record's proof
  answers, the tip left blank -- or the run itself and its report put back
  there -- is read standing in the comment that record reads behind its
  proof, and invalidated whole before the reset goes on.

Nothing is run again, pushed, or launched.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import persistence
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.workflow.engine import (
    report_commits as _commits,
    rewrite_landing_retirement as _retirement,
    rewrite_recovery_parks as _parks,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_readings as readings,
    settled_finish_support as settled_support,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# What another road puts back to restore a run its proof retired: the run itself, and the report it is bound to.
_RESTORED = (_records.CURRENT_EVIDENCE, _MOVED_RECORDS[0])

# The park a case hands the dormant guarded park.
_PARKS = partial(_parks.lands_a_park, message="The auto rebase needs a human.", reason="auto_base_rebase_push_failed")

# How the history records evidence a newer transaction for its head settled over.
_SUPERSEDED = "superseded"

# The client's reading of the pinned comment, which a case stands in for.
_READS = "read_pinned_state"

# A field of the tick's state too long for the comment, so the record carrying it is refused for room.
_FILLER = "a_field_too_long_for_the_comment"

# The guarded commit's withholding of the tick's state, read before any case stands in for it.
_WITHHOLDS = _commits.ReportCommit.withholds

# Movement a caller already read under the run, as a record's refusal reads it.
_MOVED = ReportEvidence(ReportEvidenceVerdict.DEFER, "a record the run's binding rests on moved")

# Whether a case's run is only captured, and what its first reading takes off beside the base tip.
_BLANKS = (
    (True, ()),
    (True, (_records.PENDING_EVIDENCE,)),
    (False, ()),
    (False, (_records.CURRENT_EVIDENCE,)),
)

# Whether a case's run is only captured, and which reading of the comment its
# retirement takes with the base tip blank: the last word of the captured
# run's abandonment, behind the captured proof's own, or the settled run's
# invalidation's first.
_RETIRING = ((True, 2), (False, 1))


def _writes(case, records: dict) -> None:
    """Write `records` onto `case`'s comment as it stands."""
    state = case.gh.read_pinned_state(case.issue)
    for key, recorded in records.items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)


def _writes_behind(case, run, standing: dict, *, restores: bool) -> None:
    """Put `standing` back on `case`'s comment where `restores`, or else settle a newer run on `run`'s binding."""
    if restores:
        _writes(case, standing)
    else:
        settled_support.records_a_newer_run(case, settles=True, binding=run.binding)


def _moves_the_report(case) -> None:
    """Move the report the run is bound to a revision on, over `case`'s comment as it stands, as another road would."""
    report = readings.pinned(case).get(_MOVED_RECORDS[0])
    moved = {**report, "revision": report["revision"] + 1}
    _writes(case, {_MOVED_RECORDS[0]: moved})


class _SettlesBehindTheReading:
    """The park's notice raising behind report 3, and a newer run settled right behind the next reading of the comment.

    Report 3 of `head` settles as the notice's post raises (`raises`). Right
    behind the next reading of the comment (`reads`) another road settles a
    newer run, kept as `successor` -- bound to report 3, or to `run`'s own
    binding where `valid` -- in `run`'s place, and puts report 2 back.
    """

    def __init__(self, case, head: str, run, *, valid: bool) -> None:
        self._case = case
        self._head = head
        self._run = run
        self._valid = valid
        self._read = _durable.durable_comment
        self._earlier: dict = {}
        self._subject = None
        self.successor = None

    def raises(self, *_posted, **_options):
        """Settle report 3 over the comment as it stands, then raise as GitHub not answering the notice's post."""
        case = self._case
        case.state = case.gh.read_pinned_state(case.issue)
        self._earlier = {key: case.state.get(key) for key in _MOVED_RECORDS}
        self._subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)
        raise RuntimeError("GitHub did not answer the notice's post")

    def reads(self, *read, **options):
        """The comment read afresh, the first reading behind the raise having the newer run settled behind it."""
        durable = self._read(*read, **options)
        if self._earlier:
            earlier = self._earlier
            self._earlier = {}
            binding = self._run.binding
            if not self._valid:
                target = replace(binding.target, subject=self._subject.recorded())
                binding = replace(binding, target=target)
            self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=binding)
            _writes(self._case, earlier)
        return durable


class _BlanksTheTip:
    """`live`, a call reading the comment, its `at`-th taken with the base tip blank and put back right behind it.

    The call is a reading of the comment, or a strict edit, whose walk then
    finds the comment moved. `drops` takes those records off beside the tip, put back with it;
    `settles`, a binding, has another road settle a newer run bound to it in
    the run's place first, kept as `successor`.
    """

    def __init__(self, case, live, *, at: int = 1, drops: tuple = (), settles=None) -> None:
        self._case = case
        self._live = live
        self._at = at
        self._drops = drops
        self._settles = settles
        self.calls = 0
        self.successor = None

    def __call__(self, *read, **options):
        """The reading, the `at`-th one taken with the tip blank -- and `drops` off -- right then."""
        self.calls += 1
        if self.calls != self._at:
            return self._live(*read, **options)
        if self._settles is not None:
            self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=self._settles)
        pinned = readings.pinned(self._case)
        moved = (readings.KEY_REWRITE_BASE, *self._drops)
        restored = {key: pinned.get(key) for key in moved}
        _writes(self._case, dict.fromkeys(restored))
        blank = self._live(*read, **options)
        _writes(self._case, restored)
        return blank


class SuccessorProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """Every run standing for the landed head is proved on its own binding, however soon what moved is put back."""

    def test_a_successor_behind_a_move_is_proved(self) -> None:
        # Report 3 moves under the run as the park's notice raises, and a newer
        # run is settled in the run's place right behind the reconciliation's
        # reading, report 2 put back: bound to report 3 it is invalidated whole
        # before the error goes on; bound as the run was, it is kept current.
        for valid in (False, True):
            with self.subTest(valid=valid):
                self.setUp()
                head, run = self.settles_then_dies()
                settles = _SettlesBehindTheReading(self, head, run, valid=valid)
                with (
                    patch.object(self.gh, "comment", settles.raises),
                    patch.object(_durable, "durable_comment", settles.reads),
                ):
                    self.assertRaises(RuntimeError, _PARKS, guarded.recovery_context(self))

                self._assert_proved(run, settles.successor, valid=valid)

    def test_a_successor_beside_a_blank_is_retired(self) -> None:
        # The first reading the proof before a park takes carries a newer run
        # in the place of the run it holds -- settled, or only captured --
        # beside a blank of the base tip, put back right behind: the newer run
        # is invalidated whole, with nothing current.
        for captured in (False, True):
            with self.subTest(captured=captured):
                self.setUp()
                run = (self.captures() if captured else self.settles_then_dies())[1]
                context = guarded.recovery_context(self)
                blanks = _BlanksTheTip(self, self.gh.read_pinned_state, settles=run.binding)
                with patch.object(self.gh, _READS, blanks):
                    _parks.proves_before_a_park(context)

                self._assert_proved(None, blanks.successor, valid=False)

    def test_a_successor_read_for_its_adoption(self) -> None:
        # Movement is already read under the run, a newer run stands in its
        # place, and the reading the proof takes behind its two invalidations
        # of the run -- which cannot land over that newer run -- carries it
        # beside a blank of the base tip, put back right behind: the newer run
        # is invalidated whole, with nothing current.
        run = self.settles_then_dies()[1]
        context = guarded.recovery_context(self)
        successor = settled_support.records_a_newer_run(self, settles=True, binding=run.binding)
        blanks = _BlanksTheTip(self, _durable.durable_comment, at=3)
        with patch.object(_durable, "durable_comment", blanks):
            _parks.proves_before_a_park(context, {run.receipt: _MOVED})

        self.assertGreaterEqual(blanks.calls, 3)
        self._assert_proved(None, successor, valid=False)

    def test_a_successor_read_by_a_retirement(self) -> None:
        # Movement is already read under the run, and a reading its retirement
        # takes -- the last word of a captured run's abandonment, or a settled
        # run's invalidation -- carries a newer run settled in its place beside
        # a blank of the base tip, put back right behind: the newer run is
        # invalidated whole under its own receipt, with nothing current.
        for captured, at in _RETIRING:
            with self.subTest(captured=captured):
                self.setUp()
                run = (self.captures() if captured else self.settles_then_dies())[1]
                context = guarded.recovery_context(self)
                blanks = _BlanksTheTip(self, self.gh.read_pinned_state, at=at, settles=run.binding)
                with patch.object(self.gh, _READS, blanks):
                    _parks.proves_before_a_park(context, {run.receipt: _MOVED})

                self._assert_proved(None, blanks.successor, valid=False)

    def test_a_successor_found_by_an_edit(self) -> None:
        # Movement is already read under the settled run, and the strict edit
        # invalidating it finds a newer run settled in its place beside a blank
        # of the base tip, put back right behind: the newer run is invalidated
        # whole under its own receipt, with nothing current.
        run = self.settles_then_dies()[1]
        context = guarded.recovery_context(self)
        edits = _BlanksTheTip(self, self.gh.edit_pinned_state, settles=run.binding)
        with patch.object(self.gh, "edit_pinned_state", edits):
            _parks.proves_before_a_park(context, {run.receipt: _MOVED})

        self._assert_proved(None, edits.successor, valid=False)

    def test_a_blanked_run_is_retired(self) -> None:
        # The first reading the proof takes has the base tip blank -- the run's
        # own record taken off beside it, or not -- put back right behind: a
        # run only captured is abandoned whole, a settled one invalidated
        # whole, each with its revision and binding.
        for captured, drops in _BLANKS:
            with self.subTest(captured=captured, drops=drops):
                self.setUp()
                run = (self.captures() if captured else self.settles_then_dies())[1]
                context = guarded.recovery_context(self)
                blanks = _BlanksTheTip(self, self.gh.read_pinned_state, drops=drops)
                with patch.object(self.gh, _READS, blanks):
                    _parks.proves_before_a_park(context)

                (self.assert_abandoned if captured else self.assert_invalidated)(run)

    def _assert_proved(self, run, successor, *, valid: bool) -> None:
        """`successor` current over `run` superseded where `valid`; otherwise invalidated whole, nothing current.

        Invalidated whole is into history under its own receipt, its revision and binding kept.
        """
        pending, current, retired = readings.pinned_records(self)
        self.assertIsNone(pending)
        self.assertEqual(getattr(current, "receipt", None), successor.receipt if valid else None)
        if valid:
            self.assertEqual(retired[-1], (run.receipt, _SUPERSEDED))
            return
        self.assertEqual(retired[-1], (successor.receipt, readings.INVALIDATED))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (successor.revision, successor.binding))



class LateMovementTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A run read moving where no later reading would show it -- late, at its record, or for a moment -- is retired."""

    def test_a_revision_spent_past_a_captured_run(self) -> None:
        # The proof's own reading shows a revision spent past the captured run,
        # the floor put back right behind it: the run is abandoned whole, so no
        # later finish settles it.
        run = self.captures()[1]
        spends = partial(self._spends_past, self.gh.read_pinned_state, run.revision + 1, [])
        with patch.object(self.gh, _READS, spends):
            self.proves()

        self.assert_abandoned(run)

    def test_a_run_moved_behind_its_proof(self) -> None:
        # A captured run's own proof keeps it, and the reading the settled
        # proof's reconciliation takes right behind -- the first the proof
        # reads through the durable reader -- has the base tip blank, put back
        # right behind it: the run is proved again with that movement, before a
        # park or a hold's record, and abandoned whole, so the next tick
        # settles nothing.
        for name, records in (("park", self.proves), ("hold", self._holds)):
            with self.subTest(record=name):
                self.setUp()
                run = self.captures()[1]
                blanks = _BlanksTheTip(self, _durable.durable_comment)
                with patch.object(_durable, "durable_comment", blanks):
                    records()

                self.assertGreaterEqual(blanks.calls, 1)
                self.assert_abandoned(run)
                self.recovers()
                self.assertIsNone(readings.pinned_records(self)[1])

    def test_a_successor_read_behind_the_reset_proof(self) -> None:
        # The reset's record reads the run's report moved and its proof retires the run; right as that proof answers,
        # another road settles a newer run on the run's binding, or puts the run and its report back, the tip left
        # blank. The comment the record reads behind its proof shows that run standing under a receipt it read moving,
        # which is proved again and invalidated whole before the reset goes on, so nothing stands current over the
        # checkout put back on the anchor.
        for restores in (False, True):
            with self.subTest(restores=restores):
                self.setUp()
                run = self.settles_then_dies()[1]
                standing = dict(zip(_RESTORED, self.pinned_fields(*_RESTORED), strict=True))
                races = _RacesPastTheCall(
                    _retirement.retires_unproved, 1, partial(_writes_behind, self, run, standing, restores=restores),
                )
                _moves_the_report(self)
                with patch.object(_retirement, "retires_unproved", races):
                    self._holds(partial(persistence._resets, reset_sha=self.anchor))

                self.assertEqual(self._wt_head(), self.anchor)
                self.assertIsNone(readings.pinned_records(self)[1])
                retired = readings.pinned_records(self)[2][-1]
                self.assertEqual(retired[1], readings.INVALIDATED)
                self.assertEqual(retired[0] == run.receipt, restores)

    def test_a_blank_behind_a_refusal_for_room(self) -> None:
        # The tick's state is too long for the comment, so a hold's record is
        # refused for room, and the base tip reads blank in the reading the
        # commit takes behind that refusal to say whether the comment moved,
        # put back right behind it: that reading moves the run, which is
        # invalidated whole, the attempt kept and nothing of the tick's state
        # written.
        run = self.settles_then_dies()[1]
        withholds = partial(self._withholds_over_a_blank, [])
        with patch.object(_commits.ReportCommit, "withholds", side_effect=withholds, autospec=True):
            state = self._holds(overflows=True)

        self.assert_invalidated(run)
        self.assertTrue(state.withheld)
        self.assertNotIn(_FILLER, readings.pinned(self))
        self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH)[0], self.anchor)

    def _holds(self, asks=_parks.lands_a_hold, *, overflows: bool = False):
        """Hand `asks`, the dormant hold where none is named, the context read off the comment -- its state too long
        for it where `overflows`; that state."""
        context = guarded.recovery_context(self)
        if overflows:
            context.state.set(_FILLER, "x" * MAX_PINNED_BODY)
        asks(context)
        return context.state

    def _spends_past(self, live, revision: int, reads: list, issue):
        """`live`, the client's reading; the proof's first, behind its context's, has the floor at `revision`."""
        reads.append(issue)
        if len(reads) != 2:
            return live(issue)
        floor = readings.pinned(self).get(readings.KEY_REVISION_FLOOR)
        _writes(self, {readings.KEY_REVISION_FLOOR: revision})
        read = live(issue)
        _writes(self, {readings.KEY_REVISION_FLOOR: floor})
        return read

    def _withholds_over_a_blank(self, blanked: list, commit, outcome=None) -> bool:
        """`ReportCommit.withholds`, the first asked reading the comment with the base tip blank, put back behind."""
        if blanked:
            return _WITHHOLDS(commit, outcome)
        blanked.append(outcome)
        with patch.object(self.gh, _READS, _BlanksTheTip(self, self.gh.read_pinned_state)):
            return _WITHHOLDS(commit, outcome)


if __name__ == "__main__":
    unittest.main()
