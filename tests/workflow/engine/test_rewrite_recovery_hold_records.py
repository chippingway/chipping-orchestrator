# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A dormant guarded recovery hold, its settled run proved first and once more behind its own record.

The guarded recovery case (`guarded_recovery_support`): issue #7's rebased
head reviewed, its run settled under the anchor, and the finish killed before
its announcement, so the attempt stands. No recovery road records a
publication gate's hold through the guarded `HOLD` yet, so a case hands the
recovery context read off the comment straight to the dormant hold
(`rewrite_recovery_parks.lands_a_hold`), as a gate that held a recovery's
push would: the run is proved first, and only what the tick staged since its
reading lands, over the comment read afresh.

A newer transaction recorded before the record survives it with its revision
floor, and a newer run settled beside report 3 is proved on its own readings.
Behind the record the run is proved once more, so a report settled at the
record -- landed, answer lost, or refused -- is read moving even where report
2 is put back, and so is the base tip the attempt recorded its replay as made
onto, blanked right under the record's strict edit and put back behind it.
Where nothing moved the run is kept current. The attempt stands behind every
hold, the run is made once with nothing pushed or launched, and the poll a
later tick makes routes the head over whatever the hold left current.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import (
    report_commits as _commits,
    rewrite_recovery_parks as _parks,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled_support,
    verification_report_fixture as _report,
)

# How the history records evidence a newer transaction for its head settled over.
_SUPERSEDED = "superseded"

# The guarded commit, read before any case stands in for it.
_LANDS = _commits.ReportCommit.lands

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# How the hold's record goes once report 3 settled ahead of it -- landed, its
# answer lost, or refused -- or right under its strict edit, which is refused
# over it, and whether report 2 is put back right behind it.
_UNDER_THE_EDIT = "under the edit"

# The base tip, rather than report 3, moved under that edit: blanked as a
# reset is recorded, and put back right behind the edit's refusal.
_TIP_UNDER_THE_EDIT = "the tip under the edit"

# A record the tick staged since its reading, as a gate holding over a
# reading of its own does, so the hold's record has an edit to send -- one
# that fails as a case asks.
_STAGED_BY_THE_GATE = "late_gate_hold"

_AT_THE_RECORD = (
    ("", True),
    ("lost", True),
    ("refused", False),
    (_UNDER_THE_EDIT, True),
    (_TIP_UNDER_THE_EDIT, True),
)


def _settles_a_successor(case, subject):
    """Settle a newer run bound to report `subject` over `case.state`, as another road would; now current."""
    earlier = _settlement.read_current_evidence(case.state)
    target = replace(earlier.binding.target, subject=subject.recorded())
    binding = replace(earlier.binding, target=target)
    pending = _record_state.mint_pending_evidence(case.state, case.issue.number, binding, case.source.commands)
    case.assertTrue(_record_state.record_pending_evidence(case.state, pending))
    artifact = case.gh.publish_verification_artifact(case.pull_request, pending.artifact)
    case.state = _settlement.settled_state(case.state, pending, artifact.landed_id, git_support.REVIEWING)
    return _settlement.read_current_evidence(case.state)


class _AroundTheHold:
    """The guarded commit, report 3 of `head` settled ahead of a hold's record, which meets `failing` ("" lands).

    `restores` puts report 2 back right behind the record; `successor` settles
    a newer run bound to report 3 beside it, kept as `successor`.
    """

    def __init__(self, case, head: str, failing: str = "", *, restores: bool = False, successor: bool = False) -> None:
        self._case = case
        self._head = head
        self._failing = failing
        self._restores = restores
        self._replaced: dict = {}
        self.successor = successor

    def __call__(self, commit, staged, write):
        if write is not _parks.HOLD or self._replaced:
            return _LANDS(commit, staged, write)
        case = self._case
        if self._failing:
            staged.set(_STAGED_BY_THE_GATE, self._head)
        if self._failing in {_UNDER_THE_EDIT, _TIP_UNDER_THE_EDIT}:
            with patch.object(case.gh, "edit_pinned_state", partial(self._moves_under, case.gh.edit_pinned_state)):
                return _LANDS(commit, staged, write)
        self._settles()
        failures = getattr(case.gh.pinned_failures, self._failing) if self._failing else set()
        failures.add(case.issue.number)
        landed = _LANDS(commit, staged, write)
        failures.discard(case.issue.number)
        if self._restores:
            self.puts_back()
        return landed

    def puts_back(self) -> None:
        """Write the report and review records back as they stood before report 3 moved them."""
        state = self._case.gh.read_pinned_state(self._case.issue)
        for key, recorded in self._replaced.items():
            state.set(key, recorded)
        self._case.gh.write_pinned_state(self._case.issue, state)

    def _settles(self) -> None:
        """Settle report 3 -- and a newer run bound to it, where `successor` -- keeping what it moved."""
        case = self._case
        pinned = readings.pinned(case)
        self._replaced = {key: pinned.get(key) for key in _MOVED_RECORDS}
        case.state = case.gh.read_pinned_state(case.issue)
        subject = _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        if self.successor:
            self.successor = _settles_a_successor(case, subject)
        case.gh.write_pinned_state(case.issue, case.state)

    def _blanks(self) -> None:
        """Blank the base tip the attempt recorded its replay as made onto, keeping it to put back."""
        case = self._case
        durable = case.gh.read_pinned_state(case.issue)
        self._replaced = {readings.KEY_REWRITE_BASE: durable.get(readings.KEY_REWRITE_BASE)}
        durable.set(readings.KEY_REWRITE_BASE, None)
        case.gh.write_pinned_state(case.issue, durable)

    def _moves_under(self, live, issue, state, *, over: dict, **options):
        """`live`, the strict edit, with report 3 settled -- or the tip blanked -- under it and put back behind it."""
        if self._failing == _TIP_UNDER_THE_EDIT:
            self._blanks()
        else:
            self._settles()
        answered = live(issue, state, over=over, **options)
        self.puts_back()
        return answered


def _assert_routed(case, head: str, current=None) -> None:
    """`head` announced once and routed, its attempt retired, `current` current with nothing pending; run once."""
    case.assert_recovered(head)
    case.assertEqual(readings.pinned_records(case)[:2], (None, current))
    case.assert_made_once()


class HoldRecordTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A recovery hold keeps the attempt, its settled run proved first and behind the record it lands."""

    def test_a_report_moved_at_the_record_is_read(self) -> None:
        # Report 3 settles behind the proof and ahead of the hold's record,
        # which lands it, loses its answer, or is refused -- or right under
        # its strict edit, refused over it; report 2 put back right behind a
        # record that carried report 3, or that edit, still leaves the run
        # moved -- and so does the base tip blanked right under that edit and
        # put back behind it. The run is invalidated whole with the attempt
        # kept, and the next poll routes the head with nothing current.
        for failing, restores in _AT_THE_RECORD:
            with self.subTest(record=failing or "landed"):
                self.setUp()
                head, settled = self.settles_then_dies()
                around = _AroundTheHold(self, head, failing, restores=restores)
                with patch.object(_commits.ReportCommit, "lands", side_effect=around, autospec=True):
                    self._holds()

                self.assert_invalidated(settled)
                self._assert_held()
                around.puts_back()
                self.recovers()
                _assert_routed(self, head)

    def test_a_settled_successor_survives_the_hold(self) -> None:
        # Another road settles report 3 and a newer run bound to it ahead of
        # the hold's record, which takes both in: the newer run is proved on
        # its own readings rather than over report 2's move, kept current,
        # and routed with the head by the next poll.
        head = self.settles_then_dies()[0]
        around = _AroundTheHold(self, head, successor=True)
        with patch.object(_commits.ReportCommit, "lands", side_effect=around, autospec=True):
            self._holds()

        self.assertEqual(readings.pinned_records(self)[1], around.successor)
        self._assert_held()
        self.recovers()
        _assert_routed(self, head, around.successor)

    def test_a_successor_moved_back_is_invalidated(self) -> None:
        # Another road settles report 3 and a newer run bound to it ahead of
        # the hold's record -- which lands it, loses its answer, or is refused
        # -- then puts report 2 back right behind it: the newer run is the
        # evidence the proof behind the record takes, on its own binding, and
        # is invalidated whole over report 2 rather than left current.
        for failing in ("", "lost", "refused"):
            with self.subTest(record=failing or "landed"):
                self.setUp()
                head = self.settles_then_dies()[0]
                around = _AroundTheHold(self, head, failing, restores=True, successor=True)
                with patch.object(_commits.ReportCommit, "lands", side_effect=around, autospec=True):
                    self._holds()

                records = readings.pinned_records(self)
                retired = records[2][-1]
                self.assertIsNone(records[1])
                self.assertEqual(retired, (around.successor.receipt, readings.INVALIDATED))
                self._assert_held()

    def test_a_newer_run_survives_the_hold(self) -> None:
        # Another road records a newer transaction for the head after the
        # tick read the comment: the hold's record keeps it pending, with the
        # revision floor it raised, beside the settled run the proof kept;
        # the next poll settles it over that run and routes the head.
        head, settled = self.settles_then_dies()
        context = guarded.recovery_context(self)
        newer = settled_support.records_a_newer_run(self)
        _parks.lands_a_hold(context)

        self.assertEqual(readings.pinned_records(self)[:2], (newer, settled))
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], newer.revision)
        self._assert_held()
        self.recovers()

        settles = readings.pinned_records(self)
        _assert_routed(self, head, settles[1])
        self.assertEqual(settles[1].receipt, newer.receipt)
        self.assertEqual(settles[2][-1], (settled.receipt, _SUPERSEDED))

    def test_an_unmoved_run_is_kept(self) -> None:
        # Nothing moved: every hold keeps the run current exactly as it
        # settled, and the next poll routes the head with it.
        head, settled = self.settles_then_dies()
        self._holds()
        self._holds()

        self.assertEqual(readings.pinned_records(self)[:2], (None, settled))
        self._assert_held()
        self.recovers()

        _assert_routed(self, head, settled)

    def _holds(self) -> None:
        """Hand the recovery context read off the comment as it stands to the dormant guarded hold."""
        _parks.lands_a_hold(guarded.recovery_context(self))

    def _assert_held(self) -> None:
        """The attempt standing on its anchor, unparked, with nothing announced, relabelled, or made again."""
        parked, anchor = self.pinned_fields(guarded.AWAITING, readings.KEY_PENDING_PUSH)
        self.assertEqual((bool(parked), anchor), (False, self.anchor))
        self.assertEqual(support.announced(self), [])
        self.assertEqual(readings.relabels(self), ())
        self.assert_made_once()


if __name__ == "__main__":
    unittest.main()
