# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A landed rewrite's settled run proved over the leased no-op a publication gate holds, ahead of the hold's write.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. The next tick's recovery reads the landing standing
with a transfer permission still outstanding beside it, so the landed road
receipts it through the permit-only leased no-op, and the publication gate
holds that no-op: the attempt is kept for a later tick, and the run is proved
again first (`rewrite_landing_retirement.retires_unproved`). The transfer's
own machinery -- how far it got, its permit, and the gate's answer -- is stood
in for; what is read back is the run, the attempt, and what the issue was told.

Where the issue was edited under the run, the run is invalidated whole and
putting the requirements back revives nothing; where nothing moved, it is kept
current and routed with the head once the gate lets a poll through. The
attempt stands while the gate holds, and the run is made once, with nothing
pushed or launched.

The hold's record lands over the comment read afresh: a newer transaction
recorded while the gate answers survives with its revision floor, and a newer
run settled beside report 3 is proved on its own readings. Behind the record
the run is proved once more, so a report settled at the record -- landed,
answer lost, or refused -- is read moving even where report 2 is put back.
"""
from __future__ import annotations

import contextlib
import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import transfer_permits as _transfer_permits, transfers as _transfers
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.workflow.engine import (
    report_commits as _commits,
    rewrite_recovery_parks as _parks,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.engine.rewrite_retry_permits_support import gated

_EDITED_BODY = "Also cover a base that moved twice."

# How the history records evidence a newer transaction for its head settled over.
_SUPERSEDED = "superseded"

# What the gate answered the permit-only no-op: held, with nothing pushed.
_HELD = _late_push._PushedCandidate(held=True)

# The guarded commit, read before any case stands in for it.
_LANDS = _commits.ReportCommit.lands

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = ("developer_report_current", "developer_report_handoff", "review_subject", "review_returned_subject")

# How the hold's record goes once report 3 settled ahead of it -- landed, its
# answer lost, or refused -- or right under its strict edit, which is refused
# over it, and whether report 2 is put back right behind it.
_UNDER_THE_EDIT = "under the edit"

# A record the tick staged since its reading, as a gate holding over a
# reading of its own does, so the hold's record has an edit to send.
_STAGED_BY_THE_GATE = "late_gate_hold"

_AT_THE_RECORD = (
    ("", True),
    ("lost", True),
    ("refused", False),
    (_UNDER_THE_EDIT, True),
)


@contextlib.contextmanager
def _gate_holds(publishes=None):
    """A transfer permission outstanding, its permit granted, and the gate -- `publishes`, where given -- holding."""
    with (
        patch.object(_transfers, "_carried_by", return_value=_Handoff.OUTSTANDING),
        patch.object(_transfer_permits, "_permits_the_publication", return_value=True),
        patch.object(_late_push, "_publishes", publishes or gated(_HELD)),
    ):
        yield


def _holds_beside_a_newer_run(case, recorded: list, *_called, **_options):
    """The gate's answer, held once another road recorded a newer transaction beside the run, kept in `recorded`."""
    recorded.append(guarded.records_a_newer_run(case))
    return _HELD


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
        if self._failing == _UNDER_THE_EDIT:
            staged.set(_STAGED_BY_THE_GATE, self._head)
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

    def _moves_under(self, live, issue, state, *, over: dict, **options):
        """`live`, the strict edit, with report 3 settled under it and report 2 put back right behind its answer."""
        self._settles()
        answered = live(issue, state, over=over, **options)
        self.puts_back()
        return answered


class GateHoldProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A gate holding the leased no-op keeps the attempt, its settled run proved first."""

    def test_a_moved_run_is_invalidated(self) -> None:
        # The issue is edited before the held poll: the run is invalidated
        # whole with the attempt kept; put back, a second held poll and the
        # poll the gate lets through revive nothing, the head routed once
        # with nothing current.
        head, settled = self.settles_then_dies()
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        with _gate_holds():
            self.recovers()
            self.assert_invalidated(settled)
            self._assert_held()
            self.issue.body = written
            self.recovers()

        self.assert_invalidated(settled)
        self._assert_held()
        self.recovers()

        self.assert_routed(head, current=None)
        retired = readings.pinned_records(self)[2]
        self.assertEqual(retired[-1], (settled.receipt, readings.INVALIDATED))

    def test_a_report_moved_at_the_record_is_read(self) -> None:
        # Report 3 settles behind the proof and ahead of the hold's record,
        # which lands it, loses its answer, or is refused -- or right under
        # its strict edit, refused over it; report 2 put back right behind a
        # record that carried report 3, or that edit, still leaves the run
        # moved. The run is invalidated whole with the attempt kept, and the
        # poll the gate lets through routes the head with nothing current.
        for failing, restores in _AT_THE_RECORD:
            with self.subTest(record=failing or "landed"):
                self.setUp()
                head, settled = self.settles_then_dies()
                around = _AroundTheHold(self, head, failing, restores=restores)
                with _gate_holds(), patch.object(_commits.ReportCommit, "lands", side_effect=around, autospec=True):
                    self.recovers()

                self.assert_invalidated(settled)
                self._assert_held()
                around.puts_back()
                self.recovers()
                self.assert_routed(head, current=None)

    def test_a_settled_successor_survives_the_hold(self) -> None:
        # Another road settles report 3 and a newer run bound to it ahead of
        # the hold's record, which takes both in: the newer run is proved on
        # its own readings rather than over report 2's move, kept current,
        # and routed with the head once the gate lets the poll through.
        head = self.settles_then_dies()[0]
        around = _AroundTheHold(self, head, successor=True)
        with _gate_holds(), patch.object(_commits.ReportCommit, "lands", side_effect=around, autospec=True):
            self.recovers()

        self.assertEqual(readings.pinned_records(self)[1], around.successor)
        self._assert_held()
        self.recovers()
        self.assert_routed(head, current=around.successor)

    def test_a_newer_run_survives_the_hold(self) -> None:
        # Another road records a newer transaction for the head while the gate
        # answers: the hold's record keeps it pending, with the revision floor
        # it raised, beside the settled run the proof held over it; the poll
        # the gate lets through settles it over that run and routes the head.
        head, settled = self.settles_then_dies()
        recorded: list = []
        with _gate_holds(partial(_holds_beside_a_newer_run, self, recorded)):
            self.recovers()

        newer = recorded[0]
        self.assertEqual(readings.pinned_records(self)[:2], (newer, settled))
        self.assertEqual(readings.pinned(self)[readings.KEY_REVISION_FLOOR], newer.revision)
        self._assert_held()
        self.recovers()

        settles = readings.pinned_records(self)
        self.assert_routed(head, current=settles[1])
        self.assertEqual(settles[1].receipt, newer.receipt)
        self.assertEqual(settles[2][-1], (settled.receipt, _SUPERSEDED))

    def test_an_unmoved_run_is_kept(self) -> None:
        # Nothing moved: every held poll keeps the run current exactly as it
        # settled, and the poll the gate lets through routes the head with it.
        head, settled = self.settles_then_dies()
        with _gate_holds():
            self.recovers()
            self.recovers()

        self.assertEqual(readings.pinned_records(self)[:2], (None, settled))
        self._assert_held()
        self.recovers()

        self.assert_routed(head, current=settled)

    def _assert_held(self) -> None:
        """The attempt standing on its anchor, unparked, with nothing announced, relabelled, or made again."""
        parked, anchor = self.pinned_fields(guarded.AWAITING, readings.KEY_PENDING_PUSH)
        self.assertEqual((bool(parked), anchor), (False, self.anchor))
        self.assertEqual(support.announced(self), [])
        self.assertEqual(readings.relabels(self), ())
        self.assert_made_once()


if __name__ == "__main__":
    unittest.main()
