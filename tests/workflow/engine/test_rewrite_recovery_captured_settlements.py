# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A dormant recovery record over a captured run that another road settles, or settles a newer run over, right then.

The guarded recovery case (`guarded_recovery_support`): issue #7's rebased
head reviewed and its run recorded, the finish killed posting its artifact, so
the run stands captured beside the attempt. The recovery context read off the
comment is handed straight to the dormant guarded hold or park
(`rewrite_recovery_parks.lands_a_hold`, `lands_a_park`), as a recovery road
would. Report 3 settles right under the strict edit of that record, which is
refused over it, and report 2 is put back right behind: the proof behind the
record reads report 3 moved under the captured run and abandons it.

Right as that abandonment is written, another finish of the landing settles
that very run -- announcing it on the attempt, or not -- which refuses the
abandonment. The recovery proof holds the captured run to the dormant
settled-evidence policy as a direct finish is held: the settlement is taken
in and invalidated whole over the movement already read under its receipt,
its revision and binding kept, and the announcement kept on the attempt.

The park's notice may raise instead, behind another road settling a newer
run in the captured run's place -- abandoning the captured run -- beside a
blank of the attempt's base tip, which is put back right behind the
reconciliation's reading of the comment. That reading read the blank under
the newer run, so the newer run is invalidated whole before the error goes
on, while the captured run, gone from the comment, is kept from the tick's
reading for its own proof. So is a newer run another road settles in the
captured run's place and marks moved in its handoff's place right ahead of
the reading the proof takes it in from, the handoff put back right behind:
the mark that reading read invalidates it. So is a newer run another road
settles on the captured run's binding as the proof's abandonment of that run
is lost unsent, the report moved under it only in the comment read to confirm
that edit, and put back right behind. Nothing is parked, run again, pushed, or
launched.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    rewrite_recovery_parks as _parks,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import LEFT_THE_LANDING
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled_support,
    verification_report_fixture as _report,
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# The dormant guarded records a case races, and how a recovery context lands each.
_PARKS = partial(_parks.lands_a_park, message="The auto rebase needs a human.", reason="auto_base_rebase_push_failed")
_LANDED_BY = (("hold", _parks.lands_a_hold), ("park", _PARKS))

# The client step a pinned-comment edit is.
_EDITS = "edit_pinned_state"

# A record a publication gate staged for the hold to land, as one holding over a reading of its own does, so the
# hold's record has an edit to send.
_GATE = "late_gate_hold"


def _every_edit(*_called, **_options) -> bool:
    """Whether a pinned-comment edit is one a boundary picks: every one, for the first -- the record's -- alone."""
    return True


# The strict edit of the hold's or park's record, the first pinned-comment edit either makes.
_AT_THE_RECORD = handoff.Boundary("at the record", _EDITS, _every_edit)


class _SettlesUnderTheAbandonment:
    """The client's strict edit, another finish settling `run` right ahead of the edit that abandons it.

    `announces` has that finish put its `base_rebased` event record on the
    attempt beside the settlement. `adopted` says whether it settled.
    """

    def __init__(self, case, run, *, announces: bool) -> None:
        self._case = case
        self._run = run
        self._announces = announces
        self._live = case.gh.edit_pinned_state
        self.adopted = False

    def __call__(self, issue, staged, **options):
        """Answer the edit, the first that drops the run's pending record settling the run ahead of it."""
        pending = _records.PENDING_EVIDENCE
        abandons = options["over"].get(pending) and not staged.get(pending)
        if abandons and not self.adopted:
            self.adopted = True
            self._settles(issue)
        return self._live(issue, staged, **options)

    def _settles(self, issue) -> None:
        """Publish the run's artifact and settle it over the comment as it stands, as another finish would."""
        case = self._case
        artifact = case.gh.publish_verification_artifact(case.pull_request, self._run.artifact)
        durable = _settlement.settled_state(
            case.gh.read_pinned_state(issue), self._run, artifact.landed_id, git_support.REVIEWING,
        )
        if self._announces:
            durable.set(readings.KEY_ANNOUNCED_EVENT, self._run.binding.target.target_head)
        case.gh.write_pinned_state(issue, durable)


class _ReplacesTheCapture:
    """The issue-thread post of a park's notice: a newer run settled over the captured `run`, the tip blanked, a raise.

    Another road settles the newer run, kept as `successor`, which abandons
    `run`, and blanks the base tip the attempt recorded its replay as made
    onto. The reconciliation's reading of the comment (`reads`) has the tip
    put back right behind it.
    """

    def __init__(self, case, run) -> None:
        self._case = case
        self._run = run
        self._read = _durable.durable_comment
        self._tip = None
        self.successor = None

    def __call__(self, *_posted, **_options):
        """Settle the newer run over `run` and blank the tip, then raise as GitHub not answering the post."""
        case = self._case
        self.successor = settled_support.records_a_newer_run(case, settles=True, binding=self._run.binding)
        state = case.gh.read_pinned_state(case.issue)
        self._tip = state.get(readings.KEY_REWRITE_BASE)
        state.set(readings.KEY_REWRITE_BASE, None)
        case.gh.write_pinned_state(case.issue, state)
        raise RuntimeError("GitHub did not answer the notice's post")

    def reads(self, *read, **options):
        """The comment read afresh, the first reading behind the raise having the tip put back right behind it."""
        durable = self._read(*read, **options)
        if self._tip is not None and durable[0] is not None:
            state = self._case.gh.read_pinned_state(self._case.issue)
            state.set(readings.KEY_REWRITE_BASE, self._tip)
            self._case.gh.write_pinned_state(self._case.issue, state)
            self._tip = None
        return durable


class _MarksBehindTheReading:
    """The comment read afresh, the first reading a newer run settled over the captured `run` and marked moved.

    Another road settles the newer run, kept as `successor`, and writes the
    mark of its movement in its handoff's place right ahead of that reading,
    putting the handoff back right behind it.
    """

    def __init__(self, case, run) -> None:
        self._case = case
        self._run = run
        self._read = _durable.durable_comment
        self.successor = None

    def reads(self, *read, **options):
        """The comment read afresh, the first reading taken with the newer run marked and the mark taken off behind."""
        if self.successor is not None:
            return self._read(*read, **options)
        case = self._case
        self.successor = settled_support.records_a_newer_run(case, settles=True, binding=self._run.binding)
        state = case.gh.read_pinned_state(case.issue)
        handoff = state.get(_records.EVIDENCE_HANDOFF)
        state.set(_records.EVIDENCE_HANDOFF, {"moved": self.successor.receipt})
        case.gh.write_pinned_state(case.issue, state)
        durable = self._read(*read, **options)
        state = case.gh.read_pinned_state(case.issue)
        state.set(_records.EVIDENCE_HANDOFF, handoff)
        case.gh.write_pinned_state(case.issue, state)
        return durable


class _LosesTheAbandonment:
    """The client's strict edit and reading: the abandonment of `run` lost unsent, a newer run settled in its place.

    Another road settles the newer run, kept as `successor`, on the binding of
    `run` as the edit abandoning `run` goes out, and that edit is never sent,
    its answer lost. The reading behind it is taken with the report's
    revision moved under the newer run, the report put back right behind it.
    """

    def __init__(self, case, run) -> None:
        self._case = case
        self._run = run
        self._edit = case.gh.edit_pinned_state
        self._read = case.gh.read_pinned_state
        self._armed = False
        self.successor = None

    def edits(self, issue, staged, **options):
        """Answer the edit; the first that drops the run's pending record lost unsent, the newer run settled instead."""
        pending = _records.PENDING_EVIDENCE
        abandons = options["over"].get(pending) and not staged.get(pending)
        if not abandons or self.successor is not None:
            return self._edit(issue, staged, **options)
        self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=self._run.binding)
        self._armed = True
        return PinnedEdit.UNCONFIRMED

    def reads(self, issue):
        """The comment, read; the first reading behind the lost edit taken with the report's revision moved."""
        if not self._armed:
            return self._read(issue)
        self._armed = False
        report = _MOVED_RECORDS[0]
        before = self._read(issue)
        moved = self._read(issue)
        recorded = moved.get(report)
        moved.set(report, {**recorded, "revision": recorded["revision"] + 1})
        self._case.gh.write_pinned_state(issue, moved)
        reading = self._read(issue)
        self._case.gh.write_pinned_state(issue, before)
        return reading


class CapturedSettlementTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A captured run's abandonment behind a dormant record retires a settlement another finish made of it."""

    def test_a_concurrent_settlement_is_retired(self) -> None:
        # Report 3 moves under the hold's or park's record, so the proof
        # abandons the captured run, and another finish settles that run --
        # announcing it, or not -- right as the abandonment is written: the
        # settlement is invalidated whole over report 3's move, its revision
        # and binding kept, the announcement kept, and nothing parked.
        for (name, lands), announces in product(_LANDED_BY, (False, True)):
            with self.subTest(record=name, announces=announces):
                self.setUp()
                head, run = self.captures()
                self._lands_under_report_three(head, run, lands, announces=announces)

                self._assert_retired(run, head if announces else None)

    def test_a_captured_runs_successor_is_retired(self) -> None:
        # The park's notice raises behind another road settling a newer run
        # in the captured run's place beside a blank of the base tip, and the
        # tip is put back right behind the reconciliation's reading: the
        # newer run is invalidated whole over the blank that reading read
        # before the error goes on, the captured run left abandoned, and
        # nothing parked or current.
        run = self.captures()[1]
        replaces = _ReplacesTheCapture(self, run)
        context = guarded.recovery_context(self)
        with (
            patch.object(self.gh, "comment", replaces),
            patch.object(_durable, "durable_comment", replaces.reads),
        ):
            self.assertRaises(RuntimeError, _PARKS, context)

        self._assert_retired(replaces.successor, None)
        retired = readings.pinned_records(self)[2]
        self.assertEqual(retired[-2], (run.receipt, readings.ABANDONED))

    def test_a_marked_successor_is_retired(self) -> None:
        # The proof before a park that keeps the attempt holds a captured run
        # alone, and another road settles a newer run in its place and marks
        # it moved right ahead of the reading the proof takes it in from,
        # putting the handoff back right behind: the mark that reading read
        # invalidates the newer run whole.
        run = self.captures()[1]
        marks = _MarksBehindTheReading(self, run)
        with patch.object(_durable, "durable_comment", marks.reads):
            self.proves()

        self._assert_retired(marks.successor, None)

    def _lands_under_report_three(self, head: str, run, lands, *, announces: bool) -> None:
        """Hand `lands` a context read off the comment, report 3 settled under its record's edit and undone behind.

        Another finish settles `run`, announcing it where `announces`, right
        ahead of the edit that abandons it.
        """
        replaced: dict = {}
        settles = _SettlesUnderTheAbandonment(self, run, announces=announces)
        edits = _AT_THE_RECORD.racing(
            settles, partial(self._settles_report_three, head, replaced), partial(self._writes, replaced),
        )
        context = guarded.recovery_context(self)
        context.state.set(_GATE, head)
        with patch.object(self.gh, _EDITS, edits):
            lands(context)
        self.assertTrue(settles.adopted)

    def _settles_report_three(self, head: str, replaced: dict) -> None:
        """Settle report 3 of `head` over the comment as it stands, keeping in `replaced` what it moved."""
        self.state = self.gh.read_pinned_state(self.issue)
        replaced.update({key: self.state.get(key) for key in _MOVED_RECORDS})
        _report.settles_report(self, 3, "Covered a base that moved twice as well.", head=head)
        self.gh.write_pinned_state(self.issue, self.state)

    def _writes(self, records: dict) -> None:
        """Write `records` onto the comment as it stands."""
        state = self.gh.read_pinned_state(self.issue)
        for key, recorded in records.items():
            state.set(key, recorded)
        self.gh.write_pinned_state(self.issue, state)

    def _assert_retired(self, run, announced: str | None) -> None:
        """Nothing pending, current, or parked; `run` invalidated whole, its revision and binding kept; run once.

        `announced` is the head the attempt's `base_rebased` event record names, None where it names none.
        """
        pending, current, retired = readings.pinned_records(self)
        self.assertEqual((pending, current), (None, None))
        self.assertEqual(retired[-1], (run.receipt, readings.INVALIDATED))
        self.assertEqual(self.pinned_fields(readings.KEY_ANNOUNCED_EVENT), (announced,))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (run.revision, run.binding))
        self.assertFalse(self.pinned_fields(guarded.AWAITING)[0])
        self.assert_made_once()


class LostAbandonmentTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A captured run's abandonment lost unsent behind a newer run settled in its place, movement read confirming it."""

    def test_a_confirming_read_retires_the_successor(self) -> None:
        # The proof, handed the run moved off the landing, abandons it; that edit is lost unsent as another road
        # settles a newer run on the run's binding. The comment read to confirm the edit -- the only reading of the
        # report moved under the newer run, put back right behind -- is asked like every reading of the proof's, so
        # the newer run is invalidated whole and the next proof finds nothing current.
        run = self.captures()[1]
        loses = _LosesTheAbandonment(self, run)
        context = guarded.recovery_context(self)
        with patch.multiple(self.gh, edit_pinned_state=loses.edits, read_pinned_state=loses.reads):
            self.assertFalse(_parks.proves_before_a_park(context, {run.receipt: LEFT_THE_LANDING}))
        self.assertTrue(self.proves())

        records = readings.pinned_records(self)
        self.assertEqual(records[:2], (None, None))
        self.assertIn((loses.successor.receipt, readings.INVALIDATED), records[2])


if __name__ == "__main__":
    unittest.main()
