# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A successor settled around a dormant finish's relabel, proved on its own binding and no other evidence's.

Direct finishes held to the dormant settled-evidence policy
(`settled_route_support`): issue #7's reviewed rebase, its run settled under
the anchor and its finish killed before its announcement, so the next finish
routes the head. Two successors another road settles bound to records of
their own:

- With the run taken off the comment, so nothing is current for the head, a
  newer run bound to the run's own records is settled as the relabel's
  recheck reads the comment, the base tip the attempt recorded its replay as
  made onto blanked for that one reading and put back behind it. That blank is
  movement under the newer run though nothing current was read before it:
  the newer run is invalidated whole, and the head is routed once with
  nothing current.
- On an issue already on `workflow:validating`, with no audit log, report 3
  and a newer run bound to it are settled as the relabel is made, which
  raises. The relabel's record is taken back off over report 2, so that edit
  is refused over report 3; the newer run stands on report 3 itself, so the
  movement off report 2 is none of its own, and it stays current.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import (
    rewrite_finish_rechecks as _rechecks,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled_support,
    settled_route_support as route,
    verification_report_fixture as _report,
)


def _writes(case, records: dict) -> dict:
    """Write `records` onto `case`'s comment as it stands; what they replaced."""
    state = case.gh.read_pinned_state(case.issue)
    replaced = {key: state.get(key) for key in records}
    for key, recorded in records.items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)
    return replaced


class _BlanksBesideASuccessor:
    """The relabel recheck's reading, the first time beside a newer run bound to `run`'s records and a blank tip."""

    def __init__(self, case, run) -> None:
        self._case = case
        self._run = run
        self._live = _rechecks.read_afresh
        self.successor = None

    def __call__(self, finish):
        """Read the comment afresh, the first time with the newer run settled and the tip blanked for it alone."""
        if self.successor is not None:
            return self._live(finish)
        self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=self._run.binding)
        tip = _writes(self._case, {readings.KEY_REWRITE_BASE: None})
        durable = self._live(finish)
        _writes(self._case, tip)
        return durable


def _succeeds_then_raises(case, run, settled: list, *_labelled, **_correlation) -> None:
    """The relabel, answered by another road settling report 3 and a newer run bound to it, then a raise."""
    head = run.binding.target.target_head
    case.state = case.gh.read_pinned_state(case.issue)
    subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)
    target = replace(run.binding.target, subject=subject.recorded())
    binding = replace(run.binding, target=target)
    settled.append(settled_support.records_a_newer_run(case, settles=True, binding=binding))
    raise RuntimeError("GitHub did not answer the relabel")


class RelabelSuccessorTest(route.SettledRouteCase, unittest.TestCase):
    """A successor settled around a dormant finish's relabel answers for its own binding alone."""

    def test_a_blank_tip_disproves_a_lone_successor(self) -> None:
        # Nothing is current for the head, and the recheck reads a newer run
        # bound to the run's records beside the base tip blanked, the tip put
        # back behind it: that run is invalidated whole, and the head is
        # routed once with nothing current.
        head, run = self._settles_then_dies()
        state = self.gh.read_pinned_state(self.issue)
        self.assertTrue(_settlement.retire_current_evidence(state))
        self.gh.write_pinned_state(self.issue, state)
        reads = _BlanksBesideASuccessor(self, run)
        with patch.object(_rechecks, "read_afresh", reads):
            self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

        history = readings.pinned_records(self)[2]
        self.assertEqual(history[-1], (reads.successor.receipt, readings.INVALIDATED))
        self.assertIsNone(readings.pinned_records(self)[1])
        self.assert_routed_once(head)

    def test_a_rollback_spares_a_valid_successor(self) -> None:
        # The issue already wears `workflow:validating`, and report 3 and a
        # newer run bound to it settle as the relabel is made, which raises:
        # the relabel's record, taken back off over report 2, is refused over
        # report 3 and stays, and the newer run, proved on report 3, stays
        # current.
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", None))
        self.gh.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
        head, run = self._settles_then_dies()
        settled: list = []
        raises = partial(_succeeds_then_raises, self, run, settled)
        with patch.object(self.gh, "set_workflow_label", raises):
            self.assertRaises(RuntimeError, self.finalizes, head)

        self.assertEqual(readings.pinned(self)[readings.KEY_RELABELLED], head)
        current = readings.pinned_records(self)[1]
        self.assertEqual(current.receipt, settled[0].receipt)

    def _settles_then_dies(self) -> tuple:
        """Land a reviewed rebase, settle its run, and kill its finish before its announcement; the head and the run."""
        head = self.lands_a_reviewed_rebase()
        published = partial(self.finalizes, head, FinishRoad.PUBLICATION)
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, published)
        return head, readings.pinned_records(self)[1]


if __name__ == "__main__":
    unittest.main()
