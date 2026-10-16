# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A recovery's relabel, held to the evidence it routes and made once whatever label the issue already wore.

The guarded recovery case (`guarded_recovery_support`): issue #7's reviewed
rebase, its run settled under the anchor and its finish killed before its
announcement, so the next tick's recovery finishes the route. Report 3
settled just as the relabel's recheck reads the comment afresh, report 2 put
back right behind that reading, is movement read under the run: the run is
invalidated whole before the relabel and the head routed once with nothing
current, putting report 2 back reviving nothing. And on an issue already on
`workflow:validating`, a finish lost right behind its relabel, before the
relabel's own record lands, comes back behind a restart with its event tail
gone: the audit log it configured carries the stage-entry event naming the
head, so neither the relabel nor that event is made twice.
"""
from __future__ import annotations

import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import rewrite_finish_rechecks as _rechecks
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    verification_report_fixture as _report,
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")


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
        state = case.gh.read_pinned_state(case.issue)
        for key, recorded in self._replaced.items():
            state.set(key, recorded)
        case.gh.write_pinned_state(case.issue, state)
        return durable


class RelabelReadsTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """What the recovery's relabel reads, and what it finds made, decide that relabel once."""

    def test_a_move_read_by_the_recheck_counts(self) -> None:
        # Report 3 settles as the relabel's recheck reads the comment, and
        # report 2 is put back right behind that reading: the run is
        # invalidated whole before the relabel, and the head is routed once
        # with nothing current.
        head, settled = self.settles_then_dies()
        with patch.object(_rechecks, "read_afresh", _MovesUnderTheRecheck(self, head)):
            self.recovers()

        records = readings.pinned_records(self)
        retired = records[2][-1]
        self.assertIsNone(records[1])
        self.assertEqual(retired, (settled.receipt, readings.INVALIDATED))
        self.assert_routed(head)

    def test_a_restart_finds_the_relabel_on_the_log(self) -> None:
        # The issue already wears `workflow:validating`, and the finish dies
        # right behind its relabel, before that relabel's record lands. The
        # process restarts with its event tail gone, and the audit log says
        # the relabel was made: no second relabel or stage-entry event.
        logs = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", logs / "events.jsonl"))
        self.gh.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_RELABEL_RECORD, partial(self.finishes, head))
        entered = handoff.stage_entries(self.gh, self.issue.number)
        self.gh.recorded_events.clear()

        self.recovers()
        self.recovers()

        entered += handoff.stage_entries(self.gh, self.issue.number)
        self.assertEqual(readings.relabels(self), readings.ROUTED * 2)
        self.assertEqual(entered, ["validating", "validating"])
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)


if __name__ == "__main__":
    unittest.main()
