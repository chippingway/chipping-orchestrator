# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What moves under a landed rewrite's final steps -- its announcement, relabel, and retirement -- and the run over it.

Direct finishes through the coordinator every road hands its landing to
(`settled_route_support`): issue #7's run settled and proved ready before the
announcement, then another road settles report 3 while the notice is posted,
the relabel made, or the retirement sent, or the issue is edited under the
notice and put back at the relabel. The run is invalidated whole either way,
the later report left as written, the route held where a write was refused
and routed to the fresh reviewer where a proof read it; putting report 2 back
revives nothing, and the head ends routed once -- even where it is put back
before the event's record, the checkpoint, or the retirement's own edit
returns, which names what it found moved -- and so does movement another road
recorded under the run there, a mark in its handoff's place, a revision spent
past it, or a blank of the attempt's base tip, read off the comment that edit
found. A newer transaction moved under the checkpoint's or the retirement's
edit, put back or kept, invalidates nothing, and a successor is kept as
written. A report moved under the notice refuses the event's own
record before anything is filed; a step that failed meanwhile has the run
proved once more; and a base advanced under the notice or relabel holds the
route for the next finish to continue the head. Nothing runs again.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.github import events as _github_events
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    rewrite_finish_writes as _writes,
    verification_records as _evidence_records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
    settled_route_support as route,
    verification_report_fixture as _report,
)

# The report and review records a later report's settlement moves, as the
# pinned comment spells them.
_MOVED_RECORDS = (
    "developer_report_current",
    "developer_report_handoff",
    "review_subject",
    "review_returned_subject",
)

_CURRENT_REPORT = _MOVED_RECORDS[0]

# The evidence records a newer transaction moves.
_EVIDENCE_RECORDS = (
    _evidence_records.PENDING_EVIDENCE,
    _evidence_records.CURRENT_EVIDENCE,
    _evidence_records.EVIDENCE_HISTORY,
    _evidence_records.EVIDENCE_HANDOFF,
    _evidence_records.REVISION_FLOOR,
)

_EDITED_BODY = "Also cover a base that moved twice."


class _Window(NamedTuple):
    """A final step something moves under: the client step, the call of it, and how the finish ends.

    `ahead` makes the move ahead of that call rather than behind it, and
    `answer` is what the finish comes to -- a refused write keeps the
    attempt, a proof that read the move routes the head.
    """

    name: str
    step: str
    picks: Callable
    answer: FinishOutcome
    ahead: bool = False


class _Step:
    """A client step that has `move` made once, on the call `picks` names: behind that call, or `ahead` of it."""

    def __init__(self, live, window: _Window, move) -> None:
        self._live = live
        self._window = window
        self._move = move
        self._moved = False
        self.answered: list = []

    def __call__(self, *args, **kwargs):
        picked = not self._moved and self._window.picks(*args, **kwargs)
        self._moved = self._moved or picked
        if picked and self._window.ahead:
            self._move()
        answered = self._live(*args, **kwargs)
        if picked:
            self.answered.append(answered)
        if picked and not self._window.ahead:
            self._move()
        return answered


class _AnotherRoad:
    """Another road's move, keeping first the run and how the records it moves stood.

    It settles and reviews report 3 of the head -- or, `newer` given, records a
    newer transaction beside the run, settling it over the run where `newer`,
    or, `records` given, writes the fields that hands back for the run, as a
    road recording movement under it would.
    """

    def __init__(self, case: route.SettledRouteCase, head: str, newer: bool | None = None, records=None) -> None:
        self._case = case
        self._head = head
        self._newer = newer
        self._records = records
        self._before: dict = {}
        self.settled = None

    def __call__(self) -> None:
        case = self._case
        pinned = readings.pinned(case)
        self.settled = readings.pinned_records(case)[1]
        if self._records is not None:
            self._writes(pinned, self._records(self.settled))
            return
        moved = _MOVED_RECORDS if self._newer is None else _EVIDENCE_RECORDS
        self._before = {key: pinned.get(key) for key in moved}
        if self._newer is not None:
            settled.records_a_newer_run(case, settles=self._newer)
            return
        case.state = case.gh.read_pinned_state(case.issue)
        _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)

    @property
    def superseded(self) -> tuple:
        """The history entry of the run a successor settled in its place, as that road leaves it."""
        return self.settled.receipt, "superseded"

    def restores(self) -> None:
        """Write the records the move moved back as they stood before it."""
        self._writes({}, self._before)

    def _writes(self, pinned: dict, fields: dict) -> None:
        """Write `fields` over the comment as it stands, keeping first how `pinned` spelled each where it has any."""
        if pinned:
            self._before = {key: pinned.get(key) for key in fields}
        state = self._case.gh.read_pinned_state(self._case.issue)
        for key, written in fields.items():
            state.set(key, written)
        self._case.gh.write_pinned_state(self._case.issue, state)


# Each final step a later report moves under: the notice's post, which the
# checkpoint behind it refuses; the relabel, which the proof behind it reads;
# and the retirement's own edit, which the comment moving under it refuses.
_REPORT_WINDOWS = (
    _Window("while the notice is posted", "pr_comment", handoff.BEFORE_THE_ANNOUNCEMENT.kills, FinishOutcome.REFUSED),
    _Window("while the relabel is made", "set_workflow_label", handoff.BEFORE_THE_RELABEL.kills, FinishOutcome.ROUTED),
    _Window(
        "while the retirement is sent", "edit_pinned_state", handoff.BEFORE_THE_RETIREMENT.kills,
        FinishOutcome.REFUSED, ahead=True,
    ),
)

# Each of the finish's own edits a report moves right ahead of and is put back
# right behind, before that edit returns: the event's record, the checkpoint,
# and the retirement.
_EDIT_WINDOWS = tuple(
    _Window(boundary.name, "edit_pinned_state", boundary.kills, FinishOutcome.REFUSED, ahead=True)
    for boundary in (handoff.BEFORE_THE_EVENT_RECORD, handoff.BEFORE_THE_CHECKPOINT, handoff.BEFORE_THE_RETIREMENT)
)

# What another road records under the run to say movement was read under it,
# where nothing else had room: the mark in its handoff's place, a revision
# spent past it on the floor, or the attempt's base tip blanked.
_RECORDS_MOVEMENT = (
    ("a movement mark", lambda run: {_evidence_records.EVIDENCE_HANDOFF: {"moved": run.receipt}}),
    ("a revision spent past it", lambda run: {readings.KEY_REVISION_FLOOR: run.revision + 1}),
    ("its base tip blanked", lambda run: {readings.KEY_REWRITE_BASE: None}),
)

# The checkpoint's preparation, ahead of the notice, with a move made ahead of
# it -- over the fresh reading it is decided on.
_PREPARING_THE_CHECKPOINT = _Window(
    "as the checkpoint is prepared", "prepares",
    lambda _finish, _staged, write, *_rest, **_reserves: write is _writes.CHECKPOINT, FinishOutcome.REFUSED, ahead=True,
)

# The relabel, with a move made ahead of its call rather than behind it.
_AHEAD_OF_THE_RELABEL = _Window(
    "ahead of the relabel", "set_workflow_label", handoff.BEFORE_THE_RELABEL.kills, FinishOutcome.ROUTED, ahead=True,
)


class _FinalStepCase(route.SettledRouteCase):
    """Issue #7's reviewed rebase finished directly with something moved under one of its final steps."""

    def finishes_moving(self, head: str, window: _Window, move) -> FinishOutcome:
        """Publish `head`'s direct finish with `move` made on the call of the client's step `window` names."""
        stepping = _Step(getattr(self.gh, window.step), window, move)
        with patch.object(self.gh, window.step, stepping):
            return self.finalizes(head, FinishRoad.PUBLICATION)

    def held(self) -> tuple:
        """The anchor the attempt still stands on, or None, and the revision of the report settled current."""
        pinned = readings.pinned(self)
        return pinned[readings.KEY_PENDING_PUSH], pinned[_CURRENT_REPORT]["revision"]

    def invalidated_heads(self) -> list[str]:
        """The head every evidence record tested, where all went into history invalidated; [] where any did not."""
        records = readings.pinned_records(self)
        reasons = {why for _receipt, why in records[2]}
        if records[:2] != (None, None):
            return []
        if reasons != {readings.INVALIDATED}:
            return []
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        return [entry.binding.tested_sha for entry in history]

    def edits_under_the_announcement(self, head: str) -> FinishOutcome:
        """Publish `head`'s direct finish with the issue edited as its notice is posted and put back at the relabel."""
        written = self.issue.body
        edits = partial(setattr, self.issue, "body", _EDITED_BODY)
        posted = _Step(self.gh.pr_comment, _REPORT_WINDOWS[0], edits)
        restores = partial(setattr, self.issue, "body", written)
        relabelled = _Step(self.gh.set_workflow_label, _AHEAD_OF_THE_RELABEL, restores)
        with (
            patch.object(self.gh, "pr_comment", posted),
            patch.object(self.gh, "set_workflow_label", relabelled),
        ):
            return self.finalizes(head, FinishRoad.PUBLICATION)

    def assert_continued(self, head: str) -> None:
        """`head` announced once and continued, its attempt retired, the run made once and nothing pushed."""
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, ([head], 1))
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)
        self.assert_made()

    def prepares_moving(self, head: str, moves: _AnotherRoad) -> FinishOutcome:
        """Publish `head`'s direct finish, `moves` made ahead of the checkpoint's preparation and put back behind it."""
        ahead = _Step(_writes.prepares, _PREPARING_THE_CHECKPOINT, moves)
        behind = _Step(ahead, _PREPARING_THE_CHECKPOINT._replace(ahead=False), moves.restores)
        with patch.object(_writes, "prepares", behind):
            return self.finalizes(head, FinishRoad.PUBLICATION)

    def moves_under(self, head: str, window: _Window, move, restores=None) -> list[PinnedEdit]:
        """Publish `head`'s direct finish with `move` made on the edit `window` picks, `restores` behind it; its answer.

        That edit finds the comment moved and is refused, so the finish comes back REFUSED.
        """
        ahead = _Step(self.gh.edit_pinned_state, window, move)
        behind = ahead
        if restores is not None:
            behind = _Step(ahead, window._replace(ahead=False), restores)
        with patch.object(self.gh, window.step, behind):
            self.assertEqual(self.finalizes(head, FinishRoad.PUBLICATION), FinishOutcome.REFUSED)
        self.assertEqual(ahead.answered, [PinnedEdit.MOVED])
        return ahead.answered


class FinalStepMoveTest(_FinalStepCase, unittest.TestCase):
    """A run something moved under during a final step is invalidated before the route is retired over it."""

    def test_a_moved_report_invalidates_the_run(self) -> None:
        # The run is invalidated in the finish the report moved in, that
        # report kept; the next finish, over the earlier report put back,
        # finds nothing current -- or no attempt, behind a route the proof
        # behind the relabel let go on -- and the head is said and routed once.
        for window in _REPORT_WINDOWS:
            with self.subTest(window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _AnotherRoad(self, head)

                self.assertEqual(self.finishes_moving(head, window, moves), window.answer)

                self.assert_retired_whole(moves.settled)
                standing = self.anchor if window.answer is FinishOutcome.REFUSED else None
                self.assertEqual(self.held(), (standing, 3))
                moves.restores()
                again = FinishOutcome.UNFINISHABLE if standing is None else FinishOutcome.ROUTED
                self.assertEqual(self.finalizes(head), again)

                self.assert_retired_whole(moves.settled)
                self.assert_routed_once(head)

    def test_a_move_put_back_under_an_edit_counts(self) -> None:
        # Report 3 is settled right ahead of one of the finish's own edits and
        # report 2 put back before that edit returns: the edit found the
        # comment moved, so the run is invalidated whole in that finish, the
        # attempt kept, and the next one routes the head once with nothing
        # current and nothing run, relabelled, or said again.
        for window in _EDIT_WINDOWS:
            with self.subTest(window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _AnotherRoad(self, head)

                self.moves_under(head, window, moves, moves.restores)

                self.assert_retired_whole(moves.settled)
                self.assertEqual(self.held(), (self.anchor, 2))
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

                self.assert_retired_whole(moves.settled)
                self.assert_routed_once(head)

    def test_recorded_movement_under_an_edit_counts(self) -> None:
        # Another road records movement under the run -- a mark in its
        # handoff's place, a revision spent past it, or the attempt's base tip
        # blanked -- right ahead of one of the finish's own edits, and puts it
        # back before that edit returns: the comment the edit read records
        # that movement, so the run is invalidated whole in that finish, the
        # attempt kept, and the next one routes the head once.
        for (recorded, records), window in product(_RECORDS_MOVEMENT, _EDIT_WINDOWS):
            with self.subTest(recorded=recorded, window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _AnotherRoad(self, head, records=records)

                self.moves_under(head, window, moves, moves.restores)

                self.assert_retired_whole(moves.settled)
                self.assertEqual(self.held(), (self.anchor, 2))
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
                self.assert_retired_whole(moves.settled)
                self.assert_routed_once(head)

    def test_recorded_movement_under_a_preparation(self) -> None:
        # The same movement recorded right ahead of the checkpoint's
        # preparation and put back right behind it: the fresh reading that
        # preparation was refused over records it, so the run is invalidated
        # whole before anything is said, and the next finish says and routes
        # the head once.
        for recorded, records in _RECORDS_MOVEMENT:
            with self.subTest(recorded=recorded):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _AnotherRoad(self, head, records=records)

                self.assertEqual(self.prepares_moving(head, moves), FinishOutcome.REFUSED)

                self.assert_retired_whole(moves.settled)
                self.assertEqual(readings.notices(self), [])
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)
                self.assert_routed_once(head)

    def test_a_newer_run_moved_under_an_edit(self) -> None:
        # A newer transaction recorded right ahead of the checkpoint's or the
        # retirement's own edit and put back before it returns moved only the
        # evidence records: the run is proved ready and kept, and the next
        # finish routes the head with it current. One settled there instead
        # supersedes the run as that road left it, nothing invalidated, and
        # the next finish routes the head with that successor current.
        for newer, window in product((False, True), _EDIT_WINDOWS[1:]):
            with self.subTest(settled=newer, window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _AnotherRoad(self, head, newer=newer)

                self.moves_under(head, window, moves, None if newer else moves.restores)

                self.assertEqual(self.held(), (self.anchor, 2))
                left = readings.pinned_records(self)[1:]
                self.assertEqual(left[0] == moves.settled, not newer)
                if newer:
                    self.assertEqual(left[1][-1], moves.superseded)
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

                self.assert_routed_once(head)
                self.assertEqual(readings.pinned_records(self)[1:], left)

    def test_a_restored_edit_invalidates_the_run(self) -> None:
        # The issue is edited while the notice is posted and put back as the
        # relabel is made: the proof ahead of the relabel reads the edit, so
        # the run is invalidated whole and the head goes on to the fresh
        # reviewer with nothing current, said once; the finish behind it finds
        # no attempt and changes nothing.
        head = self.lands_a_reviewed_rebase()
        self.assertEqual(self.edits_under_the_announcement(head), FinishOutcome.ROUTED)
        left = readings.pinned(self)

        self.assertEqual(self.finalizes(head), FinishOutcome.UNFINISHABLE)

        self.assertEqual(readings.pinned(self), left)
        self.assertEqual(self.invalidated_heads(), [self.anchor, head])
        self.assert_routed_once(head)

    def test_a_moved_base_holds_the_route(self) -> None:
        # The base advances again while the notice is posted, read by the
        # proof ahead of the relabel, or while the relabel is made, read by
        # the proof behind it: the run is invalidated and the route held with
        # the attempt kept. Once the checkout has fetched that base, the next
        # finish continues the head to the caller's rebase, said once.
        for window in _REPORT_WINDOWS[:2]:
            with self.subTest(window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                advances = partial(support.advances_the_base_again, self)

                self.assertEqual(self.finishes_moving(head, window, advances), FinishOutcome.HELD)

                self.assertEqual(self.invalidated_heads(), [self.anchor, head])
                self.assertEqual(self.held()[0], self.anchor)
                self._git("fetch", "--quiet", "origin", cwd=self._wt)
                self.assertEqual(self.finalizes(head), FinishOutcome.CONTINUED)

                self.assertEqual(self.invalidated_heads(), [self.anchor, head])
                self.assert_continued(head)


class EventRecordMoveTest(_FinalStepCase, unittest.TestCase):
    """A report moved under the notice refuses the event's record rather than riding into it unread."""

    def test_a_moved_report_refuses_the_event_record(self) -> None:
        # The report moved while the notice is posted refuses the event's
        # record, nothing filed, and the run is invalidated there and then;
        # the earlier report put back behind the next finish's record of the
        # event -- which refuses its checkpoint, the finish killed before it
        # files the event or not -- revives nothing, and the finish behind it
        # routes the head with everything said once.
        for boundary in (None, handoff.BEFORE_THE_EVENT):
            with self.subTest(boundary=getattr(boundary, "name", "uninterrupted")):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _AnotherRoad(self, head)
                self.assertEqual(self.finishes_moving(head, _REPORT_WINDOWS[0], moves), FinishOutcome.REFUSED)

                self.assert_retired_whole(moves.settled)
                recorded = readings.pinned(self).get(readings.KEY_ANNOUNCED_EVENT)
                self.assertEqual((support.announced(self), recorded), ([], None))
                restores = handoff.BEFORE_THE_EVENT_RECORD.moving(self.gh.edit_pinned_state, moves.restores)
                with patch.object(self.gh, "edit_pinned_state", restores):
                    handoff.dies_at(self.gh, boundary, partial(self.finalizes, head))
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

                self.assert_retired_whole(moves.settled)
                self.assert_routed_once(head)


class FailedStepMoveTest(_FinalStepCase, unittest.TestCase):
    """A run a report moved under while a final step was made that then failed is proved before the finish leaves."""

    def test_a_failed_step_proves_the_run_again(self) -> None:
        # The event stream will not read behind the posted notice, which
        # holds the finish, or the relabel lands and its answer is lost,
        # which raises: report 3, settled while either was made, invalidates
        # the run before the finish leaves, and report 2 put back before the
        # next finish revives nothing; that finish routes the head once.
        for failing in (self._unread_stream, self._lost_answer):
            with self.subTest(failure=failing.__name__):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _AnotherRoad(self, head)
                failing(head, moves)

                self.assert_retired_whole(moves.settled)
                self.assertEqual(self.held(), (self.anchor, 3))
                moves.restores()
                self.assertEqual(self.finalizes(head), FinishOutcome.ROUTED)

                self.assert_retired_whole(moves.settled)
                self.assert_routed_once(head)

    def _unread_stream(self, head: str, moves) -> None:
        """Finish `head` with `moves` made while the notice is posted, the event stream unreadable behind it."""
        with patch.object(_github_events, "filed", return_value=None):
            self.assertEqual(self.finishes_moving(head, _REPORT_WINDOWS[0], moves), FinishOutcome.HELD)

    def _lost_answer(self, head: str, moves) -> None:
        """Finish `head` with `moves` made while the relabel is made, the relabel's answer lost behind it."""
        with self.assertRaises(RuntimeError):
            self.finishes_moving(head, _REPORT_WINDOWS[1], partial(self._loses, moves))

    def _loses(self, moves) -> None:
        """Make `moves`, then lose the answer of the relabel it was made behind."""
        moves()
        raise RuntimeError("the relabel's answer was lost")


if __name__ == "__main__":
    unittest.main()
