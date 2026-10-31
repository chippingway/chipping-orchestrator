# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The completion checkpoint: one capture per issue, landed, read back, and retired through guarded commits.

What a capture lands -- its own field and nothing the caller staged -- and
what it refuses with nothing written: another invocation's unresolved capture,
a return older than one already resolved, a damaged capture, a record admission
refuses, deleted, replaced, or unreadable, and an invocation of another record
or cycle. That asking again sends nothing, that a write nobody confirmed is
settled only by its read-back, and that the only copy of a report is never
retired on the strength of a handoff nobody confirmed.
"""
from __future__ import annotations

import dataclasses
import json
import unittest
from types import MappingProxyType

from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_frozen as _frozen,
    completion_handoff as _handoff,
    completion_records as _records,
    completion_routes as _routes,
    completion_spelling as _spelling,
    report_delivery as _delivery,
)
from orchestrator.workflow.engine.pinned_commit_models import CommitRefusal
from orchestrator.workflow.engine.report_record_values import MAX_REPORT_TEXT, RecordRefusal
from orchestrator.workflow.engine.report_records import HandedRun
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import (
    completion_edits_support as edits,
    completion_test_support as support,
    report_commit_test_support as commit_support,
)

_STATUS = support.STATUS
_REFUSAL = support.REFUSAL
_STAGE = support.STAGE
_REASON = _records.RetirementReason
_LANDED = _STATUS.LANDED
_STANDING = _STATUS.STANDING
_REFUSED = _STATUS.REFUSED
_CAPTURE = _checkpoint.capture
_READ_BACK = _checkpoint.read_back
_RETIRE = _checkpoint.retire
_WATERMARK = "pr_last_comment_id"
_DELIVERED = "developer_report_delivery"
_VERDICT = "review_returned_verdict"

# A change request's run as the transfer is handed it: the verdict its report answers, retired with it.
_ANSWERING = HandedRun(WorkflowLabel.FIXING, retires=((_VERDICT, None),))

# A report past the ceiling the report records hold every report to.
_TOO_LONG = "REPORT: READY\n{report}\nREPORT: END".format(report="x" * (MAX_REPORT_TEXT + 1))

# Hand edits since a caller read the comment, and what a capture of a report
# past its ceiling is refused as over each.
_STALE_EDITS = (
    ({support.FIELD: None}, _REFUSAL.DAMAGED),
    ({"operator_note": "edited by hand"}, RecordRefusal.REPORT_TOO_LONG),
)

# A later run's own report, recorded over the capture's delivery.
_LATER_REPORT = "A later invocation's complete report."
_LATER = f"REPORT: READY\n{_LATER_REPORT}\nREPORT: END"
_MOVED_WATERMARK = 99

# What the issue carries besides its requirements before anything is captured:
# a pinned session, a watermark, a park, and a round -- none of them a
# capture's to move.
_CARRIED = MappingProxyType({
    "dev_session_id": "session-0",
    _WATERMARK: 40,
    "awaiting_human": True,
    "park_reason": "agent_question",
    "review_round": 2,
})

# What the caller stages over its state before asking: a returned session,
# a consumed watermark, and the park the reply answered taken down.
_STAGED = MappingProxyType({
    "dev_session_id": support.SESSION,
    _WATERMARK: 55,
    "awaiting_human": False,
})

_LATE_CYCLE = 7

# Identities of another record, or of a cycle the record is not on, and what
# each is refused as.
_ELSEWHERE = (
    ({"issue": support.ISSUE + 1}, _REFUSAL.FOREIGN),
    ({"repo": "someone/else"}, _REFUSAL.FOREIGN),
    ({"comment": 1}, _REFUSAL.FOREIGN),
    ({"cycle": _LATE_CYCLE}, _REFUSAL.OTHER_CYCLE),
)

# Hand edits admission refuses, and what each is refused as.
_UNADMITTED = (
    ({"unreadable": True}, CommitRefusal.UNREADABLE),
    ({"malformed": True}, CommitRefusal.MALFORMED),
    ({"unsupported": True}, CommitRefusal.UNSUPPORTED),
    ({}, CommitRefusal.REPLACED),
    ({"replaced": True}, CommitRefusal.REPLACED),
)

# Captures and cycle identities nobody reads.
_DAMAGED = (
    {support.FIELD: {"stage": "pending"}},
    {support.FIELD: None},
    {"late_cycle_id": "seven"},
)


def _quietly(world: support.CompletionWorld, operation, *arguments) -> tuple:
    """Ask `operation` of `world`: its status and refusal, and whether issue and caller stood as they were."""
    before = world.snapshot()
    outcome = world.asks(operation, *arguments)
    return outcome.status, outcome.refusal, world.snapshot() == before


def _answered(outcome) -> tuple:
    """One answer's status and the stage it leaves the capture at."""
    return outcome.status, outcome.stage


def _edited(world: support.CompletionWorld, *, unreadable=False, replaced=False, **unpinned) -> None:
    """Edit `world`'s comment by hand: unreadable, re-pinned under a new comment, or as `edits.unpinned` does."""
    if unreadable:
        world.github.pinned_failures.unreadable.add(support.ISSUE)
    elif replaced:
        world.github.seed_state(world.issue, **world.record())
    else:
        edits.unpinned(world, **unpinned)


class CaptureLandsTest(unittest.TestCase):
    """What one capture writes, and what asking again writes."""

    def test_a_capture_lands_its_own_field_alone(self) -> None:
        """Only `developer_completion` moves; the caller's staged session, watermark, and park stay unwritten."""
        world = support.seeded(**_CARRIED)
        world.state.state_data.update(_STAGED)
        completion = world.completion()
        expected = {**world.record(), support.FIELD: _spelling.spelled(completion)}
        self.assertEqual(_answered(world.captures(completion)), (_LANDED, _STAGE.PENDING))
        self.assertEqual((world.record(), world.github.write_state_calls), (expected, 1))
        synced = json.loads(world.state.synced)
        self.assertEqual(
            (world.state.get(support.FIELD), synced[support.FIELD]),
            (expected[support.FIELD], expected[support.FIELD]),
            "the capture is laid back onto the caller as the comment's",
        )
        staged = {key: world.state.get(key) for key in _STAGED}
        self.assertEqual(staged, dict(_STAGED))
        self.assertFalse(world.state.withheld, "a comment that moved nowhere holds the caller back from nothing")

    def test_asking_again_sends_nothing(self) -> None:
        """A capture asked again, or after a restart, reads back as standing; so does its read-back."""
        world = support.seeded()
        completion = world.completion()
        world.captures(completion)
        restarted = world.restarted()
        answers = (
            world.captures(completion),
            restarted.captures(completion),
            restarted.asks(_READ_BACK, completion.invocation),
        )
        answered = {(*_answered(answer), answer.settled) for answer in answers}
        self.assertEqual(answered, {(_STANDING, _STAGE.PENDING, True)})
        self.assertEqual(world.github.write_state_calls, 1)

    def test_an_unresolved_capture_is_never_replaced(self) -> None:
        """Another invocation's return is refused while a capture is pending, with nothing written."""
        world = support.seeded()
        world.captures(world.completion())
        refused = _quietly(world, _CAPTURE, world.completion(2))
        self.assertEqual(refused, (_REFUSED, _REFUSAL.UNRESOLVED, True))

    def test_a_resolved_capture_refuses_older_returns(self) -> None:
        """Past a resolved capture only a later charge is taken; this one reads back, an earlier one is stale."""
        world = support.seeded()
        world.captures(world.completion(2))
        retired = world.asks(_RETIRE, world.invocation(2), _REASON.INVALIDATED)
        older = _quietly(world, _CAPTURE, world.completion(1))
        same = world.captures(world.completion(2))
        later = world.captures(world.completion(3))
        self.assertEqual(
            (retired.stage, older, _answered(same), _answered(later)),
            (
                _STAGE.RETIRED,
                (_REFUSED, _REFUSAL.SUPERSEDED, True),
                (_STANDING, _STAGE.RETIRED),
                (_LANDED, _STAGE.PENDING),
            ),
        )

    def test_another_roads_move_is_kept_or_refuses(self) -> None:
        """A field the capture does not own keeps another road's move; a moved capture refuses the commit."""
        world = support.seeded(**_CARRIED)
        with edits.interfering(world, **{_WATERMARK: _MOVED_WATERMARK}):
            kept = world.captures(world.completion())
        moved = support.seeded()
        other = _spelling.spelled(moved.completion(2))
        with edits.interfering(moved, **{support.FIELD: other}):
            refused = moved.captures(moved.completion())
        self.assertIs(kept.status, _LANDED)
        self.assertEqual(world.record()[_WATERMARK], _MOVED_WATERMARK)
        self.assertEqual(
            (refused.refusal, refused.fields),
            (CommitRefusal.PREREQUISITE_CHANGED, (support.FIELD,)),
        )


    def test_a_stale_retry_keeps_the_handoff(self) -> None:
        """A retry from a caller that read the capture before its transfer is handed the delivery owning the report.

        That caller's own whole-state write behind the answer keeps the
        delivery, rather than putting back a record without it.
        """
        world = support.seeded()
        completion = world.completion()
        world.captures(completion)
        stale = world.restarted()
        world.asks(_handoff.transfer, completion.invocation)
        answer = stale.captures(completion)
        stale.github.write_pinned_state(stale.issue, stale.state)
        self.assertEqual(_answered(answer), (_STANDING, _STAGE.HANDED_OFF))
        record = world.record()
        self.assertIsNotNone(record.get(_DELIVERED))
        self.assertEqual(record[support.FIELD], stale.state.get(support.FIELD))


class CaptureAdmissionTest(unittest.TestCase):
    """What a capture, its read-back, and its retirement refuse with nothing written."""

    def assert_refused(self, world: support.CompletionWorld, refusal) -> None:
        """The capture, read-back, and retirement of charge 1 are each refused as `refusal`, writing nothing."""
        invocation = world.invocation()
        asked = (
            (_CAPTURE, world.completion()),
            (_READ_BACK, invocation),
            (_RETIRE, invocation, _REASON.INVALIDATED),
        )
        for operation, *arguments in asked:
            with self.subTest(operation=operation.__name__, refusal=refusal):
                answered = _quietly(world, operation, *arguments)
                self.assertEqual(answered, (_REFUSED, refusal, True))

    def test_a_record_admission_refuses_is_left_alone(self) -> None:
        """A comment unreadable, unparsed, unsupported, deleted, or replaced refuses all three as the commit does."""
        for edit, refusal in _UNADMITTED:
            world = support.seeded()
            _edited(world, **edit)
            self.assert_refused(world, refusal)

    def test_a_damaged_capture_or_cycle_is_held(self) -> None:
        """A capture or a cycle identity nobody reads is never replaced, read as absent, or retired."""
        for damaged in _DAMAGED:
            self.assert_refused(support.seeded(**damaged), _REFUSAL.DAMAGED)

    def test_another_records_invocation_is_refused(self) -> None:
        """Another issue, repository, or comment is foreign, and another cycle is no longer the record's."""
        for overrides, refusal in _ELSEWHERE:
            world = support.seeded()
            elsewhere = dataclasses.replace(world.completion(), invocation=world.invocation(**overrides))
            with self.subTest(overrides=overrides):
                self.assertEqual(_quietly(world, _CAPTURE, elsewhere), (_REFUSED, refusal, True))


    def test_a_damaged_claim_outlives_a_stale_caller(self) -> None:
        """A capture refused over a claim damaged since its caller read the comment holds that caller back.

        The caller's own whole-state write behind the refusal then writes
        nothing, so the claim is never taken for an absence and erased.
        """
        world = support.seeded()
        edited = world.github.read_pinned_state(world.issue)
        edited.set(support.FIELD, None)
        world.github.write_pinned_state(world.issue, edited)
        refusal = world.captures(world.completion()).refusal
        world.github.write_pinned_state(world.issue, world.state)
        self.assertEqual((refusal, world.state.withheld), (_REFUSAL.DAMAGED, True))
        self.assertIsNone(world.record()[support.FIELD])


    def test_a_refused_commit_withholds_its_caller(self) -> None:
        """A capture refused because a hand edit damaged the claim under its commit holds its caller back.

        The caller's own whole-state write behind the refusal then writes
        nothing, so the claim the edit left is never erased.
        """
        world = support.seeded()
        completion = world.completion()
        with edits.interfering(world, **{support.FIELD: None}):
            refusal = world.asks(_CAPTURE, completion).refusal
        world.github.write_pinned_state(world.issue, world.state)
        self.assertEqual((refusal, world.state.withheld), (CommitRefusal.PREREQUISITE_CHANGED, True))
        self.assertIsNone(world.record()[support.FIELD])

    def test_a_report_refusal_holds_a_stale_caller(self) -> None:
        """A report refused for its own reading is refused over the comment read afresh, holding a stale caller back.

        A hand edit since the caller read the comment -- a damaged claim, or
        any other field -- survives that caller's whole-state write behind the
        refusal; the damaged claim is the refusal named first.
        """
        for edit, refusal in _STALE_EDITS:
            world = support.seeded()
            completion = world.completion(message=_TOO_LONG)
            commit_support.another_road(world.github, world.issue, **edit)
            refused = world.asks(_CAPTURE, completion).refusal
            world.github.write_pinned_state(world.issue, world.state)
            with self.subTest(refusal=refusal):
                self.assertEqual((refused, world.state.withheld), (refusal, True))
                self.assertEqual({key: world.record()[key] for key in edit}, edit)


class UncertainCaptureTest(unittest.TestCase):
    """A write sent and never confirmed is settled by its read-back alone."""

    def sent(self, failure: str) -> tuple:
        """Capture charge 1 with its edit failing as `failure`: what it answered, and the issue a restart reads."""
        world = support.seeded()
        failures = getattr(world.github.pinned_failures, failure)
        failures.add(support.ISSUE)
        outcome = world.captures(world.completion())
        failures.clear()
        return (outcome.status, outcome.settled, world.state.withheld), world.restarted()

    def test_a_lost_response_reads_back_as_landed(self) -> None:
        """The edit landed and its answer was lost: the caller is withheld, and the read-back finds the capture."""
        sent, restarted = self.sent("lost")
        read_back = restarted.asks(_READ_BACK, restarted.invocation())
        retried = restarted.captures(restarted.completion())
        self.assertEqual(
            (sent, _answered(read_back), retried.status),
            ((_STATUS.UNCONFIRMED, False, True), (_STANDING, _STAGE.PENDING), _STANDING),
        )
        self.assertEqual(restarted.github.write_state_calls, 1)

    def test_a_refused_edit_reads_back_as_absent(self) -> None:
        """The edit never landed: the read-back finds no capture of this run, and asking again lands it."""
        sent, restarted = self.sent("refused")
        read_back = restarted.asks(_READ_BACK, restarted.invocation())
        retried = restarted.captures(restarted.completion())
        self.assertEqual(
            (sent, _answered(read_back), retried.status),
            ((_STATUS.UNCONFIRMED, False, True), (_STANDING, None), _LANDED),
        )


    def test_a_stale_read_back_writes_nothing_back(self) -> None:
        """A read-back by a caller that read the capture before its transfer leaves the road's retirement standing.

        The transfer retired the road's verdict with the report; the caller
        still holds it, so the read-back holds that caller back, and its
        whole-state write puts nothing back.
        """
        world = support.seeded(**{_VERDICT: {"round": 2}})
        road = dataclasses.replace(
            support.IMPLEMENTATION, route=_routes.CompletionRoute.REQUESTED_CHANGES, origin=WorkflowLabel.FIXING,
            frozen=_frozen.frozen_over(world.state, (_VERDICT,)),
        )
        completion = world.completion(handoff=road)
        world.captures(completion)
        stale = world.restarted()
        world.asks(_handoff.transfer, completion.invocation, _ANSWERING)
        read_back = stale.asks(_READ_BACK, completion.invocation)
        stale.github.write_pinned_state(stale.issue, stale.state)
        self.assertEqual((read_back.stage, stale.state.withheld), (_STAGE.HANDED_OFF, True))
        self.assertIsNone(world.record()[_VERDICT])


class RetirementTest(unittest.TestCase):
    """What a retirement may end, and what it keeps."""

    def test_a_settled_retirement_keeps_a_report(self) -> None:
        """A capture never handed off is the only copy of its report, which a settled retirement leaves alone."""
        world = support.seeded()
        world.captures(world.completion())
        settled = _quietly(world, _RETIRE, world.invocation(), _REASON.SETTLED)
        self.assertEqual(settled, (_REFUSED, _REFUSAL.NOT_HANDED_OFF, True))

    def test_an_invalidation_retires_it_once(self) -> None:
        """An invalidated capture is retired keeping which invocation it was, and why; asked again, it stands."""
        world = support.seeded()
        world.captures(world.completion())
        invocation = world.invocation()
        invalidated = world.asks(_RETIRE, invocation, _REASON.INVALIDATED)
        again = world.asks(_RETIRE, invocation, _REASON.INVALIDATED)
        self.assertEqual(
            (_answered(invalidated), again.status),
            ((_LANDED, _STAGE.RETIRED), _STANDING),
        )
        kept = _records.ResolvedCapture(invocation, _STAGE.RETIRED, reason=_REASON.INVALIDATED)
        self.assertEqual(world.record()[support.FIELD], _spelling.spelled(kept))

    def test_a_stale_retirement_writes_nothing_back(self) -> None:
        """A caller that read the capture before a later report superseded it retires it, and erases nothing.

        The retirement lands; the caller never held the later report's
        delivery, so it is held back, and its whole-state write keeps that
        delivery, the only copy of the later report.
        """
        world = support.seeded()
        completion = world.completion()
        world.captures(completion)
        stale = world.restarted()
        world.asks(_handoff.transfer, completion.invocation)
        later = support.returned(world.invocation(2), _LATER)
        _delivery.recording_stops_the_tick(world.github, world.issue, world.state, later, WorkflowLabel.IMPLEMENTING)
        retired = stale.asks(_RETIRE, completion.invocation, _REASON.SETTLED)
        stale.github.write_pinned_state(stale.issue, stale.state)
        self.assertEqual((retired.status, stale.state.withheld), (_LANDED, True))
        self.assertEqual(world.record()[_DELIVERED]["report"], _LATER_REPORT)

    def test_no_capture_of_the_run_is_absent(self) -> None:
        """Retiring a run the record holds no capture of writes nothing."""
        world = support.seeded()
        world.captures(world.completion())
        retired = _quietly(world, _RETIRE, world.invocation(2), _REASON.INVALIDATED)
        self.assertEqual(retired, (_REFUSED, _REFUSAL.ABSENT, True))


if __name__ == "__main__":
    unittest.main()
