# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run the finish's own debt park keeps, proved whole before the park and again behind its notice.

Direct finishes of the recovery's road (`settled_route_support`): issue #7's
run captured and the comment left without room for the landing's report debt,
so the finish parks for it. The policy every road selects parks over the run
still recorded, and parks anew when asked again. Held to the dormant
settled-evidence policy, the finish proves the run's binding whole ahead of
the park and behind its notice, so the report edited around the notice --
answered or raising -- abandons the run, and the head is later routed with
nothing current; asked again with no reply, it finds its park standing and
posts nothing -- also where its park write went out and never landed, the
notice it posted found on the conversation and parked over, its event filed
only where the stream lacks it -- and holds where that conversation will not
read. Answered with a reply and parked again for the same head, a replay of
that reply over a re-park that never landed parks over the notice said behind
it, and a re-park whose notice lost its answer files that park's own event,
however many parks the head took before. Requirements
edited before the finish abandon the run while
another finish settles it: that settlement is invalidated over the edit, or
with the comment full its movement recorded, a successor under its own
receipt kept -- also where that finish announced before dying at its relabel.
"""
from __future__ import annotations

import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import report_settlement_state as _report_settlement, verification_records as _records
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
    settled_route_support as route,
)
from tests.workflow.interleaving import _RacesPastTheCall

_EDITED_BODY = "Also cover a base that moved twice."

_AWAITING = "awaiting_human"

# The event a park files, and why a debt with no room parks.
_PARKED = "park_awaiting_human"

_FOR_THE_DEBT = "auto_base_rebase_unrecorded_debt"

_WATERMARK = "last_action_comment_id"

# The client's strict pinned edit, which a case answers a write under.
_PINNED_EDIT = "edit_pinned_state"

# What every debt park notice says, whichever head it parks.
_DOES_NOT_FIT = "does not fit on this issue's pinned state comment"

# Room on the pinned comment for the run's history entry and the park behind
# it, and short of the landing's report debt and the announcement it rides.
_SHORT_OF_THE_DEBT = 250

# When the report the run answers for is edited: before the finish, put back
# while the debt park's notice is posted; or while that notice is posted, put
# back behind the finish -- and whether the notice's post raises, which leaves
# nothing parked.
_REPORT_EDITS = (
    ("before the park", True, False),
    ("under the notice", False, False),
    ("under a raised notice", False, True),
)


def _loses_the_answer(moves=None) -> None:
    """Make `moves`, where given, then lose the answer of the request it was made behind."""
    if moves is not None:
        moves()
    raise RuntimeError("the answer was lost")


def _abandoning(state, over: dict) -> bool:
    """Whether a pinned-comment edit drops a transaction the comment it is made over still carries pending."""
    drops = state.get(_records.PENDING_EVIDENCE) is None
    return drops and over.get(_records.PENDING_EVIDENCE) is not None


class _DebtParkCase(route.SettledRouteCase):
    """A captured run a direct finish parks for the landing's debt, its report edited around the park."""

    def parks_over_an_edit(self, finishing, *, before: bool, raises: bool = False) -> None:
        """Ask `finishing` over the report edited `before` it or under the park's notice, whose post `raises`.

        `finishing` is a direct finish of the landing. An edit made before it
        is put back while the notice is posted; the report is put back behind
        it in any case. The debt is parked unless the notice's post raised.
        """
        finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
        posted = self._report_comment()
        written = posted.body
        edits = partial(setattr, posted, "body", f"{written}\nEdited by hand.")
        noticed = partial(setattr, posted, "body", written) if before else edits
        if before:
            edits()
        if raises:
            noticed = partial(_loses_the_answer, noticed)
        with patch.object(self.gh, "comment", _RacesPastTheCall(self.gh.comment, 1, noticed)):
            if raises:
                self.assertRaises(RuntimeError, finishing)
            else:
                self.assertEqual(finishing(), FinishOutcome.PARKED)
        posted.body = written
        parked = self.pinned_fields(_AWAITING)[0]
        self.assertEqual(bool(parked), not raises)

    def answers_the_park(self, head: str) -> FinishOutcome:
        """Make room, have the issue's author reply to the park, and finish `head` directly spending that reply."""
        finish_moves.makes_room(self)
        return self.finalizes(head, retry=self.replies())

    def replies(self) -> int:
        """Have the issue's author reply to the park; the reply's id."""
        reply = self.gh.comment(self.issue, "/orchestrator continue")
        reply.user.login = self.issue.user.login
        return reply.id

    def assert_routed_unparked(self, head: str) -> None:
        """`head` routed once with nothing current or pending and nothing parked, the run made once."""
        self.assertEqual(readings.pinned_records(self)[:2], (None, None))
        self.assertFalse(readings.pinned(self).get(_AWAITING))
        self.assert_routed_once(head)

    def _report_comment(self):
        """The comment the report this issue last settled landed as."""
        location = _report_settlement.read_current_report(self.gh.read_pinned_state(self.issue)).location
        return next(posted for posted in self.pull_request.issue_comments if posted.id == location.comment_id)

    def _loses_the_park(self, live, issue, state, *, over: dict, **options):
        """`live`, the client's pinned edit, answering a park's own write as sent and never confirmed, unlanded.

        A park's write is the one that has the issue awaiting a human over a
        watermark it moves to the notice just said -- a first park, or one
        made again over a park a reply answered.
        """
        moves = state.get(_WATERMARK) != over.get(_WATERMARK)
        if moves and state.get(_AWAITING) is True:
            return PinnedEdit.UNCONFIRMED
        return live(issue, state, over=over, **options)

    def _parks(self) -> tuple[int, int]:
        """How many `park_awaiting_human` events were filed, and how many notices the issue was given."""
        events = [event.get("event") for event in self.gh.recorded_events]
        return events.count(_PARKED), len(self.gh.posted_comments)


class DebtParkPolicyTest(_DebtParkCase, unittest.TestCase):
    """Only a finish held to the settled-evidence policy proves a captured run whole around the debt's park."""

    def test_a_report_put_back_under_the_notice(self) -> None:
        # The report the run answers for is edited before the finish and put
        # back while the debt park's notice is posted. The policy every road
        # selects parks over the run still recorded, its last word never
        # re-reading the report at its location; the settled-evidence policy
        # proves the run whole ahead of the park and abandons it. Either way
        # the debt is parked and the run was made once.
        for proves_settled in (False, True):
            with self.subTest(proves_settled=proves_settled):
                self.setUp()
                head, captured = self.captures()
                finishing = self.finalizes if proves_settled else partial(self.finishes, road=FinishRoad.RECOVERY)
                self.parks_over_an_edit(partial(finishing, head), before=True)

                records = readings.pinned_records(self)
                self.assertEqual(records[0], None if proves_settled else captured)
                self.assertEqual((captured.receipt, readings.ABANDONED) in records[2], proves_settled)
                self.assert_made()

    def test_a_repeated_finish_keeps_its_park(self) -> None:
        # The debt has no room and the landing is finished directly twice,
        # with no reply between. The settled-evidence policy proves the run
        # again and finds its park standing, so the second finish posts no
        # notice and files no park event; the policy every road selects parks
        # anew. Either way the run stays recorded and was made once.
        for proves_settled, parks in ((False, 2), (True, 1)):
            with self.subTest(proves_settled=proves_settled):
                self.setUp()
                head, captured = self.captures()
                settled.charges(self)
                finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
                finishing = self.finalizes if proves_settled else partial(self.finishes, road=FinishRoad.RECOVERY)

                self.assertEqual(finishing(head), FinishOutcome.PARKED)
                self.assertEqual(finishing(head), FinishOutcome.PARKED)

                self.assertEqual(self._parks(), (parks, parks))
                self.assertEqual(readings.pinned_records(self)[0], captured)
                self.assert_made()
                settled.assert_charged_as_left(self)

    def test_an_unconfirmed_park_is_said_once(self) -> None:
        # The debt park's notice and event go out, and its write is sent and
        # never lands. Asked again with no reply between, the settled-evidence
        # policy finds that notice on the conversation and parks over it,
        # posting and filing nothing more; the policy every road selects says
        # both again. Either way the debt ends parked and the run made once.
        for proves_settled, parks in ((False, 2), (True, 1)):
            with self.subTest(proves_settled=proves_settled):
                self.setUp()
                head = self.captures()[0]
                finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
                finishing = self.finalizes if proves_settled else partial(self.finishes, road=FinishRoad.RECOVERY)
                loses = partial(self._loses_the_park, self.gh.edit_pinned_state)
                with patch.object(self.gh, _PINNED_EDIT, loses):
                    self.assertEqual(finishing(head), FinishOutcome.UNCONFIRMED)

                self.assertEqual(finishing(head), FinishOutcome.PARKED)

                self.assertEqual(self._parks(), (parks, parks))
                self.assertTrue(self.pinned_fields(_AWAITING)[0])
                self.assert_made()

    def test_an_unread_thread_holds_the_park(self) -> None:
        # The park's write behind its notice and event is sent and never
        # lands, and the conversation then will not read: nobody can say
        # whether the notice was said, so the finish holds with nothing said
        # again, and once the conversation reads it parks over that notice.
        head = self.captures()[0]
        finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
        loses = partial(self._loses_the_park, self.gh.edit_pinned_state)
        with patch.object(self.gh, _PINNED_EDIT, loses):
            self.assertEqual(self.finalizes(head), FinishOutcome.UNCONFIRMED)
        with patch.object(self.gh, "comments_after", side_effect=RuntimeError("the conversation would not read")):
            self.assertEqual(self.finalizes(head), FinishOutcome.HELD)

        self.assertEqual(self._parks(), (1, 1))
        self.assertEqual(self.finalizes(head), FinishOutcome.PARKED)
        self.assertEqual(self._parks(), (1, 1))
        self.assert_made()

    def test_a_lost_notice_files_its_event_once(self) -> None:
        # The stream already carries a debt park this issue took earlier,
        # naming no head. The park notice's post lands and its answer is lost,
        # so the finish leaves before the park's event is filed or its write
        # sent. The next finish parks over that notice and files the missing
        # event once, naming the landed head, the earlier park counting for
        # nothing; the one behind it finds the park standing and makes nothing.
        head = self.captures()[0]
        self.gh.emit_event(_PARKED, issue_number=self.issue.number, stage="validating", reason=_FOR_THE_DEBT)
        finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
        with patch.object(self.gh, "comment", _RacesPastTheCall(self.gh.comment, 1, _loses_the_answer)):
            self.assertRaises(RuntimeError, self.finalizes, head)
        self.assertEqual(self._parks(), (1, 1))

        retries = (self.finalizes(head), self.finalizes(head))
        self.assertEqual(retries, (FinishOutcome.PARKED, FinishOutcome.PARKED))

        filed = [event for event in self.gh.recorded_events if event.get("event") == _PARKED]
        named = [(event.get("reason"), event.get("sha")) for event in filed]
        self.assertEqual(named, [(_FOR_THE_DEBT, None), (_FOR_THE_DEBT, head)])
        self.assertEqual(self._parks(), (2, 1))
        self.assertTrue(self.pinned_fields(_AWAITING)[0])
        self.assert_made()



class DebtReparkTest(_DebtParkCase, unittest.TestCase):
    """A park answered with a reply and made again for the same head, said and filed once whatever is replayed."""

    def test_a_replayed_reply_reparks_once(self) -> None:
        # The debt parks, its author replies with no room made, and the
        # finish spending that reply parks again: its notice and event go
        # out and its write is sent and never lands, so the reply stays short
        # of the watermark. Handed that very reply again, the finish finds the
        # notice said behind it and parks over it, posting and filing nothing
        # more; asked once more with no reply, it finds the park standing.
        head, reply = self._parked_and_answered()
        loses = partial(self._loses_the_park, self.gh.edit_pinned_state)
        with patch.object(self.gh, _PINNED_EDIT, loses):
            self.assertEqual(self.finalizes(head, retry=reply), FinishOutcome.UNCONFIRMED)
        self.assertLess(readings.pinned(self)[_WATERMARK], reply)

        retries = (self.finalizes(head, retry=reply), self.finalizes(head))
        self.assertEqual(retries, (FinishOutcome.PARKED, FinishOutcome.PARKED))

        self._assert_parked_twice(head, reply)

    def test_a_lost_repark_notice_files_its_event(self) -> None:
        # The debt parks for the head, its author replies with no room made,
        # and the notice of the park made again lands with its answer lost,
        # so neither that park's event nor its write goes out. Handed the
        # reply again, the finish parks over that notice and files its event,
        # the first park's event of the very same head no event of this one;
        # asked once more with no reply, it finds the park standing.
        head, reply = self._parked_and_answered()
        with patch.object(self.gh, "comment", _RacesPastTheCall(self.gh.comment, 1, _loses_the_answer)):
            self.assertRaises(RuntimeError, self.finalizes, head, retry=reply)
        self.assertEqual(self._parks(), (1, 3))

        retries = (self.finalizes(head, retry=reply), self.finalizes(head))
        self.assertEqual(retries, (FinishOutcome.PARKED, FinishOutcome.PARKED))

        self._assert_parked_twice(head, reply)

    def _parked_and_answered(self) -> tuple[str, int]:
        """The run captured, the debt parked for its head with no room, and the park answered with none made."""
        head = self.captures()[0]
        finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
        self.assertEqual(self.finalizes(head), FinishOutcome.PARKED)
        return head, self.replies()

    def _assert_parked_twice(self, head: str, reply: int) -> None:
        """Two park notices ahead of and behind `reply`, each with one event of its own naming it and `head`."""
        noticed = [
            posted.id for posted in self.issue.comments
            if _DOES_NOT_FIT in (posted.body or "")
        ]
        self.assertEqual(len(noticed), 2)
        self.assertLess(noticed[0], reply)
        named = [
            (event.get("reason"), event.get("sha"), event.get("notice_id"))
            for event in self.gh.recorded_events if event.get("event") == _PARKED
        ]
        self.assertEqual(named, [(_FOR_THE_DEBT, head, notice) for notice in noticed])
        self.assertEqual(self._parks(), (2, 3))
        self.assertEqual(self.pinned_fields(_AWAITING, _WATERMARK), (True, noticed[1]))
        self.assert_made()


class DebtParkReportEditTest(_DebtParkCase, unittest.TestCase):
    """A report edited around the debt park's notice abandons the run, however soon it is put back."""

    def test_a_report_edit_abandons_the_run(self) -> None:
        # The run is abandoned whole ahead of the park or behind its notice,
        # whichever the edit was read by, and once room is made and any park
        # answered the head is routed with nothing current.
        for window, before, raises in _REPORT_EDITS:
            with self.subTest(window=window):
                self.setUp()
                head, captured = self.captures()
                self.parks_over_an_edit(partial(self.finalizes, head), before=before, raises=raises)

                self.assert_abandoned(captured)
                self.assertEqual(self.answers_the_park(head), FinishOutcome.ROUTED)

                self.assert_abandoned(captured)
                self.assert_routed_unparked(head)


class SettledUnderTheAbandonmentTest(_DebtParkCase, unittest.TestCase):
    """A captured run another finish settles while the debt park's proof abandons it over an edited issue."""

    def test_the_settled_run_is_invalidated(self) -> None:
        # The debt is parked over the run invalidated whole, and once room is
        # made and the park answered the head is routed with nothing current.
        head, captured = self._abandons_under_a_settlement(
            partial(finish_moves.fills_the_comment, left=_SHORT_OF_THE_DEBT), FinishOutcome.PARKED,
        )
        self.assert_retired_whole(captured)
        self.assertTrue(readings.pinned(self)[_AWAITING])
        self.assertEqual(self.answers_the_park(head), FinishOutcome.ROUTED)
        self.assert_routed_unparked(head)

    def test_a_full_comment_records_the_movement(self) -> None:
        # Nothing parked and the tip blank, the run current; room made, the
        # next finish invalidates it whole and routes the head.
        head, captured = self._abandons_under_a_settlement(finish_moves.fills_the_comment, FinishOutcome.HELD)
        self.assertEqual(self.pinned_fields(_AWAITING, readings.KEY_REWRITE_BASE), (None, None))
        self.assertEqual(readings.pinned_records(self)[1].receipt, captured.receipt)
        finish_moves.makes_room(self)
        self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
        retired = readings.pinned_records(self)[2]
        self.assertEqual(retired[-1], (captured.receipt, readings.INVALIDATED))
        self.assert_routed_unparked(head)

    def test_a_successor_settled_meanwhile_is_kept(self) -> None:
        # The newer run stays current, the captured one superseded as that
        # road left it, and nothing is parked.
        then = partial(settled.records_a_newer_run, settles=True)
        captured = self._abandons_under_a_settlement(then, FinishOutcome.HELD)[1]
        current, retired = readings.pinned_records(self)[1:]
        self.assertNotEqual(current.receipt, captured.receipt)
        self.assertEqual(retired[-1], (captured.receipt, "superseded"))
        self.assertFalse(readings.pinned(self).get(_AWAITING))

    def test_an_announced_settlement_is_invalidated(self) -> None:
        # The finish that settles the run also records the debt, announces
        # the landing, and dies at its relabel: its mark and the record of its
        # event are this attempt advanced, so the settlement is invalidated
        # over the edit all the same. With room for that, nothing is parked
        # and the head is routed in the same finish, the announcement said
        # once; with the comment full, the base tip is blanked with the run
        # current and nothing relabelled, and once room is made the next
        # finish invalidates the run whole and routes the head.
        for full in (False, True):
            with self.subTest(full=full):
                self.setUp()
                fills = partial(finish_moves.fills_the_comment, left=0 if full else _SHORT_OF_THE_DEBT)
                answer = FinishOutcome.HELD if full else FinishOutcome.ROUTED
                head, captured = self._abandons_under_a_settlement(fills, answer, handoff.BEFORE_THE_RELABEL)
                if full:
                    self.assertEqual(self.pinned_fields(_AWAITING, readings.KEY_REWRITE_BASE), (None, None))
                    self.assertEqual(readings.pinned_records(self)[1].receipt, captured.receipt)
                    self.assertEqual(readings.relabels(self), ())
                    finish_moves.makes_room(self)
                    self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
                self.assert_retired_whole(captured)
                self.assert_routed_unparked(head)

    def _abandons_under_a_settlement(
        self, then, answer: FinishOutcome, died: handoff.Boundary = handoff.BEFORE_THE_ANNOUNCEMENT,
    ) -> tuple:
        """Capture a run, edit the issue, and finish it directly as another finish settles the run; head and run.

        That finish, of this landing and under the same policy, is given room
        for its own debt and dies at `died`, and `then` is made behind it; the
        proving finish answers `answer`.
        """
        landed = self.captures()
        head = landed[0]
        finish_moves.fills_the_comment(self, _SHORT_OF_THE_DEBT)
        raced: list = []
        settles = partial(self._settles_elsewhere, head, self.issue.body, raced, died, then)
        self.issue.body = _EDITED_BODY
        edits = partial(self._ahead, settles, self.gh.edit_pinned_state)
        with patch.object(self.gh, _PINNED_EDIT, edits):
            self.assertEqual(self.finalizes(head), answer)
        self.assertEqual(raced, [head])
        return landed

    def _settles_elsewhere(self, head: str, written: str, raced: list, died: handoff.Boundary, then) -> None:
        """Put the issue back as `written`, make room, and settle the run as another finish would; `then` behind it.

        Made once, on the first edit abandoning the run.
        """
        if raced:
            return
        raced.append(head)
        self.issue.body = written
        finish_moves.makes_room(self)
        handoff.dies_at(self.gh, died, partial(self.finalizes, head))
        then(self)

    def _ahead(self, settles, live, issue, state, **options):
        """`live`, the client's pinned edit, with `settles` made ahead of an edit abandoning the pending run."""
        if _abandoning(state, options["over"]):
            settles()
        return live(issue, state, **options)


if __name__ == "__main__":
    unittest.main()
