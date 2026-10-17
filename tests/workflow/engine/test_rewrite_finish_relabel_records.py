# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A dormant finish's relabel, held to the evidence it routes and made once whatever label the issue already wore.

Direct finishes held to the dormant settled-evidence policy
(`settled_route_support`): issue #7's reviewed rebase, its run settled under
the anchor and its finish killed before its announcement, so the next finish
routes the head. Report 3 settled just as the relabel's recheck reads the
comment afresh, report 2 put back right behind that reading, is movement read
under the run: the run is invalidated whole before the relabel and the head
routed once with nothing current, putting report 2 back reviving nothing. A
successor another road settled bound to report 3 in the run's place, read by
that recheck with report 2 put back and report 3 put back behind it, is
invalidated on its own binding the same way. A relabel that raises, behind
another road settling report 3 and a newer run bound to it and then putting
report 2 back, is proved again over the comment
as it then stands: that newer run is invalidated on its own binding before
the error goes on, so putting report 3 back revives nothing and the next
finish routes the head once.

On an issue already on `workflow:validating` the relabel's own record lands
ahead of it, and a finish lost anywhere around the two comes back behind a
restart with its event tail gone. With no audit log, a finish lost at that
record or behind the relabel is relabelled once in all; one lost at the
relabel itself, behind its record, is read as relabelled -- nothing durable
says otherwise -- so the stage-entry event is filed at most once, never twice.
With the log configured, that last one is answered off the log, which lacks
the stage-entry event naming the head, and relabelled once. A relabel that
raises takes its record back, and the next finish relabels once.
"""
from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from functools import partial
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import rewrite_finish_rechecks as _rechecks, rewrite_finish_settled as _settled
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled_support,
    settled_route_support as route,
    verification_report_fixture as _report,
)

# Each finish lost around the relabel of an issue already on `workflow:validating`,
# and how many relabels onto it the issue has taken once a restart with no audit
# log finished it twice: the one ahead of the rebase, and the route's own --
# save at the relabel itself, behind its record, read as made.
_RESTARTS = (
    (handoff.BEFORE_THE_RELABEL_RECORD, readings.ROUTED * 2),
    (handoff.BEFORE_THE_RELABEL, readings.ROUTED),
    (handoff.BEFORE_THE_RETIREMENT, readings.ROUTED * 2),
)

# The stage-entry events onto `workflow:validating` an issue that wore it ahead
# of the rebase has filed once the route relabelled it once: that one, and the route's.
_ENTERED_TWICE = ("validating", "validating")

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

_UNANSWERED = "GitHub did not answer the relabel"

# An attempt another road anchors in place of the finish's.
_ANOTHER_ANCHOR = "e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0e0"

# What `_MovesUnderTheRecheck` moves for its one reading, put back behind it.
_RACED_RECORDS = (*_MOVED_RECORDS, readings.KEY_PENDING_PUSH)

# Each relabel that raises behind another road's move: whether that road
# blanked the attempt's base tip rather than settling a successor, and whether
# what it moved is put back right behind the reading the proof starts from.
_RAISED_RELABELS = ((False, False), (False, True), (True, True))


class _MovesUnderTheRecheck:
    """The relabel recheck's reading of the comment, report 3 of `head` settled ahead of it and put back behind it.

    `replaces` has another road anchor an attempt of its own in place of the
    finish's beside report 3, for that one reading, put back with it.
    """

    def __init__(self, case, head: str, *, replaces: bool = False) -> None:
        self._case = case
        self._head = head
        self._replaces = replaces
        self._live = _rechecks.read_afresh
        self._replaced: dict = {}

    def __call__(self, finish):
        """Read the comment afresh, the first time with report 3 -- and another attempt -- settled for it alone."""
        if self._replaced:
            return self._live(finish)
        case = self._case
        case.state = case.gh.read_pinned_state(case.issue)
        self._replaced = {key: case.state.get(key) for key in _RACED_RECORDS}
        _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        if self._replaces:
            case.state.set(readings.KEY_PENDING_PUSH, _ANOTHER_ANCHOR)
        case.gh.write_pinned_state(case.issue, case.state)
        durable = self._live(finish)
        _writes(case, self._replaced, keeping={})
        return durable

    def patching(self):
        """This reading in place of the recheck's own."""
        return patch.object(_rechecks, "read_afresh", self)

    def assert_retired(self, run) -> None:
        """History ending with `run`, read moving, invalidated whole."""
        retired = readings.pinned_records(self._case)[2][-1]
        self._case.assertEqual(retired, (run.receipt, readings.INVALIDATED))


class _RaisesUnderTheRelabel:
    """The relabel, the first time answered by another road's newer run of `head` and a raise.

    That road settles report 3 and a run bound to it, kept as `successor`,
    keeps the records report 3 moved in `settled`, and puts report 2 back --
    or, `blanks`, blanks the base tip the attempt recorded its replay as made
    onto instead, as a reset is recorded, keeping that tip in `settled`.
    """

    def __init__(self, case, head: str, *, blanks: bool = False) -> None:
        self._case = case
        self._head = head
        self._blanks = blanks
        self._live = case.gh.set_workflow_label
        self.raised = False
        self.settled: dict = {}
        self.successor = None

    def __call__(self, *labelled, **correlation):
        """Settle the newer run and put report 2 back, or blank the tip, then raise; relabel after that."""
        if self.raised:
            return self._live(*labelled, **correlation)
        self.raised = True
        case = self._case
        if self._blanks:
            _writes(case, {readings.KEY_REWRITE_BASE: None}, keeping=self.settled)
            raise RuntimeError(_UNANSWERED)
        case.state = case.gh.read_pinned_state(case.issue)
        replaced = {key: case.state.get(key) for key in _MOVED_RECORDS}
        subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)
        earlier = readings.pinned_records(case)[1].binding
        bound = replace(earlier, target=replace(earlier.target, subject=subject.recorded()))
        self.successor = settled_support.records_a_newer_run(case, settles=True, binding=bound)
        _writes(case, replaced, keeping=self.settled)
        raise RuntimeError(_UNANSWERED)

    def assert_retired(self, run) -> None:
        """History ending with `run` superseded by the successor and that invalidated whole -- or `run` itself."""
        history = readings.pinned_records(self._case)[2]
        if self.successor is None:
            self._case.assertEqual(history[-1], (run.receipt, readings.INVALIDATED))
            return
        superseded = (run.receipt, readings.SUPERSEDED)
        invalidated = (self.successor.receipt, readings.INVALIDATED)
        self._case.assertEqual(history[-2:], (superseded, invalidated))


class _RestoresBehindTheProof:
    """The proof's fresh reading behind a raised relabel, what `raises` moved put back right behind it where `restores`.

    That reading carries the successor `raises` settled beside report 2,
    which disproves its binding, or the base tip it blanked; report 3, or the
    tip, put back behind it would prove the evidence again to any reading
    taken after.
    """

    def __init__(self, case, raises: _RaisesUnderTheRelabel, *, restores: bool) -> None:
        self._case = case
        self._raises = raises
        self._live = _settled.read_afresh
        self._restored = not restores

    def __call__(self, finish):
        """Read the comment afresh, the first time behind the raise with what it moved put back right behind it."""
        durable = self._live(finish)
        if self._raises.raised and not self._restored:
            self._restored = True
            _writes(self._case, self._raises.settled, keeping={})
        return durable


class _SucceedsUnderTheRecheck:
    """The relabel recheck's reading of the comment, another road's newer run of `head` settled in the run's place.

    That road settles report 3 and a run bound to it, kept as `successor`,
    and puts report 2 back ahead of the reading (`_RaisesUnderTheRelabel`,
    its raise swallowed), so the reading disproves the successor's own
    binding; report 3 is put back right behind it. `at_the_record` races the
    strict edit of the relabel's own record instead (`edits`), which is
    refused over the comment it finds, report 3 put back behind that refusal
    -- or, `blanks`, a newer run settled bound to report 2 beside the
    attempt's base tip blanked there, the tip put back behind the refusal.
    """

    def __init__(self, case, head: str, *, at_the_record: bool = False, blanks: bool = False) -> None:
        self._case = case
        self._at_the_record = at_the_record
        self._blanks = blanks
        self._live = _rechecks.read_afresh
        self._edit = case.gh.edit_pinned_state
        self._race = _RaisesUnderTheRelabel(case, head)
        self._head = head
        self._tip: dict = {}
        self._successor = None

    def __call__(self, finish):
        """Read the comment afresh, the first time with the successor settled and report 2 put back for it."""
        if self._race.raised:
            return self._live(finish)
        self._case.assertRaises(RuntimeError, self._race)
        durable = self._live(finish)
        _writes(self._case, self._race.settled, keeping={})
        return durable

    def edits(self, issue, state, *, over: dict, **options):
        """The client's strict edit, the relabel's record the first time raced by the successor and refused over it."""
        records = state.get(readings.KEY_RELABELLED) == self._head
        if not records or over.get(readings.KEY_RELABELLED) or self._race.raised or self._tip:
            return self._edit(issue, state, over=over, **options)
        if self._blanks:
            self._successor = settled_support.records_a_newer_run(self._case, settles=True)
            _writes(self._case, {readings.KEY_REWRITE_BASE: None}, keeping=self._tip)
        else:
            self._case.assertRaises(RuntimeError, self._race)
        answered = self._edit(issue, state, over=over, **options)
        _writes(self._case, self._tip or self._race.settled, keeping={})
        return answered

    def patching(self):
        """This race in place of the recheck's reading, or of the client's strict edit `at_the_record`."""
        if self._at_the_record:
            return patch.object(self._case.gh, "edit_pinned_state", self.edits)
        return patch.object(_rechecks, "read_afresh", self)

    def assert_retired(self, run) -> None:
        """History ending with `run` superseded by the successor, and the successor invalidated whole."""
        if self._successor is None:
            self._race.assert_retired(run)
            return
        history = readings.pinned_records(self._case)[2]
        superseded = (run.receipt, readings.SUPERSEDED)
        invalidated = (self._successor.receipt, readings.INVALIDATED)
        self._case.assertEqual(history[-2:], (superseded, invalidated))


# Each race around the route's relabel, and what the finish it races comes
# to: report 3 moved under the recheck, beside another attempt there too, a
# successor settled under the recheck, or one settled at the relabel's record
# -- off its binding, or beside the base tip blanked there.
_RELABEL_READS = (
    (partial(_MovesUnderTheRecheck), FinishOutcome.ROUTED),
    (partial(_MovesUnderTheRecheck, replaces=True), FinishOutcome.HELD),
    (partial(_SucceedsUnderTheRecheck), FinishOutcome.ROUTED),
    (partial(_SucceedsUnderTheRecheck, at_the_record=True), FinishOutcome.REFUSED),
    (partial(_SucceedsUnderTheRecheck, at_the_record=True, blanks=True), FinishOutcome.REFUSED),
)


def _lands_then_raises(live, *labelled, **correlation) -> None:
    """`live`, the client's relabel, landing -- its stage-entry event filed -- and then raising as an answer lost."""
    live(*labelled, **correlation)
    raise RuntimeError(_UNANSWERED)


def _writes(case, records: dict, *, keeping: dict) -> None:
    """Write `records` onto the comment, keeping what they replace in `keeping`."""
    state = case.gh.read_pinned_state(case.issue)
    for key, recorded in records.items():
        keeping[key] = state.get(key)
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)


class RelabelReadsTest(route.SettledRouteCase, unittest.TestCase):
    """What a dormant finish's relabel reads, around the evidence it routes, decides that relabel once."""

    def test_a_move_read_by_the_recheck_counts(self) -> None:
        # Report 3 settles as the relabel's recheck reads the comment, and
        # report 2 is put back right behind that reading -- or another road
        # settles a newer run bound to report 3 in the run's place and puts
        # report 2 back ahead of that reading, report 3 back right behind it:
        # the evidence that reading carries, the run or that successor on its
        # own binding, is invalidated whole before the relabel, and the head
        # is routed once with nothing current. So it is where that reading
        # carries another attempt beside report 3, both put back behind it --
        # the route held over that attempt -- and where the successor is read
        # by the refused strict edit of the relabel's record instead: the next
        # finish routes the head once with nothing current.
        for reader, outcome in _RELABEL_READS:
            with self.subTest(reading=reader.func.__name__, **reader.keywords):
                self.setUp()
                head, run = self.dies_unannounced()
                reads = reader(self, head)
                with reads.patching():
                    self.assertEqual(self.finalizes(head), outcome)
                self.finalizes(head)

                reads.assert_retired(run)
                self.assertIsNone(readings.pinned_records(self)[1])
                self.assert_routed_once(head)

    def test_a_raised_relabel_proves_a_successor(self) -> None:
        # Another road settles report 3 and a newer run bound to it as the
        # relabel is made, puts report 2 back, and the relabel raises: that
        # run is proved on its own binding behind the raise and invalidated
        # whole -- also where report 3 is put back right behind the reading
        # that proof starts from -- so putting report 3 back revives nothing,
        # and the next finish routes the head once with nothing current. So is
        # the run itself where another road blanked the attempt's base tip
        # instead, and put it back right behind that reading.
        for blanks, restores in _RAISED_RELABELS:
            with self.subTest(blanks=blanks, restores=restores):
                self.setUp()
                head, run = self.dies_unannounced()
                raises = _RaisesUnderTheRelabel(self, head, blanks=blanks)
                with (
                    patch.object(self.gh, "set_workflow_label", raises),
                    patch.object(_settled, "read_afresh", _RestoresBehindTheProof(self, raises, restores=restores)),
                ):
                    self.assertRaises(RuntimeError, self.finalizes, head)

                raises.assert_retired(run)
                self.assertIsNone(readings.pinned_records(self)[1])
                _writes(self, raises.settled, keeping={})
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
                self.assertIsNone(readings.pinned_records(self)[1])
                self.assert_routed_once(head)

    def test_a_restart_without_a_log_relabels_once(self) -> None:
        # The issue already wears `workflow:validating`, no audit log is
        # configured, and the finish dies at the relabel's record, at the
        # relabel behind it, or behind both; the process restarts with its
        # event tail gone and the landing is finished twice. Nothing is
        # relabelled twice: the route's relabel is made once, save where the
        # record landed and the relabel did not, which no later finish can
        # tell from one made.
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", None))
        for boundary, relabelled in _RESTARTS:
            with self.subTest(boundary=boundary.name):
                self.setUp()
                head = self._validates_then_dies(boundary)
                self.gh.recorded_events.clear()

                self.finalizes(head)
                self.finalizes(head)

                finished = (readings.relabels(self), readings.attempt(readings.pinned(self)))
                self.assertEqual(finished, (relabelled, readings.RETIRED))
                self.assert_made()

    def test_a_restart_reads_the_log_for_the_relabel(self) -> None:
        # The issue already wears `workflow:validating`, and the finish dies at
        # the relabel itself, its record landed ahead of it. The process
        # restarts with its event tail gone, and the audit log carries no
        # stage-entry event naming the head: the relabel is made once.
        logs = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", logs / "events.jsonl"))
        head = self._validates_then_dies(handoff.BEFORE_THE_RELABEL)
        entered = handoff.stage_entries(self.gh, self.issue.number)
        self.gh.recorded_events.clear()

        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        self.finalizes(head)

        entered += handoff.stage_entries(self.gh, self.issue.number)
        self.assertEqual(readings.relabels(self), readings.ROUTED * 2)
        self.assertEqual(tuple(entered), _ENTERED_TWICE)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def test_a_raised_relabel_takes_its_record_back(self) -> None:
        # The issue already wears `workflow:validating`, and the finish's
        # relabel raises behind its record: one that raised before it filed
        # anything takes the record back off before the error goes on, so the
        # next finish relabels once; one that landed, its stage-entry event
        # filed, and then raised keeps it, so the next finish relabels
        # nothing. Either way the route's relabel is made once.
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", None))
        for lands in (False, True):
            with self.subTest(landed=lands):
                self.setUp()
                self.gh.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
                head = self.lands_a_reviewed_rebase()
                answers = {"new": partial(_lands_then_raises, self.gh.set_workflow_label)} if lands else {
                    "side_effect": RuntimeError(_UNANSWERED),
                }
                with patch.object(self.gh, "set_workflow_label", **answers):
                    self.assertRaises(RuntimeError, self.finalizes, head, FinishRoad.PUBLICATION)

                kept = readings.pinned(self).get(readings.KEY_RELABELLED)
                self.assertEqual(kept, head if lands else None)
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
                self.assertEqual(readings.relabels(self), readings.ROUTED * 2)
                entered = handoff.stage_entries(self.gh, self.issue.number)
                self.assertEqual(tuple(entered), _ENTERED_TWICE)
                self.assertEqual(support.announced(self), [head])

    def _validates_then_dies(self, boundary: handoff.Boundary) -> str:
        """Put the issue on `workflow:validating`, land a reviewed rebase, and kill its finish at `boundary`; head."""
        self.gh.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finalizes, head, FinishRoad.PUBLICATION))
        return head


if __name__ == "__main__":
    unittest.main()
