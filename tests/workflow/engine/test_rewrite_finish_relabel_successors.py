# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A successor settled around a finish's relabel, proved on its own binding and no other evidence's.

Direct finishes of the landing (`settled_route_support`): issue #7's reviewed
rebase, its run settled under the anchor and its finish killed before its
announcement, so the next finish routes the head. Four successors another road
settles bound to records of their own:

- With the run taken off the comment, so nothing is current for the head, a
  newer run bound to the run's own records is settled as the relabel's
  recheck reads the comment, the base tip the attempt recorded its replay as
  made onto blanked for that one reading and put back behind it. That blank is
  movement under the newer run though nothing current was read before it:
  the newer run is invalidated whole, and the head is routed once with
  nothing current. Where the same newer run and blank race the strict edit of
  the relabel's own record instead, which is refused over them, the newer run
  is invalidated whole by that refused finish all the same, and the next
  finish routes the head once with nothing current.
- On an issue already on `workflow:validating`, with no audit log, report 3
  and a newer run bound to it are settled as the relabel is made, which
  raises. The relabel's record is taken back off over report 2, so that edit
  is refused over report 3; the newer run stands on report 3 itself, so the
  movement off report 2 is none of its own, and it stays current.
- Report 3 settles as the relabel's recheck reads the comment, report 2 put
  back right behind it, so the run is invalidated over report 3, and a newer
  run bound to the run's own records settles right ahead of the fresh reading
  behind that invalidation, which takes it in. An operator's note left under
  the retirement then refuses it: the movement read under the run is none of
  the newer run's, and it stays current. Where that newer run settles beside
  report 3 once more and bound to it instead, report 2 put back right behind
  that fresh reading, the tick holds it beside report 2's records; report 3
  put back right under the strict edit of the relabel's record refuses that
  edit, and the fresh reading the record was derived over -- the newer run
  beside report 2 -- read it off its own binding: it is invalidated whole,
  and the next finish routes the head once with nothing current. So it is
  where report 3 is put back right behind that edit instead, which lands --
  its answer lost or not -- the record it made of the comment reading the
  newer run off its own binding, and where that edit will not read the
  comment, the fresh reading it was prepared over reading it so.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    rewrite_finish_rechecks as _rechecks,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    settled_finish_support as settled_support,
    settled_route_support as route,
    verification_report_fixture as _report,
)

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_REPORT_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# What report 3 says.
_REPORT_THREE = "Covered a base that moved twice as well."

# A field no binding rests on, as an operator's note under the retirement leaves it.
_NOTED = MappingProxyType({"operator_note": "Checked the rebase by hand."})


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

    def __init__(self, case, run, live) -> None:
        self._case = case
        self._run = run
        self._live = live
        self.successor = None

    def __call__(self, finish):
        """Read the comment afresh, the first time with the newer run settled and the tip blanked for it alone."""
        if self.successor is not None:
            return self._live(finish)
        return self._races(finish)

    def _races(self, *call, **options):
        """Answer `call` with the newer run settled and the tip blanked for it alone, the tip put back behind it."""
        self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=self._run.binding)
        tip = _writes(self._case, {readings.KEY_REWRITE_BASE: None})
        answered = self._live(*call, **options)
        _writes(self._case, tip)
        return answered


class _RefusesBesideASuccessor(_BlanksBesideASuccessor):
    """The client's strict edit, the relabel's record the first time raced as the recheck's reading is above."""

    def __call__(self, issue, state, *, over: dict, **options):
        """Answer the edit, the first one sending the relabel's record raced by the newer run and the blank tip."""
        relabel = state.get(readings.KEY_RELABELLED) == self._run.binding.target.target_head
        if self.successor is not None or not relabel:
            return self._live(issue, state, over=over, **options)
        return self._races(issue, state, over=over, **options)


class _AdoptsBehindTheRecheck:
    """A newer run taken in behind the run's invalidation, then a write of the route raced.

    The recheck's first reading is over report 3, report 2 put back right
    behind it, and the second -- the fresh reading behind the run's
    invalidation -- takes in a newer run: bound to `run`'s own records and
    settled right ahead of it, the attempt's first retirement then raced by an
    operator's note no binding rests on; or, `beside_report_three`, settled
    beside report 3 once more and bound to it, report 2 put back right behind
    that reading too, and report 3 right under the strict edit of the
    relabel's record.
    """

    def __init__(self, case, run, *, beside_report_three: bool = False) -> None:
        self._case = case
        self._run = run
        self._beside = beside_report_three
        self._read = _rechecks.read_afresh
        self._edit = case.gh.edit_pinned_state
        self._readings = 0
        self._later: dict = {}
        self.successor = None
        self.answered = None

    def reads(self, finish):
        """Read the comment afresh, racing the first two readings as above."""
        self._readings += 1
        if self._readings == 1 or (self._readings == 2 and self._beside):
            return self._reads_report_three(finish)
        if self._readings == 2:
            self.successor = settled_support.records_a_newer_run(self._case, settles=True, binding=self._run.binding)
        return self._read(finish)

    def edits(self, issue, state, *, over: dict, **options):
        """Answer the edit, the first one making the record raced -- the relabel's, or the retirement -- raced."""
        raced = readings.KEY_RELABELLED if self._beside else readings.KEY_PENDING_PUSH
        unset = state.get(raced) is None
        if unset == (over.get(raced) is None) or self.answered is not None:
            return self._edit(issue, state, over=over, **options)
        _writes(self._case, self._later if self._beside else _NOTED)
        self.answered = self._edit(issue, state, over=over, **options)
        return self.answered

    def _reads_report_three(self, finish):
        """Read the comment afresh over report 3, settled right ahead of it, and put report 2 back behind it.

        The second reading, beside report 3, settles the newer run bound to it there too.
        """
        case = self._case
        case.state = case.gh.read_pinned_state(case.issue)
        earlier = {key: case.state.get(key) for key in _REPORT_RECORDS}
        subject = _report.settles_report(case, 3, _REPORT_THREE, head=self._run.binding.target.target_head)
        case.gh.write_pinned_state(case.issue, case.state)
        if self._readings == 2:
            target = replace(self._run.binding.target, subject=subject.recorded())
            self.successor = settled_support.records_a_newer_run(
                case, settles=True, binding=replace(self._run.binding, target=target),
            )
        durable = self._read(finish)
        self._later = _writes(case, earlier)
        return durable


class _LandsBesideTheAdopted(_AdoptsBehindTheRecheck):
    """`_AdoptsBehindTheRecheck` beside report 3, report 3 put back right behind the relabel record's edit instead.

    That edit lands over the newer run beside report 2 -- its answer lost
    where `answer` is `PinnedEdit.UNCONFIRMED` -- so the record it made of the
    comment is the reading that disproves the newer run; or, `answer`
    `PinnedEdit.UNREAD`, it would not read the comment and sends nothing,
    report 3 put back right under it, so only the fresh reading it was
    prepared over read the newer run beside report 2.
    """

    def __init__(self, case, run, *, answer: PinnedEdit | None = None) -> None:
        super().__init__(case, run, beside_report_three=True)
        self._answer = answer

    def edits(self, issue, state, *, over: dict, **options):
        """Answer the relabel record's first edit as `answer` has it, report 3 put back right behind it."""
        records = state.get(readings.KEY_RELABELLED) != over.get(readings.KEY_RELABELLED)
        if not records or self.answered is not None:
            return self._edit(issue, state, over=over, **options)
        if self._answer is not PinnedEdit.UNREAD:
            self.answered = self._edit(issue, state, over=over, **options)
        _writes(self._case, self._later)
        self.answered = self._answer or self.answered
        return self.answered


# How the strict edit of the relabel's record meets report 3 put back around
# it, beside a newer run the recheck took in: right under it, refusing it or
# not reading the comment at all; or right behind it, landed or with its answer
# lost -- and what the finish comes to.
_AROUND_THE_RECORD = (
    (partial(_AdoptsBehindTheRecheck, beside_report_three=True), FinishOutcome.REFUSED),
    (partial(_LandsBesideTheAdopted, answer=PinnedEdit.UNREAD), FinishOutcome.REFUSED),
    (partial(_LandsBesideTheAdopted), FinishOutcome.ROUTED),
    (partial(_LandsBesideTheAdopted, answer=PinnedEdit.UNCONFIRMED), FinishOutcome.UNCONFIRMED),
)


def _succeeds_then_raises(case, run, settled: list, *_labelled, **_correlation) -> None:
    """The relabel, answered by another road settling report 3 and a newer run bound to it, then a raise."""
    head = run.binding.target.target_head
    case.state = case.gh.read_pinned_state(case.issue)
    subject = _report.settles_report(case, 3, _REPORT_THREE, head=head)
    case.gh.write_pinned_state(case.issue, case.state)
    target = replace(run.binding.target, subject=subject.recorded())
    binding = replace(run.binding, target=target)
    settled.append(settled_support.records_a_newer_run(case, settles=True, binding=binding))
    raise RuntimeError("GitHub did not answer the relabel")


class RelabelSuccessorTest(route.SettledRouteCase, unittest.TestCase):
    """A successor settled around a finish's relabel answers for its own binding alone."""

    def test_a_blank_tip_disproves_a_lone_successor(self) -> None:
        # Nothing is current for the head, and the recheck reads a newer run
        # bound to the run's records beside the base tip blanked, the tip put
        # back behind it: that run is invalidated whole, and the head is
        # routed once with nothing current.
        head, outcome, successor = self._races_a_lone_successor(_rechecks, "read_afresh", _BlanksBesideASuccessor)
        self.assertEqual(outcome, FinishOutcome.ROUTED)
        self._assert_disproved(head, successor)

    def test_a_refused_record_disproves_a_successor(self) -> None:
        # The same newer run and blank tip race the strict edit of the
        # relabel's record, which is refused over them: the refused finish
        # invalidates that run whole, and the next finish routes the head
        # once with nothing current.
        head, outcome, successor = self._races_a_lone_successor(self.gh, "edit_pinned_state", _RefusesBesideASuccessor)
        self.assertEqual(outcome, FinishOutcome.REFUSED)
        history = readings.pinned_records(self)[2]
        self.assertEqual(history[-1], (successor.receipt, readings.INVALIDATED))
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        self._assert_disproved(head, successor)

    def test_a_rollback_spares_a_valid_successor(self) -> None:
        # The issue already wears `workflow:validating`, and report 3 and a
        # newer run bound to it settle as the relabel is made, which raises:
        # the relabel's record, taken back off over report 2, is refused over
        # report 3 and stays, and the newer run, proved on report 3, stays
        # current.
        self.enterContext(patch.object(config, "EVENT_LOG_PATH", None))
        self.gh.set_workflow_label(self.issue, WorkflowLabel.VALIDATING)
        head, run = self.dies_unannounced()
        settled: list = []
        raises = partial(_succeeds_then_raises, self, run, settled)
        with patch.object(self.gh, "set_workflow_label", raises):
            self.assertRaises(RuntimeError, self.finalizes, head)

        self.assertEqual(readings.pinned(self)[readings.KEY_RELABELLED], head)
        current = readings.pinned_records(self)[1]
        self.assertEqual(current.receipt, settled[0].receipt)

    def test_a_valid_successor_outlives_a_refusal(self) -> None:
        # The recheck invalidates the run over report 3, report 2 put back
        # right behind it, and the fresh reading behind that invalidation
        # takes in a newer run bound to report 2; an operator's note then
        # refuses the retirement. The movement read under the run is the
        # run's alone, so the newer run stays current.
        head, run = self.dies_unannounced()
        races = _AdoptsBehindTheRecheck(self, run)
        with (
            patch.object(_rechecks, "read_afresh", races.reads),
            patch.object(self.gh, "edit_pinned_state", races.edits),
        ):
            self.assertEqual(self.finalizes(head), FinishOutcome.REFUSED)

        self.assertIsNotNone(races.answered)
        current, retired = readings.pinned_records(self)[1:]
        self.assertEqual(current.receipt, races.successor.receipt)
        self.assertEqual(retired[-1], (run.receipt, readings.INVALIDATED))

    def test_a_fresh_reading_disproves_an_adopted_one(self) -> None:
        # The fresh reading behind the run's invalidation takes in a newer
        # run bound to report 3, report 2 put back right behind it, and report
        # 3 is put back right under the strict edit of the relabel's record,
        # which is refused over it or will not read the comment -- or right
        # behind that edit, which lands, its answer lost or not: the fresh
        # reading that record was derived
        # over, or the record it made of the comment, read the newer run off
        # its own binding, so it is invalidated whole, and the head is routed
        # once with nothing current.
        for racer, outcome in _AROUND_THE_RECORD:
            with self.subTest(racer=racer.func.__name__, **racer.keywords):
                self.setUp()
                head, run = self.dies_unannounced()
                races = racer(self, run)
                with (
                    patch.object(_rechecks, "read_afresh", races.reads),
                    patch.object(self.gh, "edit_pinned_state", races.edits),
                ):
                    self.assertEqual(self.finalizes(head), outcome)

                self.assertIsNotNone(races.answered)
                self.assertIsNone(readings.pinned_records(self)[1])
                self.finalizes(head)
                self._assert_disproved(head, run, races.successor)

    def _races_a_lone_successor(self, owner, name: str, racer: type) -> tuple:
        """Retire the run and finish its head, `owner`'s `name` raced by `racer`; the head, outcome, and newer run."""
        head, run = self.dies_unannounced()
        state = self.gh.read_pinned_state(self.issue)
        self.assertTrue(_settlement.retire_current_evidence(state))
        self.gh.write_pinned_state(self.issue, state)
        races = racer(self, run, getattr(owner, name))
        with patch.object(owner, name, races):
            outcome = self.finalizes(head)
        return head, outcome, races.successor

    def _assert_disproved(self, head: str, *runs) -> None:
        """`runs` the last invalidated, in order, with nothing current, and `head` routed once."""
        history = readings.pinned_records(self)[2]
        retired = [(run.receipt, readings.INVALIDATED) for run in runs]
        self.assertEqual(list(history[-len(runs):]), retired)
        self.assertIsNone(readings.pinned_records(self)[1])
        self.assert_routed_once(head)


if __name__ == "__main__":
    unittest.main()
