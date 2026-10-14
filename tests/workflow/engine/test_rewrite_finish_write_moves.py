# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What moves under a landed rewrite's final steps -- its announcement, relabel, and retirement -- and the run over it.

The real-git finish case (`rewrite_verification_recovery_support`), every
finish -- handed over directly or reached by a refresh -- held to the dormant
settled-evidence policy (`settled_finish_support`): issue #7's rebased head
reviewed and its finish publishing the landing, the run of the configured
command settled under the anchor and proved ready before the announcement.
Then something it rests on moves while a final step is answered.

Another road settles and reviews a later report of the head: while the
announcement's notice is posted, which refuses the checkpoint; while the
relabel is made, which the run's proof taken once more behind the relabel
reads; or while the retirement itself is sent, which the comment moving under
that write refuses. Or the issue is edited while the notice is posted and put
back as the relabel is made, which the proof taken ahead of the relabel reads.
The run is invalidated into history whole either way, its revision and binding
kept, the later report left as that road wrote it --
the route held with the attempt standing where the write was refused, and
taken on to the fresh reviewer where the proof read it -- and putting the
earlier report and review back before the next poll revives nothing: the head
ends routed with nothing current, its notice and `base_rebased` event said
once. The report moved under the notice refuses the event's own record before
anything is filed, rather than riding into it unread, so the earlier report
put back behind the next finish's record of the event -- that finish killed
before it files the event, or not -- revives nothing either. Nor does report
2 put back behind a step that failed while report 3 was settled: an event
stream that would not read behind the posted notice, or a relabel that landed
with its answer lost. The finish proves the run once more before it leaves --
behind a retirement that landed with its answer lost as well, the issue edited
while it was sent: the run is invalidated over the attempt that retirement
left, so the issue put back before the finish is handed over again revives
nothing, and that finish finds no attempt standing and makes nothing.

Or the base advances while the notice is posted or the relabel made: the
proof behind the relabel reads it, invalidates the run, and holds the route
with the attempt standing, and the next tick continues the head to another
rebase it routes, each head announced once.

The run is never made again, and no developer is launched.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.github import events as _github_events
from orchestrator.workflow.engine import verification_settlement_state as _settlement
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
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

_CURRENT_REPORT = "developer_report_current"


class _Window(NamedTuple):
    """A final step something moves under: the client step, the call of it, and how the tick ends.

    `ahead` makes the move ahead of that call rather than behind it, and
    `standing` says whether the attempt still stands behind the tick -- a
    refused write keeps it, a proof that read the move takes the route on.
    """

    name: str
    step: str
    picks: Callable
    ahead: bool = False
    standing: bool = True


class _Step:
    """A client step that has `move` made once, on the call `picks` names: behind that call, or `ahead` of it."""

    def __init__(self, live, window: _Window, move) -> None:
        self._live = live
        self._window = window
        self._move = move
        self._moved = False

    def __call__(self, *args, **kwargs):
        picked = not self._moved and self._window.picks(*args, **kwargs)
        self._moved = self._moved or picked
        if picked and self._window.ahead:
            self._move()
        answered = self._live(*args, **kwargs)
        if picked and not self._window.ahead:
            self._move()
        return answered


class _LaterReport:
    """Another road settling and reviewing report 3 of the head, keeping first the run and the records it moves."""

    def __init__(self, case: support.CapturedRunCase, head: str) -> None:
        self._case = case
        self._head = head
        self._before: dict = {}
        self.settled = None

    def __call__(self) -> None:
        case = self._case
        pinned = readings.pinned(case)
        self._before = {key: pinned.get(key) for key in _MOVED_RECORDS}
        self.settled = readings.pinned_records(case)[1]
        case.state = case.gh.read_pinned_state(case.issue)
        _report.settles_report(case, 3, "Covered a base that moved twice as well.", head=self._head)
        case.gh.write_pinned_state(case.issue, case.state)

    def restores(self) -> None:
        """Write the report and review records back as they stood before report 3 moved them."""
        state = self._case.gh.read_pinned_state(self._case.issue)
        for key, recorded in self._before.items():
            state.set(key, recorded)
        self._case.gh.write_pinned_state(self._case.issue, state)


# Each final step a later report moves under: the notice's post, which the
# checkpoint behind it refuses; the relabel, which the proof behind it reads;
# and the retirement's own edit, which the comment moving under it refuses.
_REPORT_WINDOWS = (
    _Window("while the notice is posted", "pr_comment", handoff.BEFORE_THE_ANNOUNCEMENT.kills),
    _Window("while the relabel is made", "set_workflow_label", handoff.BEFORE_THE_RELABEL.kills, standing=False),
    _Window("while the retirement is sent", "edit_pinned_state", handoff.BEFORE_THE_RETIREMENT.kills, ahead=True),
)

# Each final step the base advances under, read by the proof behind the relabel.
_BASE_WINDOWS = _REPORT_WINDOWS[:2]

# The relabel, with a move made ahead of its call rather than behind it.
_AHEAD_OF_THE_RELABEL = _Window(
    "ahead of the relabel", "set_workflow_label", handoff.BEFORE_THE_RELABEL.kills, ahead=True,
)

_EDITED_BODY = "Also cover a base that moved twice."


class _FinalStepCase(settled.SettledRunCase):
    """Issue #7's reviewed rebase finished with something moved under one of its final steps, and read back."""

    def _finishes(self, head: str, window: _Window, move) -> None:
        """Publish `head`'s finish with `move` made on the call of the client's step `window` names."""
        stepping = _Step(getattr(self.gh, window.step), window, move)
        with patch.object(self.gh, window.step, stepping):
            self.finishes(head)

    def _edits_under_the_announcement(self, head: str) -> None:
        """Publish `head`'s finish with the issue edited as its notice is posted and put back ahead of the relabel."""
        written = self.issue.body
        edits = partial(setattr, self.issue, "body", _EDITED_BODY)
        restores = partial(setattr, self.issue, "body", written)
        posted = _Step(self.gh.pr_comment, _REPORT_WINDOWS[0], edits)
        relabelled = _Step(self.gh.set_workflow_label, _AHEAD_OF_THE_RELABEL, restores)
        with (
            patch.object(self.gh, "pr_comment", posted),
            patch.object(self.gh, "set_workflow_label", relabelled),
        ):
            self.finishes(head)

    def _held(self) -> tuple:
        """The anchor the attempt still stands on, or None, and the revision of the report settled current."""
        pinned = readings.pinned(self)
        return pinned[readings.KEY_PENDING_PUSH], pinned[_CURRENT_REPORT]["revision"]

    def _tested(self) -> list[str]:
        """The head every evidence record tested, where all went into history invalidated; [] where any did not."""
        records = readings.pinned_records(self)
        reasons = {why for _receipt, why in records[2]}
        if records[:2] != (None, None):
            return []
        if reasons != {readings.INVALIDATED}:
            return []
        history = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))
        return [entry.binding.tested_sha for entry in history]

    def _assert_routed_once(self, *heads: str) -> None:
        """Each of `heads` filed as `base_rebased` and announced once, in order, and the attempt retired."""
        said = (support.announced(self), len(readings.notices(self)))
        self.assertEqual(said, (list(heads), len(heads)))
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def _assert_invalidated(self, settled) -> None:
        """`settled` invalidated whole behind the anchor's evidence and nothing current, its command run once."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        made = (self.runs(), self.developer.call_count)
        self.assertEqual(made, (1, 0))



class FinalStepMoveTest(_FinalStepCase, unittest.TestCase):
    """A run something moved under during a final step is invalidated before the route is retired over it."""

    def test_a_moved_report_invalidates_the_run(self) -> None:
        # The run is invalidated in the tick the report moved in, that report
        # kept; the next poll, over the earlier report put back, finds nothing
        # current, and the head is announced once and routed.
        for window in _REPORT_WINDOWS:
            with self.subTest(window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _LaterReport(self, head)
                self._finishes(head, window, moves)

                self._assert_invalidated(moves.settled)
                standing = self.anchor if window.standing else None
                self.assertEqual(self._held(), (standing, 3))
                moves.restores()
                self.recovers()

                self._assert_invalidated(moves.settled)
                self._assert_routed_once(head)

    def test_a_restored_edit_invalidates_the_run(self) -> None:
        # The issue is edited while the notice is posted and put back as the
        # relabel is made: the proof ahead of the relabel reads the edit, so
        # the run is invalidated whole and the head goes on to the fresh
        # reviewer with nothing current, said once, and the poll behind it
        # changes nothing.
        head = self.lands_a_reviewed_rebase()
        self._edits_under_the_announcement(head)
        self.recovers()

        self.assertEqual(self._tested(), [self.anchor, head])
        self._assert_routed_once(head)
        self.assertEqual(readings.relabels(self), readings.ROUTED)
        self.assertEqual((self.runs(), self.developer.call_count), (1, 0))

    def test_a_moved_base_holds_the_route(self) -> None:
        # The proof behind the relabel reads the base gone elsewhere: the run
        # is invalidated and the attempt kept, and the next tick continues
        # the head to another rebase and routes it, each head said once.
        for window in _BASE_WINDOWS:
            with self.subTest(window=window.name):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                self._finishes(head, window, partial(support.advances_the_base_again, self))

                self.assertEqual(self._tested(), [self.anchor, head])
                self.assertEqual(self._held()[0], self.anchor)
                self.recovers()

                self.assertEqual(self._tested(), [self.anchor, head])
                self._assert_routed_once(head, git_support.remote_head(self))
                self.assertEqual((self.runs(), self.pushes.call_count), (1, 1))


class EventRecordMoveTest(_FinalStepCase, unittest.TestCase):
    """A report moved under the notice refuses the event's record rather than riding into it unread."""

    def test_a_moved_report_refuses_the_event_record(self) -> None:
        # The report moved while the notice is posted refuses the event's
        # record, nothing filed, and the run is invalidated there and then;
        # the earlier report put back behind the next finish's record of the
        # event, killed before it files the event or not, revives nothing.
        for boundary in (None, handoff.BEFORE_THE_EVENT):
            with self.subTest(boundary=getattr(boundary, "name", "uninterrupted")):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _LaterReport(self, head)
                self._finishes(head, _REPORT_WINDOWS[0], moves)

                self._assert_invalidated(moves.settled)
                recorded = readings.pinned(self).get(readings.KEY_ANNOUNCED_EVENT)
                self.assertEqual((support.announced(self), recorded), ([], None))
                restores = handoff.BEFORE_THE_EVENT_RECORD.moving(self.gh.edit_pinned_state, moves.restores)
                with patch.object(self.gh, "edit_pinned_state", restores):
                    handoff.dies_at(self.gh, boundary, self.recovers)
                self.recovers()
                self.recovers()

                self._assert_invalidated(moves.settled)
                self._assert_routed_once(head)



class FailedStepMoveTest(_FinalStepCase, unittest.TestCase):
    """A run a report moved under while a final step was made that then failed is proved before the finish leaves."""

    def test_a_failed_step_proves_the_run_again(self) -> None:
        # The event stream will not read behind the posted notice, or the
        # relabel lands and its answer is lost: report 3, settled while either
        # was made, invalidates the run before the finish leaves, and report 2
        # put back before the next poll revives nothing.
        for failing in (self._unread_stream, self._lost_answer):
            with self.subTest(failure=failing.__name__):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                moves = _LaterReport(self, head)
                failing(head, moves)

                self._assert_invalidated(moves.settled)
                self.assertEqual(self._held(), (self.anchor, 3))
                moves.restores()
                self.recovers()

                self._assert_invalidated(moves.settled)
                self._assert_routed_once(head)
                self.assertEqual(readings.relabels(self), readings.ROUTED)

    def test_a_lost_retirement_keeps_the_movement(self) -> None:
        # The retirement lands with its answer lost, the issue edited while it
        # is sent or not. The proof behind it reads the edit and invalidates
        # the run over the attempt that retirement left -- or reads nothing,
        # and the run stays current -- and with the issue put back the finish
        # handed over again makes nothing: the head routed once.
        for edited in (False, True):
            with self.subTest(edited=edited):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                written = self.issue.body
                body = _EDITED_BODY if edited else written
                retiring = partial(self._loses_the_retirement, self.gh.edit_pinned_state, body)
                with patch.object(self.gh, "edit_pinned_state", retiring):
                    self.assertEqual(self.finishes(head), FinishOutcome.UNCONFIRMED)
                self.issue.body = written

                self.assertEqual(self.finishes(head, FinishRoad.RECOVERY), FinishOutcome.UNFINISHABLE)

                self._assert_kept_unless(edited, head)
                self._assert_routed_once(head)
                self.assertEqual((self.runs(), self.developer.call_count), (1, 0))

    def _unread_stream(self, head: str, moves) -> None:
        """Finish `head` with `moves` made while the notice is posted, the event stream unreadable behind it."""
        with patch.object(_github_events, "filed", return_value=None):
            self._finishes(head, _REPORT_WINDOWS[0], moves)

    def _lost_answer(self, head: str, moves) -> None:
        """Finish `head` with `moves` made while the relabel is made, the relabel's answer lost behind it."""
        with self.assertRaises(RuntimeError):
            self._finishes(head, _REPORT_WINDOWS[1], partial(self._loses, moves))

    def _loses(self, moves) -> None:
        """Make `moves`, then lose the answer of the relabel it was made behind."""
        moves()
        raise RuntimeError("the relabel's answer was lost")

    def _loses_the_retirement(self, live, body: str, issue, state, *, over: dict):
        """`live`, the client's pinned edit; the retirement writes `body` as the issue's and lands, its answer lost."""
        if not handoff.BEFORE_THE_RETIREMENT.kills(issue, state, over=over):
            return live(issue, state, over=over)
        self.issue.body = body
        with patch.object(self.gh.pinned_failures, "lost", {self.issue.number}):
            return live(issue, state, over=over)

    def _assert_kept_unless(self, edited: bool, head: str) -> None:
        """The run invalidated whole beside the anchor's evidence where `edited`, and current as settled otherwise."""
        current = readings.pinned_records(self)[1]
        self.assertEqual(current is None, edited)
        invalidated = [self.anchor, head] if edited else []
        self.assertEqual(self._tested(), invalidated)


if __name__ == "__main__":
    unittest.main()
