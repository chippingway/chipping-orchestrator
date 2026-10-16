# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Movement a dormant finish's relabel reads in its later windows, kept however soon what moved is put back.

Direct finishes held to the dormant settled-evidence policy
(`settled_route_support`): issue #7's reviewed rebase, its run settled under
the anchor. Two windows read the comment once more on the way to the relabel,
and another road moves a record right there and puts it back right behind:

- On an issue already on `workflow:validating`, a relabel that raises takes
  its own record back off, and report 3 settles right under the strict edit
  of that rollback, which is refused over it, report 2 put back behind. The
  movement that refusal read is the movement it is: the run is invalidated
  whole before the error goes on, and the next finish routes the head with
  nothing current.
- Report 3 settles as the relabel's recheck reads the comment, so the run is
  invalidated, and another road settles a newer run bound to report 3 in its
  place right as the comment is read afresh behind that invalidation, report
  2 put back for that one reading. That reading disproves the newer run on
  its own binding, so it is invalidated whole too, its provenance kept, and
  putting report 3 back revives nothing: the head is routed with nothing
  current. Where report 2 is put back right behind that first reading
  instead, and another road settles a newer run bound to it as the relabel
  is made, which raises, that run proves on its own readings: the movement
  read under the run is the run's alone, and the newer run stays current.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import rewrite_finish_rechecks as _rechecks
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled_support,
    settled_route_support as route,
    verification_report_fixture as _report,
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")


def _records_of(case) -> dict:
    """The report and review records `case`'s comment carries now."""
    pinned = readings.pinned(case)
    return {key: pinned.get(key) for key in _MOVED_RECORDS}


def _writes(case, records: dict) -> None:
    """Write `records` onto `case`'s comment as it stands."""
    state = case.gh.read_pinned_state(case.issue)
    for key, recorded in records.items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)


def _settles_report_three(case, head: str):
    """Settle report 3 of `head` and hand a reviewer it, as another road would; its subject."""
    case.state = case.gh.read_pinned_state(case.issue)
    subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)
    return subject


class _MovesUnderTheRollback:
    """The client's strict edit, the relabel record's rollback the first time raced by report 3 and put back."""

    def __init__(self, case, head: str) -> None:
        self._case = case
        self._head = head
        self._live = case.gh.edit_pinned_state
        self.answered = None

    def __call__(self, issue, state, *, over: dict, **options):
        """Answer the edit, the rollback of the relabel's record the first time under report 3."""
        rollback = over.get(readings.KEY_RELABELLED) == self._head
        rollback = rollback and self.answered is None
        if not rollback or state.get(readings.KEY_RELABELLED) is not None:
            return self._live(issue, state, over=over, **options)
        earlier = _records_of(self._case)
        _settles_report_three(self._case, self._head)
        self.answered = self._live(issue, state, over=over, **options)
        _writes(self._case, earlier)
        return self.answered


class _SucceedsBehindTheRecheck:
    """The recheck's readings of the comment: report 3 settled for the first, a newer run bound to it for the second.

    The second, the fresh reading behind the invalidation the first earns,
    carries that newer run beside report 2 -- the records as they stood when
    this was built -- put back for that one reading, report 3 put back right
    behind it. With no `successor`, report 2 is put back right behind the
    first reading instead, and the second is read as it stands.
    """

    def __init__(self, case, head: str, run, *, successor: bool = True) -> None:
        self._case = case
        self._head = head
        self._run = run
        self._settles = successor
        self._live = _rechecks.read_afresh
        self._readings = 0
        self._earlier = _records_of(case)
        self.successor = None

    def __call__(self, finish):
        """Read the comment afresh, racing the first two readings as above."""
        self._readings += 1
        if self._readings == 1:
            self._subject = _settles_report_three(self._case, self._head)
        if self._readings == 1 and not self._settles:
            durable = self._live(finish)
            _writes(self._case, self._earlier)
            return durable
        if self._readings != 2 or not self._settles:
            return self._live(finish)
        later = _records_of(self._case)
        target = replace(self._run.binding.target, subject=self._subject.recorded())
        self.successor = settled_support.records_a_newer_run(
            self._case, settles=True, binding=replace(self._run.binding, target=target),
        )
        _writes(self._case, self._earlier)
        durable = self._live(finish)
        _writes(self._case, later)
        return durable


def _raises_beside_a_valid_run(case, run, settled: list, *_labelled, **_correlation) -> None:
    """The relabel, answered by another road settling a newer run bound to `run`'s own records, then a raise."""
    settled.append(settled_support.records_a_newer_run(case, settles=True, binding=run.binding))
    raise RuntimeError("GitHub did not answer the relabel")


class RelabelWindowTest(route.SettledRouteCase, unittest.TestCase):
    """What a dormant finish's relabel reads in its later windows counts, however soon it is put back."""

    def test_a_refused_rollback_keeps_its_move(self) -> None:
        # The issue already wears `workflow:validating`, the relabel raises,
        # and report 3 settles under the strict edit taking the relabel's
        # record back off, which is refused over it: the run is invalidated
        # whole before the error goes on, and the next finish routes the head
        # with nothing current.
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", None))
        self.gh.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
        head = self.lands_a_reviewed_rebase()
        moves = _MovesUnderTheRollback(self, head)
        with (
            patch.object(self.gh, "edit_pinned_state", moves),
            patch.object(self.gh, "set_workflow_label", side_effect=RuntimeError("GitHub refused the relabel")),
        ):
            self.assertRaises(RuntimeError, self.finalizes, head, FinishRoad.PUBLICATION)

        self.assertIsNotNone(moves.answered)
        self.assertIsNone(readings.pinned_records(self)[1])
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        self.assertIsNone(readings.pinned_records(self)[1])

    def test_a_successor_behind_the_recheck_is_proved(self) -> None:
        # The recheck's first reading invalidates the run over report 3, and
        # the fresh reading behind that invalidation carries a newer run bound
        # to report 3 beside report 2: that run is invalidated whole on its
        # own binding, its revision and binding kept, and the head is routed
        # with nothing current once report 3 is back.
        head, run = self._settles_then_dies()
        reads = _SucceedsBehindTheRecheck(self, head, run)
        with patch.object(_rechecks, "read_afresh", reads):
            self.finalizes(head)
        self.finalizes(head)

        history = readings.pinned_records(self)[2]
        self.assertEqual(history[-2], (run.receipt, readings.INVALIDATED))
        self.assertEqual(history[-1], (reads.successor.receipt, readings.INVALIDATED))
        self.assertIsNone(readings.pinned_records(self)[1])
        self.assert_routed_once(head)


    def test_a_valid_successor_outlives_a_raise(self) -> None:
        # The recheck's reading invalidates the run over report 3, report 2
        # put back right behind it, and another road settles a newer run bound
        # to report 2 as the relabel is made, which then raises. That run
        # proves on its own readings: the movement read under the run ahead of
        # the relabel is the run's alone, so the newer run stays current.
        head, run = self._settles_then_dies()
        settled: list = []
        with (
            patch.object(_rechecks, "read_afresh", _SucceedsBehindTheRecheck(self, head, run, successor=False)),
            patch.object(self.gh, "set_workflow_label", partial(_raises_beside_a_valid_run, self, run, settled)),
        ):
            self.assertRaises(RuntimeError, self.finalizes, head)

        current, retired = readings.pinned_records(self)[1:]
        self.assertEqual(current.receipt, settled[0].receipt)
        self.assertEqual(retired[-1], (run.receipt, readings.INVALIDATED))

    def _settles_then_dies(self) -> tuple:
        """Land a reviewed rebase, settle its run, and kill its finish before its announcement; the head and the run."""
        head = self.lands_a_reviewed_rebase()
        published = partial(self.finalizes, head, FinishRoad.PUBLICATION)
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, published)
        return head, readings.pinned_records(self)[1]


if __name__ == "__main__":
    unittest.main()
