# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The resume answering a pull request's human feedback, captured as it returns and finished once.

A human comments on a pull request the reviewer approved; `in_review`
bookmarks the batch, stamps `pending_fix_at`, and flips the issue to
`workflow:fixing`, whose tick resumes the developer over that batch. Its report
is captured as it returns, and while an operator holds the issue nothing it was
handed is consumed: the bookmarks, the readers, the round, and the baseline
stand, and the pull request is untouched. Once the control comes off, the
dispatcher's recovery finishes the round from the capture with no developer
launched: the batch the prompt quoted is settled exactly once beside the report
-- never a comment posted later, and never a stretch of the thread no prompt was
handed -- the bookmarks are cleared, the round reset once, the report published
once onto the commit the run left or, with none, the head the pull request
already carries, the approval of the report it replaces covering it no longer,
and the issue handed back for review. A route, a batch, a reader, a pull
request, or requirements moved meanwhile retire the capture; a record nobody
can read holds it. An `ACK:`, a question, or a failure earns no capture, and a
process or an answer lost at the capture or the handoff -- a restart among them
-- is finished by the next dispatch with nothing paid twice.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.workflow.engine import completion_routes as _routes
from orchestrator.workflow.stages.fixing import feedback_road as _feedback_road
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow import (
    captured_fixes as _held,
    drift_reports as _drift_world,
    fix_reports as world,
    human_fix_reports as human,
)
from tests.workflow.fixtures import LABEL_FIXING, _agent, accounted
from tests.workflow.stages.fixing import captured_feedback_support as support
from tests.workflow.stages.fixing.captured_feedback_support import (
    BASELINE,
    BOUNDARY,
    LATER_REPLY,
    PENDING_FIX_AT,
    PENDING_FIX_IDS,
    PR_LAST,
    SPENT_ROUNDS,
)

ISSUE = 2_432

PR = 24_320

DELIVERED_AFTER = "delivered_after_comment_id"
DELIVERED_THROUGH = "delivered_through_comment_id"
PARK_REASON = "park_reason"

# What a held round leaves standing while its capture waits or once it is
# retired: nothing on the pull request, the round unspent, and the label on
# `workflow:fixing`.
_UNSPENT = (0, SPENT_ROUNDS, LABEL_FIXING)

# The two controls an operator holds an issue with.
_CONTROLS = (_held.PAUSED, _held.BACKLOG)

# Every hold the resumed developer may return under, by the control and by
# whether it committed or answered in its report alone.
_HOLDS = tuple(product(_CONTROLS, (True, False)))

# When a comment no prompt of the round carried lands on the pull request:
# while the developer is out, while its held report waits, or as the
# recovery's push lands.
_DURING_THE_RUN = "during the run"
_WHILE_HELD = "while held"
_AS_IT_PUBLISHES = "as the recovery publishes"
_LATER_TIMINGS = (_DURING_THE_RUN, _WHILE_HELD, _AS_IT_PUBLISHES)

# The reply boundary an issue arrives carrying, below the batch the route
# bookmarks; and the delivered stretch beside it, reaching that boundary or
# left short of it by the comments beneath it no prompt was handed.
_BOUNDARY_AT = 40_000
_STRETCHES = (("reaching the boundary", _BOUNDARY_AT, True), ("short of the boundary", _BOUNDARY_AT - 2, False))

def _stretch(through: int) -> dict:
    """The reply boundary the issue arrives carrying, and a delivered stretch from the start through `through`."""
    return {BOUNDARY: _BOUNDARY_AT, DELIVERED_AFTER: 0, DELIVERED_THROUGH: through}


# Records the round froze, moved while it is held, and the stage the move
# leaves the capture in: another route's stamp, another batch bookmarked, a
# reader advanced past what the run was handed, and another pull request
# retire it; each spelled as nothing its own reader takes holds it.
_MOVES = (
    (PENDING_FIX_AT, "2026-11-01T00:00:00+00:00", _held.RETIRED),
    (PENDING_FIX_AT, 7, _held.PENDING),
    (PENDING_FIX_IDS, [4_242], _held.RETIRED),
    (PENDING_FIX_IDS, "not a list", _held.PENDING),
    (PENDING_FIX_IDS, [True], _held.PENDING),
    (PR_LAST, 4_242, _held.RETIRED),
    (PR_LAST, "later", _held.PENDING),
    (PR_LAST, -1, _held.PENDING),
    ("pr_number", PR + 1, _held.RETIRED),
)

# The replies that finish on no report, each as the message it ends on and
# the exit it ends with: an acknowledgement, a question, and a run that
# failed whatever it said.
_ORDINARY = (
    ("an acknowledgement", "ACK: nothing to change", 0),
    ("a question", world.QUESTION_REPLY, 0),
    ("a failure", world.reported(), 1),
)

# What a pull request nobody could read answers.
_UNAVAILABLE = "the pull request could not be read"

# What an operator's `/orchestrator continue` is, and the session park it retries.
_CONTINUE = "/orchestrator continue"
_SILENT = "agent_silent"


class HeldFeedbackTest(unittest.TestCase, support.FeedbackTicks):
    """A held feedback round's report settles exactly what its run was handed, once the recovery finishes it."""

    def test_each_hold_is_finished_once(self) -> None:
        # Under either control, committed or answered in the report alone:
        # held, the capture is taken on the feedback road over the batch and
        # the round the route owes, and nothing else moves -- the bookmarks,
        # the readers, the round, and the pull request stand. Unheld, the
        # recovery settles the frozen pairs, clears the bookmarks, resets the
        # round, publishes the report once, and hands the issue back, the run
        # accounted once and no developer run again. Reconciled twice more,
        # nothing is published, consumed, spent, or accounted again.
        for control, committed in _HOLDS:
            with self.subTest(control=control, committed=committed):
                asked = self.opened(ISSUE, PR, committed=committed)
                self.held_round(control=control, committed=committed)
                held = self.pinned()
                self._held(held, asked)
                self.held_ticks()
                self.unheld(**_held.READING[committed])
                self.finished(held, committed=committed)
                settled = (self.pinned(), self.reports())
                self.reconcile()
                self.reconcile()
                self.assertEqual((self.pinned(), self.reports()), settled)

    def test_a_replayed_batch_is_settled_once(self) -> None:
        # The round's session went silent and an operator's continue replays
        # the batch the route bookmarked. The held replay is captured over the
        # batch and the command beside it; unheld, both are settled once with
        # the report, the park down, and no developer run again.
        self.opened(ISSUE, PR, committed=False)
        world.parked(self, _SILENT)
        world.replied(self, _CONTINUE)
        command = max(comment.id for comment in self.issue.comments)
        replay = self.held_round(committed=False)
        self.assertIn(human.HUMAN_REPORT_FEEDBACK, replay[_held.RUN_AGENT].call_args.args[1])
        held = self.pinned()
        frozen = dict(_held.capture_of(held).handoff.watermarks)
        self.assertEqual(frozen[BOUNDARY], command)
        self.assertEqual(
            self.fields(_held.AWAITING, PARK_REASON, BOUNDARY),
            (True, _SILENT, None),
        )
        self.unheld(**_held.UNMOVED)
        self.finished(held, committed=False)
        self.assertEqual(self.fields(BOUNDARY, PARK_REASON), (command, None))

    def _held(self, held: dict, asked: int) -> None:
        """`held` captured the round on the feedback road over `asked`, with nothing else of the round moved."""
        handoff = _held.capture_of(held).handoff
        spends = dict(handoff.spends)
        self.assertEqual(
            (handoff.route, handoff.origin, tuple(field for field, _digest in handoff.frozen)),
            (_routes.CompletionRoute.PR_FEEDBACK, WorkflowLabel.FIXING, tuple(sorted(_feedback_road.FROZEN))),
        )
        self.assertEqual(
            (dict(handoff.watermarks)[PR_LAST], spends[_held.ROUND], spends[PENDING_FIX_AT]),
            (asked, 0, None),
        )
        self.assertEqual(self.standing(), (_held.PENDING, *_UNSPENT))
        self.assertEqual(
            self.fields(PENDING_FIX_IDS, PR_LAST, BOUNDARY),
            ([asked], 0, None),
        )
        self.assertEqual(self.pull_request.head.sha, world.PUBLISHED_HEAD)


class LaterFeedbackTest(unittest.TestCase, support.FeedbackTicks):
    """What lands after the scan stays the next round's, and a reply on the issue retires the held report."""

    def test_a_later_comment_stays_unread(self) -> None:
        # A human comments on the pull request while the developer is out,
        # while its report is held, or as the recovery's push lands. No
        # prompt of the round carried it, so the recovery settles the readers
        # to the batch alone, and the next in_review scan routes the comment
        # to a round of its own.
        for timing in _LATER_TIMINGS:
            with self.subTest(timing=timing):
                asked = self.opened(ISSUE, PR)
                self.held_round(during=self.comments_on_the_pull_request if timing == _DURING_THE_RUN else None)
                held = self.pinned()
                if timing == _WHILE_HELD:
                    self.comments_on_the_pull_request()
                landing = {"push_branch": support.CommentingPush(self)} if timing == _AS_IT_PUBLISHES else {}
                self.unheld(**_held.COMMITTED, **landing)
                self.finished(held, committed=True)
                self.assertEqual(self.pinned()[PR_LAST], asked)
                self.assertEqual(
                    self.routes_it_afresh(),
                    ((ISSUE, LABEL_FIXING), [self.later.id]),
                )

    def test_an_issue_reply_retires_the_held_report(self) -> None:
        # A human replies on the issue thread while the developer is out, or
        # while its report is held: requirements the run was never handed. The
        # recovery restamps nothing onto the old report: the capture is
        # retired, nothing is published or consumed, the round is unspent,
        # and the baseline stays where the route left it. The next dispatch
        # resumes one developer over the batch and the reply together.
        for during in (True, False):
            with self.subTest(during_the_run=during):
                asked = self.opened(ISSUE, PR, committed=False)
                routed = self.pinned()[BASELINE]
                self.held_round(during=self.replies_later if during else None, committed=False)
                if not during:
                    self.replies_later()
                self.unheld(**_held.UNMOVED)
                self.assertEqual(self.standing(), (_held.RETIRED, *_UNSPENT))
                self.assertEqual(
                    self.fields(PR_LAST, PENDING_FIX_IDS, BASELINE),
                    (0, [asked], routed),
                )
                runs, prompt = self.answered_afresh()
                self.assertEqual(
                    (runs, human.HUMAN_REPORT_FEEDBACK in prompt, LATER_REPLY in prompt),
                    (1, True, True),
                )


class DeliveredStretchTest(unittest.TestCase, support.FeedbackTicks):
    """A recovered round carries the delivered stretch only where its own launch's pairs did."""

    def test_the_stretch_moves_only_from_the_boundary(self) -> None:
        # The issue arrives with its reply boundary below the batch and the
        # stretch of the thread developer prompts were handed either reaching
        # that boundary or left short of it -- the comments beneath it that
        # no prompt was handed, an earlier bounded excerpt's omission among
        # them. The recovery moves the boundary over the batch either way,
        # and carries the stretch over it only where the stretch already
        # reached the boundary: an omission is never recorded as delivered.
        for described, through, carried in _STRETCHES:
            with self.subTest(stretch=described):
                asked = self.opened(ISSUE, PR, committed=False, **_stretch(through))
                self.held_round(committed=False)
                self.unheld(**_held.UNMOVED)
                self.assertEqual(self.standing(), support.HANDED_BACK)
                self.assertEqual(
                    self.fields(BOUNDARY, DELIVERED_AFTER, DELIVERED_THROUGH),
                    (asked, 0, asked if carried else through),
                )


class MovedRoadTest(unittest.TestCase, support.FeedbackTicks):
    """A held round over a route, batch, reader, or pull request moved since is retired; over damage or a hold, kept."""

    def test_a_moved_record_retires_or_holds_it(self) -> None:
        # Each record the round froze, rewritten while it is held: a move the
        # record's own reader takes is another road's, and retires the
        # capture with nothing published, consumed, or spent; a spelling no
        # reader takes is damage, and holds it with nothing written.
        for field, spelled, stage in _MOVES:
            with self.subTest(field=field, spelled=spelled):
                self.opened(ISSUE, PR, committed=False)
                self.held_round(committed=False)
                self.hand_edit(**{field: spelled})
                before = (self.pinned(), self.github.write_state_calls)
                self.unheld(**_held.UNMOVED)
                self.assertEqual(self.standing(), (stage, *_UNSPENT))
                if stage == _held.PENDING:
                    self.assertEqual((self.pinned(), self.github.write_state_calls), before)

    def test_a_control_during_the_reads_holds_it(self) -> None:
        # An operator applies `paused` or `backlog` as a pull request read
        # the recovery takes is answered -- the admission's, its effect's, or
        # the fixing tick's own fetch of the handles it finishes the round
        # with -- every one ahead of the issue's last fetch before the
        # handoff, which reads the control. The capture is held with nothing
        # written: nothing published or consumed, the round unspent, the
        # readers where they stood. With the control off, the next dispatch
        # finishes the round once.
        reads = range(1, self.reads_ahead_of_the_handoff(ISSUE, PR))
        for control, at in product(_CONTROLS, reads):
            with self.subTest(control=control, read=at):
                self.opened(ISSUE, PR, committed=False)
                self.held_round(committed=False)
                self.lifts_the_control()
                before = (self.pinned(), self.github.write_state_calls)
                reading = support.ControlAtRead(self, control, at)
                with patch.object(self.github, "get_pr", side_effect=reading.read):
                    self.dispatched(**_held.UNMOVED)[_held.RUN_AGENT].assert_not_called()
                self.assertEqual((self.pinned(), self.github.write_state_calls), before)
                self.control = control
                self.unheld(**_held.UNMOVED)
                self.finished(before[0], committed=False)

    def test_a_pushed_over_pull_request_retires_it(self) -> None:
        # Somebody pushes onto the pull request while the report is held: the
        # head is neither the one the run started on nor the one it reported
        # on, so the capture is retired and nothing is published over it.
        self.opened(ISSUE, PR, committed=False)
        self.held_round(committed=False)
        self.pull_request.head.sha = _drift_world.CONCURRENT_HEAD
        self.unheld(**_held.UNMOVED)
        self.assertEqual(self.standing(), (_held.RETIRED, *_UNSPENT))
        self.assertEqual(self.pull_request.head.sha, _drift_world.CONCURRENT_HEAD)

    def test_an_unread_pull_request_holds_it(self) -> None:
        # The pull request will not read as the control comes off: nothing
        # proves the capture stale, so it is held with nothing written, and
        # the next dispatch that reads it finishes the round once.
        self.opened(ISSUE, PR, committed=False)
        self.held_round(committed=False)
        held = self.pinned()
        before = (held, self.github.write_state_calls)
        with patch.object(self.github, "get_pr", side_effect=RuntimeError(_UNAVAILABLE)):
            self.unheld(**_held.UNMOVED)
        self.assertEqual((self.pinned(), self.github.write_state_calls), before)
        self.dispatched(**_held.UNMOVED)[_held.RUN_AGENT].assert_not_called()
        self.finished(held, committed=False)


class OrdinaryOutcomeTest(unittest.TestCase, support.FeedbackTicks):
    """An acknowledgement, a question, or a failure earns no capture, so its held return buys no replay."""

    def test_no_report_no_capture(self) -> None:
        # Held as it returns, each is accounted once and nothing else of it
        # is kept: no capture, the batch unconsumed, the round unspent. With
        # the control off, the next dispatch answers the batch with a
        # developer of its own, since nothing durable describes what the held
        # one said.
        for described, message, exit_code in _ORDINARY:
            with self.subTest(reply=described):
                self.opened(ISSUE, PR, committed=False)
                self.held_round(
                    _agent(session_id=world.DEV_SESSION, last_message=message, exit_code=exit_code), committed=False,
                )
                self.assertNotIn(_held.CAPTURED, self.pinned())
                self.assertEqual(self.fields(PR_LAST, _held.ROUND), (0, SPENT_ROUNDS))
                self.assertEqual(accounted(self.pinned()), (1, 1))
                self.lifts_the_control()
                self.assertEqual(self.answered_afresh()[0], 1)
                self.assertEqual(self.reports(), 1)
                self.assertEqual(accounted(self.pinned()), (2, 2))


class LostFeedbackHandoffTest(unittest.TestCase, support.FeedbackTicks):
    """A round lost at its capture or its handoff is finished by the next dispatch, nothing paid twice."""

    def test_a_live_round_lost_at_its_handoff(self) -> None:
        # The live round's process is lost as the report's handoff goes out,
        # or right after it landed with the commit not yet pushed; or the
        # handoff lands with its answer lost, the tick held. The next dispatch
        # finishes the round once either way, from the capture or from the
        # delivery the handoff left, with no developer run.
        for lost in (_held.SENT, _held.LANDED, _held.ANSWER):
            with self.subTest(lost=lost):
                self.opened(ISSUE, PR)
                self._lost(_held.LostAtTheHandoff, lost, self.live_round)
                handed = lost != _held.SENT
                self.assertEqual(
                    (_held.stage_of(self.pinned()), self.reports()),
                    (_held.HANDED_OFF if handed else _held.PENDING, 0),
                )
                self.finished_once(handed=handed)

    def test_a_live_round_lost_at_its_capture(self) -> None:
        # The capture lands and the process is lost behind it -- a restart --
        # or its answer is lost and the tick holds as a pause would: either
        # way nothing of the round is written past it, and the next dispatch
        # finishes the round once from the capture.
        for lost in (_held.LANDED, _held.ANSWER):
            with self.subTest(lost=lost):
                asked = self.opened(ISSUE, PR)
                self._lost(partial(_held.LostAtTheHandoff, stage=_held.PENDING), lost, self.live_round)
                self.assertEqual(self.standing(), (_held.PENDING, *_UNSPENT))
                self.assertEqual(self.fields(PR_LAST, PENDING_FIX_IDS), (0, [asked]))
                self.finished_once(handed=False)

    def test_a_recovery_lost_at_its_handoff(self) -> None:
        # The same losses in the recovery of a held round: whichever the
        # dispatch behind it finds, a capture to recover again or a delivery
        # to bind, it finishes the round once.
        for lost in (_held.SENT, _held.LANDED, _held.ANSWER):
            with self.subTest(lost=lost):
                self.opened(ISSUE, PR)
                self.held_round()
                self._lost(_held.LostAtTheHandoff, lost, partial(self.unheld, **_held.COMMITTED))
                self.finished_once(handed=lost != _held.SENT)

    def _lost(self, losing, lost: str, ticked) -> None:
        """Run `ticked` with the process, or the answer, lost at the edit `losing` names."""
        with patch.object(self.github, "edit_pinned_state", losing(self.github, lost)):
            try:
                ticked()
            except SystemExit:
                self.assertNotEqual(lost, _held.ANSWER)


if __name__ == "__main__":
    unittest.main()
