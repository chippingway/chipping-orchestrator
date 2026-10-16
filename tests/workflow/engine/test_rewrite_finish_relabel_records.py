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
relabel that raises, behind another road settling report 3 and a newer run
bound to it and then putting report 2 back, is proved again over the comment
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
from orchestrator.workflow.engine import rewrite_finish_rechecks as _rechecks
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


class _MovesUnderTheRecheck:
    """The relabel recheck's reading of the comment, report 3 of `head` settled ahead of it and put back behind it."""

    def __init__(self, case, head: str) -> None:
        self._case = case
        self._head = head
        self._live = _rechecks.read_afresh
        self._replaced: dict = {}

    def __call__(self, finish):
        """Read the comment afresh, the first time with report 3 settled for that one reading."""
        if self._replaced:
            return self._live(finish)
        case = self._case
        case.state = case.gh.read_pinned_state(case.issue)
        self._replaced = {key: case.state.get(key) for key in _MOVED_RECORDS}
        _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)
        durable = self._live(finish)
        _writes(case, self._replaced, keeping={})
        return durable


class _RaisesUnderTheRelabel:
    """The relabel, the first time answered by another road's newer run of `head` and a raise.

    That road settles report 3 and a run bound to it, kept as `successor`,
    keeps the records report 3 moved in `settled`, and puts report 2 back.
    """

    def __init__(self, case, head: str) -> None:
        self._case = case
        self._head = head
        self._live = case.gh.set_workflow_label
        self.settled: dict = {}
        self.successor = None

    def __call__(self, *labelled, **correlation):
        """Settle the newer run and put report 2 back, then raise as GitHub not answering; relabel after that."""
        if self.successor is not None:
            return self._live(*labelled, **correlation)
        case = self._case
        case.state = case.gh.read_pinned_state(case.issue)
        replaced = {key: case.state.get(key) for key in _MOVED_RECORDS}
        subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)
        earlier = readings.pinned_records(case)[1].binding
        bound = replace(earlier, target=replace(earlier.target, subject=subject.recorded()))
        self.successor = settled_support.records_a_newer_run(case, settles=True, binding=bound)
        _writes(case, replaced, keeping=self.settled)
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
        # report 2 is put back right behind that reading: the run is
        # invalidated whole before the relabel, and the head is routed once
        # with nothing current.
        head, run = self._settles_then_dies()
        with patch.object(_rechecks, "read_afresh", _MovesUnderTheRecheck(self, head)):
            self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

        retired = readings.pinned_records(self)[2][-1]
        self.assertEqual(retired, (run.receipt, readings.INVALIDATED))
        self.assertIsNone(readings.pinned_records(self)[1])
        self.assert_routed_once(head)

    def test_a_raised_relabel_proves_a_successor(self) -> None:
        # Another road settles report 3 and a newer run bound to it as the
        # relabel is made, puts report 2 back, and the relabel raises: that
        # run is proved on its own binding behind the raise and invalidated
        # whole, so putting report 3 back revives nothing, and the next
        # finish routes the head once with nothing current.
        head, run = self._settles_then_dies()
        raises = _RaisesUnderTheRelabel(self, head)
        with patch.object(self.gh, "set_workflow_label", raises):
            self.assertRaises(RuntimeError, self.finalizes, head)

        records = readings.pinned_records(self)
        moved = ((run.receipt, readings.SUPERSEDED), (raises.successor.receipt, readings.INVALIDATED))
        self.assertIsNone(records[1])
        self.assertEqual(records[2][-2:], moved)
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
        # relabel raises behind its record: the record is taken back off
        # before the error goes on, so the next finish relabels once.
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", None))
        self.gh.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
        head = self.lands_a_reviewed_rebase()
        with patch.object(self.gh, "set_workflow_label", side_effect=RuntimeError(_UNANSWERED)):
            self.assertRaises(RuntimeError, self.finalizes, head, FinishRoad.PUBLICATION)

        self.assertIsNone(readings.pinned(self).get(readings.KEY_RELABELLED))
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        self.assertEqual(readings.relabels(self), readings.ROUTED * 2)
        entered = handoff.stage_entries(self.gh, self.issue.number)
        self.assertEqual(tuple(entered), _ENTERED_TWICE)
        self.assertEqual(support.announced(self), [head])

    def _settles_then_dies(self) -> tuple:
        """Land a reviewed rebase, settle its run, and kill its finish before its announcement; the head and the run."""
        head = self.lands_a_reviewed_rebase()
        published = partial(self.finalizes, head, FinishRoad.PUBLICATION)
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, published)
        return head, readings.pinned_records(self)[1]

    def _validates_then_dies(self, boundary: handoff.Boundary) -> str:
        """Put the issue on `workflow:validating`, land a reviewed rebase, and kill its finish at `boundary`; head."""
        self.gh.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, boundary, partial(self.finalizes, head, FinishRoad.PUBLICATION))
        return head


if __name__ == "__main__":
    unittest.main()
