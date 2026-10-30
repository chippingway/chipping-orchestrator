# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured completion handed to the existing report delivery: one commit, one owner of the report.

The transfer records the delivered report through the delivery's own write --
minted past every report the issue holds, under the route, requirements,
delivered input and round settlement the road froze -- and hands the capture
off in that very commit, retiring with it whatever its road names. Asked
again, after a lost response or a restart, it finds the handoff it landed and
records nothing twice; an edit nobody confirmed never lets the only copy of a
report be retired. A capture not pending, a handoff another road moved, a
verification of another repository, and a delivery the comment has no room
for are each answered as refusals, parking nothing. A delivery handed off
from a capture is bound only to the commit that capture reported on
(`test_completion_binding`).
"""
from __future__ import annotations

import contextlib
import dataclasses
import unittest
from types import MappingProxyType

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_frozen as _frozen,
    completion_handoff as _handoff,
    completion_records as _records,
    completion_routes as _routes,
    completion_spelling as _spelling,
    completion_state as _state,
    report_delivery_state as _delivery_state,
)
from orchestrator.workflow.engine.report_record_room import CommentOverflow, MeasuredWrite
from orchestrator.workflow.engine.report_records import DELIVERED_REPORT, DeliveredReport, ReportMode
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import completion_test_support as support, report_commit_test_support as commit_support

_STATUS = support.STATUS
_ELSEWHERE = support.VERIFIED.replace(support.REPO, "someone/else")
_REPOSITORY_READ = "is_own_repository"
_DAMAGED_CAPTURE = MappingProxyType({support.FIELD: None})
_REFUSAL = support.REFUSAL
_STAGE = support.STAGE
_INVALIDATED = _records.RetirementReason.INVALIDATED
_TRANSFER = _handoff.transfer
_READ_BACK = _checkpoint.read_back
_RETIRE = _checkpoint.retire
_VERDICT = "review_returned_verdict"
_RETIRES = ((_VERDICT, None),)

# How much room a comment is left with once another road has filled it.
_LEFT = 64

# The writes a capture and its transfer send between them.
_CAPTURED_AND_HANDED = 2

# What a park would have written.
_PARK = ("awaiting_human", "park_reason")

# A verdict the change request answered, and the one another road moves it to.
_HANDED_VERDICT = MappingProxyType({_VERDICT: {"round": 2}})
_MOVED_VERDICT = MappingProxyType({_VERDICT: {"round": 3}})

# The feedback a change request's prompt delivered, and the round it closes.
_WATERMARKS = (("pr_last_comment_id", 55),)
_SPENDS = (("review_round", 3), ("pending_fix_at", None))

# What the transfer of that road's capture records.
_ROAD_DELIVERY = DeliveredReport(
    receipt="issue-2426-report-1",
    report_revision=1,
    mode=ReportMode.PUBLISH,
    route=WorkflowLabel.FIXING,
    requirements_revision=support.REQUIREMENTS,
    report=support.REPORT,
    watermarks=_WATERMARKS,
    spends=_SPENDS,
)

# What a transfer leaves exactly as the record had it: the feedback watermark
# and the round, settled only once the report is, and the usage meter.
_UNMOVED = ("pr_last_comment_id", "review_round", "issue_agent_runs")

# A report the comment carries five characters wider per terminator once each
# is escaped, and how wide a note another road writes beside its capture: wide
# enough that the delivery's own record, or the transaction its binding
# reserves, is past the ceiling escaped in full, and which of the two is.
_TERMINATORS = 2000
_TERMINATED = "REPORT: READY\n{report}\nREPORT: END".format(report="-->" * _TERMINATORS)
_FILLED_SINCE = ((52000, MeasuredWrite.RECORD), (48000, MeasuredWrite.BINDING))

# An earlier report delivered and never bound, which a transfer supersedes.
_OLDER = DeliveredReport(
    receipt="issue-2426-report-2",
    report_revision=2,
    mode=ReportMode.PUBLISH,
    route=WorkflowLabel.IMPLEMENTING,
    requirements_revision=support.REQUIREMENTS,
    report="An older report nobody published.",
    spends=(("review_round", 1),),
)


def _handed(world: support.CompletionWorld) -> _records.CompletionHandoff:
    """A change request's road, its verdict frozen over the reading the caller holds."""
    return dataclasses.replace(
        support.IMPLEMENTATION,
        route=_routes.CompletionRoute.REQUESTED_CHANGES,
        origin=WorkflowLabel.FIXING,
        watermarks=_WATERMARKS,
        spends=_SPENDS,
        frozen=_frozen.frozen_over(world.state, (_VERDICT,)),
    )


def _captured(world: support.CompletionWorld, **completion) -> _records.CompletionCapture:
    """Capture one completed run on `world`, and answer what was captured."""
    captured = world.completion(**completion)
    world.captures(captured)
    return captured


def _delivered(world: support.CompletionWorld) -> DeliveredReport | None:
    """The delivered report the issue's comment carries now."""
    return _delivery_state.read_delivered_report(PinnedState(state_data=world.record()))


def _stage(world: support.CompletionWorld) -> _records.CaptureStage | None:
    """The stage of the capture the issue's comment carries now."""
    captured = _state.read(PinnedState(state_data=world.record()))
    return None if captured is None else captured.stage


def _unpending() -> tuple:
    """Issues carrying no capture of charge 1 to hand on, and what each transfer of it is refused as."""
    other = support.seeded()
    _captured(other, ordinal=2)
    retired = support.seeded()
    _captured(retired)
    retired.asks(_RETIRE, retired.invocation(), _INVALIDATED)
    return (
        (support.seeded(), _REFUSAL.ABSENT),
        (other, _REFUSAL.ABSENT),
        (retired, _REFUSAL.RETIRED),
        (support.seeded(**{support.FIELD: {"stage": "pending"}}), _REFUSAL.DAMAGED),
    )


class TransferTest(unittest.TestCase):
    """What one transfer records, and what it refuses with nothing written."""

    def transferred(self) -> tuple:
        """A change request's capture handed on: the world, and what the transfer answered."""
        world = support.seeded(**_HANDED_VERDICT)
        captured = _captured(world, handoff=_handed(world))
        return world, world.asks(_TRANSFER, captured.invocation, _RETIRES)

    def test_the_delivery_and_handoff_land_together(self) -> None:
        """One more write records the delivery on the road's terms, hands the capture off, and retires its verdict.

        It settles nothing else -- no watermark, round, or usage counter --
        and what it wrote is laid onto the caller as the comment's.
        """
        world, outcome = self.transferred()
        record = world.record()
        answered = (outcome.status, outcome.stage, world.github.write_state_calls)
        self.assertEqual(answered, (_STATUS.LANDED, _STAGE.HANDED_OFF, 2))
        self.assertEqual(_delivered(world), _ROAD_DELIVERY)
        observed = (
            record[support.FIELD],
            record[_VERDICT],
            *map(record.get, _UNMOVED),
        )
        self.assertEqual(observed, (
            _spelling.spelled(_records.ResolvedCapture(
                world.invocation(), _STAGE.HANDED_OFF, receipt=_ROAD_DELIVERY.receipt, report_revision=1,
                branch=support.BRANCH, source_sha=support.SOURCE,
            )),
            None, None, None, None,
        ))
        self.assertEqual(world.state.get(DELIVERED_REPORT), record[DELIVERED_REPORT])

    def test_a_verified_capture_is_delivered_as_one(self) -> None:
        """A VERIFIED capture becomes a verification owed at its location, with no text."""
        world = support.seeded()
        captured = _captured(world, message=support.VERIFIED)
        world.asks(_TRANSFER, captured.invocation)
        delivered = _delivered(world)
        observed = (
            delivered.mode,
            delivered.report,
            delivered.location.pr_number,
            delivered.content_revision,
        )
        self.assertEqual(observed, (ReportMode.VERIFY, "", support.VERIFIED_PR, support.VERIFIED_REVISION))

    def test_the_revision_moves_past_every_report(self) -> None:
        """A delivery standing unbound is superseded: its revision passed, its bookkeeping carried, its text gone."""
        alone = PinnedState()
        _delivery_state.stage_delivered_report(alone, _OLDER)
        world = support.seeded(**{DELIVERED_REPORT: alone.get(DELIVERED_REPORT)})
        world.asks(_TRANSFER, _captured(world).invocation)
        delivered = _delivered(world)
        self.assertEqual((delivered.report_revision, delivered.spends), (3, _OLDER.spends))
        self.assertNotIn(_OLDER.report, pinned_state_body(world.record()))

    def test_a_capture_not_pending_is_not_handed_on(self) -> None:
        """No capture, another invocation's, a retired one, or a damaged one transfers nothing."""
        for world, refusal in _unpending():
            before = world.snapshot()
            outcome = world.asks(_TRANSFER, world.invocation())
            with self.subTest(refusal=refusal):
                self.assertEqual((outcome.refusal, world.snapshot()), (refusal, before))

    def test_a_moved_handoff_is_not_answered(self) -> None:
        """A verdict the road froze, moved by another road since, refuses the transfer with nothing written."""
        world = support.seeded(**_HANDED_VERDICT)
        captured = _captured(world, handoff=_handed(world))
        commit_support.another_road(world.github, world.issue, **_MOVED_VERDICT)
        before = world.snapshot()
        outcome = world.asks(_TRANSFER, captured.invocation, _RETIRES)
        observed = (outcome.refusal, outcome.fields, world.snapshot())
        self.assertEqual(observed, (_REFUSAL.HANDOFF_MOVED, (_VERDICT,), before))


    def test_a_comment_filled_since_refuses_it(self) -> None:
        """Measured afresh and escaped in full, a comment another road filled since the capture refuses the transfer.

        The capture stays pending with its report, and nothing is written or
        parked.
        """
        for width, write in _FILLED_SINCE:
            world = support.seeded()
            _captured(world, message=_TERMINATED)
            commit_support.another_road(world.github, world.issue, operator_note="x" * width)
            world = world.restarted()
            before = world.snapshot()
            refusal = world.asks(_TRANSFER, world.invocation()).refusal
            with self.subTest(write=write):
                self.assertIsInstance(refusal, CommentOverflow)
                self.assertIs(refusal.write, write)
                self.assertEqual(world.snapshot(), before)
                self.assertIs(_stage(world), _STAGE.PENDING)


class UnsettledTransferTest(unittest.TestCase):
    """A transfer nobody confirmed, one the comment has no room for, and one no delivery can be made of."""

    def sent(self, failure: str) -> tuple:
        """Capture charge 1 and transfer it, its edit failing as `failure`: its answer, and the issue restarted."""
        world = support.seeded()
        _captured(world)
        failures = getattr(world.github.pinned_failures, failure)
        failures.add(support.ISSUE)
        sent = (world.asks(_TRANSFER, world.invocation()).status, world.state.withheld)
        failures.clear()
        return sent, world.restarted()

    def lost(self) -> support.CompletionWorld:
        """An issue whose capture's transfer landed with its answer lost, as the caller that sent it still holds it."""
        world = support.seeded()
        _captured(world)
        world.github.pinned_failures.lost.add(support.ISSUE)
        world.asks(_TRANSFER, world.invocation())
        world.github.pinned_failures.lost.clear()
        return world

    def test_a_lost_answer_is_confirmed_to_its_caller(self) -> None:
        """A read-back or a retry by the very caller that lost the answer hands it the delivery that landed."""
        for operation in (_READ_BACK, _TRANSFER):
            world = self.lost()
            answer = world.asks(operation, world.invocation())
            caller = (answer.stage, answer.settled, _delivery_state.read_delivered_report(world.state))
            with self.subTest(operation=operation.__name__):
                self.assertIsNotNone(_delivered(world))
                self.assertEqual(caller, (_STAGE.HANDED_OFF, True, _delivered(world)))

    def test_a_lost_response_records_nothing_twice(self) -> None:
        """The handoff landed and its answer was lost: the read-back finds it, and asking again records nothing."""
        sent, restarted = self.sent("lost")
        read_back = restarted.asks(_READ_BACK, restarted.invocation())
        again = restarted.asks(_TRANSFER, restarted.invocation())
        self.assertEqual(sent, (_STATUS.UNCONFIRMED, True))
        stages = {read_back.stage, again.stage, _stage(restarted)}
        self.assertEqual(stages, {_STAGE.HANDED_OFF})
        self.assertEqual(_delivered(restarted).report_revision, 1)
        self.assertEqual(restarted.github.write_state_calls, _CAPTURED_AND_HANDED)

    def test_a_refused_edit_keeps_the_only_copy(self) -> None:
        """The handoff never landed: the capture reads back pending and refuses a settled retirement."""
        sent, restarted = self.sent("refused")
        invocation = restarted.invocation()
        read_back = restarted.asks(_READ_BACK, invocation)
        retired = restarted.asks(_RETIRE, invocation, _records.RetirementReason.SETTLED)
        self.assertEqual(
            (sent[0], read_back.stage, retired.refusal, _delivered(restarted)),
            (_STATUS.UNCONFIRMED, _STAGE.PENDING, _REFUSAL.NOT_HANDED_OFF, None),
        )
        self.assertIs(restarted.asks(_TRANSFER, restarted.invocation()).status, _STATUS.LANDED)

    def test_a_crowded_comment_is_answered_not_parked(self) -> None:
        """Filled since the capture, the comment has no room for the delivery: refused for room, parking nothing."""
        world = support.seeded()
        _captured(world)
        room = MAX_PINNED_BODY - len(pinned_state_body(world.record())) - _LEFT
        commit_support.another_road(world.github, world.issue, operator_note="x" * room)
        restarted = world.restarted()
        refusal = restarted.asks(_TRANSFER, restarted.invocation()).refusal
        self.assertIsInstance(refusal, CommentOverflow)
        parked = tuple(map(restarted.record().get, _PARK))
        self.assertEqual(parked, (None, None))
        self.assertIs(_stage(restarted), _STAGE.PENDING)

    def test_another_repository_is_unrecordable(self) -> None:
        """A verification of somebody else's repository earns no delivery, its capture pending and its caller writable.

        Unless the comment moved during that repository read: a capture a
        hand edit damaged meanwhile holds the caller back, and survives the
        caller's whole-state write behind the refusal.
        """
        for edited in (False, True):
            world = support.seeded()
            invocation = _captured(world, message=_ELSEWHERE).invocation
            during = contextlib.nullcontext()
            if edited:
                during = commit_support.behind(world.github, world.issue, _REPOSITORY_READ, **_DAMAGED_CAPTURE)
            with during:
                refusal = world.asks(_TRANSFER, invocation).refusal
            world.github.write_pinned_state(world.issue, world.state)
            with self.subTest(edited=edited):
                self.assertIs(refusal, _REFUSAL.UNRECORDABLE)
                self.assertIs(world.state.withheld, edited)
                self.assertIn(support.FIELD, world.record())
                self.assertIs(_stage(world) is None, edited, "a capture damaged meanwhile is kept, not written back")


if __name__ == "__main__":
    unittest.main()
