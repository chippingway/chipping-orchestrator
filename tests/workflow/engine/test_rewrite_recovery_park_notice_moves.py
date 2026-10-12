# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A run settled for a landed head, under a park whose notice another road writes past, or whose record never lands.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. The next tick parks rather than route the head, and
while the park's notice is posted another road settles and reviews report 3 of
the head, the report the run was bound to replaced: under the park a finish
takes for want of room for the landing's report debt, which is decided on the
report records and refused over that move; or under a recovery park that keeps
the attempt behind a fetch and a reset that both failed, whose record keeps
the report as the comment then carries it -- over a run settled, or one only
captured and never settled. Either way the run is read moving before the tick
ends -- by the refused park, or by the park's record that adopted report 3,
handed to the proof taken once more behind the notice -- and invalidated or
abandoned whole, so putting report 2 back, even right behind that record and
before the proof, revives nothing.

And a checkout gone from disk under a label the refresh does not drive, which
the dispatcher's stranded park answers by retiring the run on the state that
park writes: the movement is recorded against the run in a write of its own
first, so a park record refused, or a process killed before it, leaves the run
read moving once the checkout and the label are put back.

Each time the head is then routed with nothing current, its notice said once,
the run never made again, and no developer launched.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedEdit, pinned_state_body
from orchestrator.workflow.engine import dispatch_guards, verification_settlement_state as _settlement
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    verification_report_fixture as _report,
)
from tests.workflow.interleaving import _RacesPastTheCall

_AWAITING = "awaiting_human"

_GIT = "_git_hardened"

# The report and review records report 3's settlement moves, as the pinned comment spells them.
_MOVED_RECORDS = (
    "developer_report_current",
    "developer_report_handoff",
    "review_subject",
    "review_returned_subject",
)

# Room on the pinned comment for the run's history entry and the park behind
# it, and short of the landing's report debt and the announcement it rides.
_SHORT_OF_THE_DEBT = 250

# How a park's record fails to land: GitHub refusing it, or the process killed ahead of it.
_RECORD_FAILURES = ("refused", "killed")

# A park's record: the edit that puts the park's flag on a comment that lacks it.
_BEFORE_THE_RECORD = handoff.Boundary(
    "before the park is recorded",
    "edit_pinned_state",
    lambda _issue, state, *, over: (
        bool(state.get(_AWAITING)) and not over.get(_AWAITING)
    ),
)


def _settles_a_later_report(case: support.CapturedRunCase, head: str, replaced: list) -> None:
    """Settle and review report 3 of `head` as another road would, keeping in `replaced` the records it moves."""
    pinned = readings.pinned(case)
    replaced.append({key: pinned.get(key) for key in _MOVED_RECORDS})
    case.state = case.gh.read_pinned_state(case.issue)
    _report.settles_report(case, 3, "Implemented the change and covered a base that moved twice.", head=head)
    case.gh.write_pinned_state(case.issue, case.state)


def _puts_back(case: support.CapturedRunCase, replaced: list) -> None:
    """Write the report and review records back as they stood before report 3 moved them, as `replaced` kept them."""
    state = case.gh.read_pinned_state(case.issue)
    for key, recorded in replaced[-1].items():
        state.set(key, recorded)
    case.gh.write_pinned_state(case.issue, state)


def _fills_short_of_the_debt(case: support.CapturedRunCase) -> None:
    """Fill the pinned comment to `_SHORT_OF_THE_DEBT` short of its limit, as another road's records would."""
    filled = case.gh.read_pinned_state(case.issue)
    filled.set("room_filler", "")
    room = MAX_PINNED_BODY - len(pinned_state_body(filled.data))
    filled.set("room_filler", "x" * (room - _SHORT_OF_THE_DEBT))
    case.gh.write_pinned_state(case.issue, filled)


def _refuses(original, *called, **options) -> subprocess.CompletedProcess:
    """`original` git, save a fetch of issue #7's branch or a reset, each failing as git does."""
    fetches = any("issue-7" in str(arg) for arg in called)
    if fetches or called[0] == "reset":
        return subprocess.CompletedProcess(called, 1, "", "refused")
    return original(*called, **options)


def _refusing(live, issue, state, *, over: dict):
    """`live`, the client's pinned edit, refused as moved where it is a park's record."""
    if _BEFORE_THE_RECORD.kills(issue, state, over=over):
        return PinnedEdit.MOVED
    return live(issue, state, over=over)


def _held_by_the_dispatcher(case: support.CapturedRunCase, *, refusing: bool = False) -> None:
    """Have the dispatcher's anchor hold answer `case`'s issue, a park's record refused where `refusing`."""
    label = case.gh.workflow_label(case.issue)
    state = case.gh.read_pinned_state(case.issue)
    edit = partial(_refusing, case.gh.edit_pinned_state) if refusing else case.gh.edit_pinned_state
    with patch.object(case.gh, "edit_pinned_state", edit):
        dispatch_guards._anchor_holds_the_tick(case.gh, case._spec, case.issue, label, state)


class ParkNoticeMoveTest(support.CapturedRunCase, unittest.TestCase):
    """A park leaves no run a report moved under, or a checkout left, for the next poll to take up as current."""

    def test_a_debt_park_refused_over_a_moved_report(self) -> None:
        # The debt park, decided on the report records, is refused over
        # report 3, and that refusal invalidates the run; report 2 put back
        # and room made, the head is routed with nothing current.
        head, settled = self._settles_then_dies()
        _fills_short_of_the_debt(self)
        replaced = self._posting_moves_the_report(head, self.recovers)

        self.assertFalse(readings.pinned(self).get(_AWAITING))
        self._assert_retired(settled)
        _puts_back(self, replaced)
        finish_moves.makes_room(self)
        self.recovers()

        self._assert_retired(settled)
        self._assert_routed(head)

    def test_a_kept_park_proves_behind_its_notice(self) -> None:
        # The park behind a fetch and a reset that failed keeps the attempt
        # and records report 3 as the comment carries it -- report 2 put back
        # right behind that record, before the proof, or only after the tick:
        # the run, settled or only captured, is invalidated or abandoned, and
        # once the park is continued the head is routed with nothing current.
        for captures, restoring in product((False, True), (False, True)):
            with self.subTest(captured=captures, restored_behind_the_record=restoring):
                self.setUp()
                head, run = self.captures() if captures else self._settles_then_dies()
                with patch.object(commands, _GIT, partial(_refuses, getattr(commands, _GIT))):
                    replaced = self._posting_moves_the_report(head, self.recovers, restoring=restoring)

                self.assertTrue(readings.pinned(self).get(_AWAITING))
                self._assert_retired(run, captured=captures)
                _puts_back(self, replaced)
                self.continues()
                self.recovers()
                self._assert_routed(head)

    def test_a_missing_checkout_park_that_never_lands(self) -> None:
        # The stranded park's record is refused, or the process is killed
        # ahead of it: the movement was recorded against the run first, so
        # the checkout and the label put back leave the run read moving, and
        # the head is routed with nothing current.
        for failing in _RECORD_FAILURES:
            with self.subTest(record=failing):
                self.setUp()
                head, settled = self._settles_then_dies()
                away = self._wt.parent / "checkout-away"
                self._wt.rename(away)
                self.issue.labels = [FakeLabel("workflow:resolving_conflict")]
                if failing == "killed":
                    handoff.dies_at(self.gh, _BEFORE_THE_RECORD, partial(_held_by_the_dispatcher, self))
                else:
                    _held_by_the_dispatcher(self, refusing=True)
                away.rename(self._wt)
                self.issue.labels = [FakeLabel(git_support.REVIEWING)]

                self.assertEqual(
                    (readings.pinned_records(self)[1], readings.pinned(self)[readings.KEY_REWRITE_BASE]),
                    (settled, None),
                )
                self.recovers()
                self._assert_retired(settled)
                self._assert_routed(head)

    def _settles_then_dies(self) -> tuple:
        """Land a reviewed rebase, settle its run, and kill its finish before the announcement; the head and the run."""
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        return head, readings.pinned_records(self)[1]

    def _posting_moves_the_report(self, head: str, finishing, *, restoring: bool = False) -> list:
        """Run `finishing` with report 3 of `head` settled behind the first issue-thread post; the records it moved.

        `restoring` puts them back right behind the park's record, before
        anything behind it reads the comment again.
        """
        replaced: list = []
        races = _RacesPastTheCall(self.gh.comment, 1, partial(_settles_a_later_report, self, head, replaced))
        edit = self.gh.edit_pinned_state
        if restoring:
            edit = _BEFORE_THE_RECORD.moving(edit, partial(_puts_back, self, replaced))
        with (
            patch.object(self.gh, "comment", races),
            patch.object(self.gh, "edit_pinned_state", edit),
        ):
            finishing()
        return replaced

    def _assert_retired(self, run, *, captured: bool = False) -> None:
        """`run` abandoned whole where it was only `captured`, else invalidated whole, its revision and binding kept.

        Behind the anchor's own evidence the rewrite invalidated, and run once.
        """
        if captured:
            self.assert_abandoned(run)
            return
        retired = (*git_support.invalidated(self), (run.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (run.revision, run.binding))
        self.assertEqual((self.runs(), self.developer.call_count), (1, 0))

    def _assert_routed(self, head: str) -> None:
        """`head` announced, relabelled, and its attempt retired once, nothing pending or current, nothing pushed."""
        self.assertEqual(readings.pinned_records(self)[:2], (None, None))
        self.assertEqual(support.announced(self), [head])
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        self.assertEqual(self.pushes.call_count, 0)


if __name__ == "__main__":
    unittest.main()
