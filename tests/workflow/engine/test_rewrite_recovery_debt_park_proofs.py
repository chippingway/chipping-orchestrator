# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run the finish's own debt park keeps, proved whole before the park and again behind its notice.

The real-git finish case (`rewrite_verification_recovery_support`), every
finish -- handed over directly or reached by a refresh -- held to the dormant
settled-evidence policy (`settled_finish_support`): issue #7's rebased head
reviewed and its run captured by a finish that died posting its artifact, and
the pinned comment then left without room for the landing's report debt, so
the recovery's finish parks for that debt and keeps the run for the reply that
brings the route back. The run's binding is proved again whole -- the report
it answers for re-read at its location -- ahead of the park and again behind
its notice, so the report edited before the tick and put back while the notice
is posted, or edited while the notice is posted -- its post answered or
raising -- and put back behind the tick, has the run abandoned whole: room
made and any park answered, the head is routed with nothing current.

The issue's requirements edited before the tick have the run abandoned ahead
of the park, and another finish settles that very run, the edit put back,
while the abandonment's own write is asked: the settlement is invalidated over
the edit already read and the debt parked -- or, the comment full, the movement
is recorded by the base tip blanked and the settlement invalidated once room
is made -- and a newer run another road settled over it under its own receipt
is left as it stands. The run is made once, and nothing is pushed or launched.

The policy every road selects proves no captured run whole ahead of the park:
with the report edited before the tick and put back while the notice is
posted, its park keeps the run recorded, where the settled-evidence policy
abandons it.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.workflow.engine import report_settlement_state as _report_settlement, verification_records as _records
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    settled_finish_support as settled,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a base that moved twice."

# Room on the pinned comment for the run's history entry and the park behind
# it, and short of the landing's report debt and the announcement it rides.
_SHORT_OF_THE_DEBT = 250

# When the report the run answers for is edited: before the tick, put back
# while the debt park's notice is posted; or while that notice is posted, put
# back behind the tick -- and whether the notice's post raises, which leaves
# nothing parked.
_REPORT_EDITS = (
    ("before the park", True, False),
    ("under the notice", False, False),
    ("under a raised notice", False, True),
)


def _report_comment(case):
    """The comment the report `case`'s issue last settled landed as."""
    location = _report_settlement.read_current_report(case.gh.read_pinned_state(case.issue)).location
    return next(posted for posted in case.pull_request.issue_comments if posted.id == location.comment_id)


def _loses_the_answer(moves) -> None:
    """Make `moves`, then lose the answer of the request it was made behind."""
    moves()
    raise RuntimeError("the answer was lost")


def _abandoning(state, over: dict) -> bool:
    """Whether a pinned-comment edit drops a transaction the comment it is made over still carries pending."""
    drops = state.get(_records.PENDING_EVIDENCE) is None
    return drops and over.get(_records.PENDING_EVIDENCE) is not None


class _DebtParkCase(guarded.GuardedRecoveryCase):
    """A captured run the recovery's finish parks for the landing's debt, its report edited around the park."""

    def parks_over_an_edit(self, *, before: bool, raises: bool) -> None:
        """Recover the debt's park over the report edited `before` the tick or under the notice, which `raises`.

        An edit made before the tick is put back while the notice is posted;
        the report is put back behind the tick in any case. The debt is parked
        unless the notice's post raised.
        """
        finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
        posted = _report_comment(self)
        written = posted.body
        edits = partial(setattr, posted, "body", f"{written}\nEdited by hand.")
        noticed = partial(setattr, posted, "body", written) if before else edits
        if before:
            edits()
        if raises:
            noticed = partial(_loses_the_answer, noticed)
        with patch.object(self.gh, "comment", _RacesPastTheCall(self.gh.comment, 1, noticed)):
            self.recovers()
        posted.body = written
        parked = self.pinned_fields(guarded.AWAITING)[0]
        self.assertEqual(bool(parked), not raises)


class DebtParkPolicyTest(_DebtParkCase, unittest.TestCase):
    """Only a finish held to the settled-evidence policy proves a captured run whole ahead of the debt's park."""

    def test_a_report_put_back_under_the_notice(self) -> None:
        # The report the run answers for is edited before the tick and put
        # back while the debt park's notice is posted. The policy every road
        # selects parks over the run still recorded, its last word never
        # re-reading the report at its location; the settled-evidence policy
        # proves the run whole ahead of the park and abandons it. Either way
        # the debt is parked and the run was made once. The baseline goes
        # first, so the policy the second case selects outlives neither.
        for proves_settled in (False, True):
            with self.subTest(proves_settled=proves_settled):
                self.setUp()
                if proves_settled:
                    self.enterContext(settled.selected())
                captured = self.captures()[1]
                self.parks_over_an_edit(before=True, raises=False)

                pending, _current, retired = readings.pinned_records(self)
                self.assertEqual(pending, None if proves_settled else captured)
                self.assertEqual((captured.receipt, readings.ABANDONED) in retired, proves_settled)
                self.assert_made_once()


class DebtParkReportEditTest(_DebtParkCase, settled.SettledGuardedCase, unittest.TestCase):
    """A report edited around the debt park's notice abandons the run, however soon it is put back."""

    def test_a_report_edit_abandons_the_run(self) -> None:
        # The run is abandoned whole ahead of the park or behind its notice,
        # whichever the edit was read by, and once room is made and any park
        # answered the head is routed with nothing current.
        for window, before, raises in _REPORT_EDITS:
            with self.subTest(window=window):
                self.setUp()
                head, captured = self.captures()
                self.parks_over_an_edit(before=before, raises=raises)

                self.assert_abandoned(captured)
                finish_moves.makes_room(self)
                if not raises:
                    self.continues()
                self.recovers()

                self.assert_abandoned(captured)
                self.assert_routed(head)


class SettledUnderTheAbandonmentTest(settled.SettledGuardedCase, unittest.TestCase):
    """A captured run another finish settles while the debt park's proof abandons it over an edited issue."""

    def test_the_settled_run_is_invalidated(self) -> None:
        # The debt is parked over the run invalidated whole, and once room is
        # made and the park answered the head is routed with nothing current.
        head, captured = self._abandons_under_a_settlement(
            partial(finish_moves.fills_the_comment, left=_SHORT_OF_THE_DEBT),
        )
        self.assert_invalidated(captured)
        self.assertTrue(self.pinned_fields(guarded.AWAITING)[0])
        finish_moves.makes_room(self)
        self.continues()
        self.recovers()
        self.assert_routed(head)

    def test_a_full_comment_records_the_movement(self) -> None:
        # Nothing parked and the tip blank, the run current; room made, the
        # next recovery invalidates it whole and routes the head.
        head, captured = self._abandons_under_a_settlement(finish_moves.fills_the_comment)
        self.assertEqual(self.pinned_fields(guarded.AWAITING, readings.KEY_REWRITE_BASE), (None, None))
        self.assertEqual(readings.pinned_records(self)[1].receipt, captured.receipt)
        finish_moves.makes_room(self)
        self.recovers()
        retired = readings.pinned_records(self)[2]
        self.assertEqual(retired[-1], (captured.receipt, readings.INVALIDATED))
        self.assert_routed(head)

    def test_a_successor_settled_meanwhile_is_kept(self) -> None:
        # The newer run stays current, the captured one superseded as that
        # road left it, and nothing is parked.
        captured = self._abandons_under_a_settlement(partial(settled.records_a_newer_run, settles=True))[1]
        current, retired = readings.pinned_records(self)[1:]
        self.assertNotEqual(current.receipt, captured.receipt)
        self.assertEqual(retired[-1], (captured.receipt, "superseded"))
        self.assertFalse(self.pinned_fields(guarded.AWAITING)[0])

    def _abandons_under_a_settlement(self, then) -> tuple:
        """Capture a run, edit the issue, and recover the debt's park as another finish settles the run; head and run.

        That finish is given room for its own debt, and `then` is made behind it.
        """
        head, captured = self.captures()
        finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
        raced: list = []
        settles = partial(self._settles_elsewhere, head, self.issue.body, raced, then)
        self.issue.body = _EDITED_BODY
        edits = partial(self._ahead, settles, self.gh.edit_pinned_state)
        with patch.object(self.gh, "edit_pinned_state", edits):
            self.recovers()
        self.assertEqual(raced, [head])
        return head, captured

    def _settles_elsewhere(self, head: str, written: str, raced: list, then) -> None:
        """Make room and settle `head`'s run as another finish would, once, with `then` behind it."""
        if not raced:
            finish_moves.makes_room(self)
        settled.settles_elsewhere(self, head, written, raced, then)

    def _ahead(self, settles, live, issue, state, *, over: dict):
        """`live`, the client's pinned edit, with `settles` made ahead of an edit abandoning the pending run."""
        if _abandoning(state, over):
            settles()
        return live(issue, state, over=over)


if __name__ == "__main__":
    unittest.main()
