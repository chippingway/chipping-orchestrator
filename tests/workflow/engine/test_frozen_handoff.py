# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The frozen handoff a pending captured completion is decided on.

A handoff frozen over a pinned record is handed on only while that record
still reads as the launch read it. A move the record's own reader takes --
another change request, a verdict taken off, a debt carried onto another
head -- is another road's, and retires the capture; a spelling that reader
refuses is damage, and holds it with nothing written. So does a move of a
record no reader is registered for, since nothing can tell it from damage.
A late revision's frozen late record is read by the late domain's own check
for that very field, and a late record none of its checks judges is one no
reader is registered for.
"""
from __future__ import annotations

import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_recovery_models as _models,
    completion_routes as _routes,
    review_subjects as _review_subjects,
)
from orchestrator.workflow.stages.validating import review_verdicts as _review_verdicts
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.engine import completion_dispatch_support as _dispatch, completion_recovery_support as _support
from tests.workflow.engine.completion_turn_support import Turn

_HELD = (_models.Reason.PREREQUISITE_UNREAD, _models.Standing.UNCERTAIN)

# The returned change request a fix's handoff is frozen over, as the launch
# read it; as another road moves it -- another change request, or the verdict
# taken off; and as a hand edit leaves it, nothing its reader takes.
_VERDICT = _review_verdicts.RETURNED_VERDICT
_LAUNCHED_VERDICT = _review_verdicts.ReturnedVerdict(
    0,
    _review_verdicts.CHANGES_REQUESTED,
    _review_subjects.ReviewSubject(_support.PR_NUMBER, _support.BEFORE, _support.PROMPT).recorded(),
    "Fix the empty input.",
    handed=_support.RUNS_USED,
)
_ANOTHER_VERDICT = MappingProxyType({
    _VERDICT: {**_LAUNCHED_VERDICT.recorded(), "feedback": "Cover the empty input too."},
})
_VERDICT_MOVES = (
    Turn(edits=_ANOTHER_VERDICT),
    Turn(edits=MappingProxyType({_VERDICT: _support.DROPPED})),
)

# A record no reader is registered for, as the launch read it and as another road moves it.
_UNREGISTERED = "dev_resume_count"

_COUNT_AT_LAUNCH = 3

# Each move that leaves a frozen record as nothing a reader here can take --
# the change request hand-damaged, and the unregistered record moved on --
# beside the record frozen and its spelling at the launch, the change
# request's own where None.
_UNDECIDED = (
    ((_VERDICT, None), Turn(edits=MappingProxyType({_VERDICT: {"unreadable": True}}))),
    ((_UNREGISTERED, _COUNT_AT_LAUNCH), Turn(edits=MappingProxyType({_UNREGISTERED: _COUNT_AT_LAUNCH + 1}))),
)

# The pinned readings a dispatch takes up to its retirement's own: the
# dispatcher's, the capture's read-back, and the retirement's.
_RETIREMENT_READING = 3

# A rewritten head's report debt, owed on the pinned pull request and branch,
# that a road's handoff froze; its hand-damaged spelling, and another
# readable debt another road carried it onto.
_DEBT = "developer_report_rewrite_debt"
_OWED = MappingProxyType({
    "pr": _support.PR_NUMBER, "branch": _support.BRANCH,
    "previous_head": _support.ELSEWHERE, "rewritten_head": _support.BEFORE,
})
_DAMAGED_DEBT = Turn(edits=MappingProxyType({_DEBT: "unreadable debt"}))
_CARRIED_DEBT = Turn(edits=MappingProxyType({_DEBT: {**_OWED, "rewritten_head": _support.SOURCE}}))

# The roads that froze the debt: the refresh that answers it, and a drift resume that only stood on it.
_DEBT_ROADS = (_routes.CompletionRoute.REPORT_REFRESH, _routes.CompletionRoute.REQUIREMENTS_DRIFT)

# A late revision's frozen late records: a hold's route bookkeeping, which the
# late domain's spend check judges, the measurement's ceiling, which its
# reading check judges, and a late record none of its checks judges. Each
# case is the record and its spelling at the launch, and the move made of it:
# a spelling the check refuses, or a move of the unjudged record, holds the
# revision; a move the check reads retires it.
_SPENDS = "late_spends"
_SPENT_ROUND = "review_round"
_SPENT_ONCE = (_SPENDS, [[_SPENT_ROUND, 1]])
_SPEND_DAMAGED = Turn(edits=MappingProxyType({_SPENDS: [[_SPENT_ROUND, "unreadable"]]}))
_SPENT_AGAIN = Turn(edits=MappingProxyType({_SPENDS: [[_SPENT_ROUND, 2]]}))

_CEILING = "late_threshold"
_CEILING_AT_LAUNCH = (_CEILING, 100)
_CEILING_MOVED = Turn(edits=MappingProxyType({_CEILING: 200}))

_COMMENT_HASH = "late_comment_hash"
_HASHED = (_COMMENT_HASH, "cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcd")
_HASH_MOVED = Turn(edits=MappingProxyType({
    _COMMENT_HASH: "efefefefefefefefefefefefefefefefefefefefefefefefefefefefefefefef",
}))

_LATE_HOLDS = ((_SPENT_ONCE, _SPEND_DAMAGED), (_HASHED, _HASH_MOVED))
_LATE_MOVES = ((_SPENT_ONCE, _SPENT_AGAIN), (_CEILING_AT_LAUNCH, _CEILING_MOVED))


def _debt_world(route: _routes.CompletionRoute) -> tuple[_support.CapturedWorld, _records.CompletionCapture]:
    """A world on `validating` owing a rewritten head's report, whose capture on `route` froze that debt."""
    world = _support.CapturedWorld(WorkflowLabel.VALIDATING, pull_request=True)
    world.hand_edit(**{_DEBT: dict(_OWED)})
    frozen = _frozen.frozen_over(world.github.read_pinned_state(world.issue), (_DEBT,))
    return world, world.captured(_support.road(route, WorkflowLabel.VALIDATING, frozen))


def _frozen_world(
    record: str = _VERDICT, at_launch: object = None,
) -> tuple[_support.CapturedWorld, _records.CompletionCapture]:
    """A world on `fixing` whose change request's capture froze `record`, spelled `at_launch` when it launched.

    The returned change request as the launch read it, where `at_launch` is None.
    """
    world = _support.CapturedWorld(WorkflowLabel.FIXING, pull_request=True)
    spelled = _LAUNCHED_VERDICT.recorded() if at_launch is None else at_launch
    world.hand_edit(**{record: spelled})
    frozen = _frozen.frozen_over(world.github.read_pinned_state(world.issue), (record,))
    road = _support.road(_routes.CompletionRoute.REQUESTED_CHANGES, WorkflowLabel.FIXING, frozen)
    return world, world.captured(road)


def _revision_world(launched: tuple) -> _support.CapturedWorld:
    """A world under a live late adjudication whose developer revision's capture froze one late record.

    `launched` is that record and its spelling when the revision launched.
    """
    record, at_launch = launched
    world = _support.CapturedWorld(WorkflowLabel.DECOMPOSING)
    world.hand_edit(**{**_support.ADJUDICATING, record: at_launch})
    frozen = _frozen.frozen_over(world.github.read_pinned_state(world.issue), (record,))
    world.captured(_support.road(_routes.CompletionRoute.LATE_REVISION, WorkflowLabel.DECOMPOSING, frozen))
    return world


class FrozenHandoffTest(unittest.TestCase):
    """A handoff frozen over a record another road has since moved is no longer the one the run answered."""

    def test_a_moved_frozen_record_retires_it(self) -> None:
        # The returned change request, moved to a spelling its own reader
        # takes, or taken off: another road's move, so the fix is stale.
        for turn in _VERDICT_MOVES:
            with self.subTest(turn=turn):
                world, captured = _frozen_world()

                seen = _dispatch.observed(world, _dispatch.RoadOwner(), turn)

                retired = _support.read_capture(seen.after)
                self.assertTrue(seen.says(_models.Reason.HANDOFF_MOVED), seen.said)
                self.assertEqual(retired.stage, _records.CaptureStage.RETIRED)
                self.assertEqual(retired.invocation, captured.invocation)
                self.assertEqual((seen.ran, seen.handed), ((), ()), "the tick ends behind the retirement")
                # The move is the other road's, and stands.
                self.assertEqual(seen.after.get(_VERDICT), seen.before.get(_VERDICT))

    def test_a_repair_behind_the_proof_keeps_it(self) -> None:
        # The record that proved the capture stale is put back by hand after
        # the dispatch read it and before the retirement's own reading: the
        # retirement is decided on the reading the proof was taken over, so it
        # is refused, nothing is written or run, and the next dispatch -- on
        # the repaired record -- hands the capture on.
        world, captured = _frozen_world()
        world.hand_edit(**_ANOTHER_VERDICT)
        repaired = _support.RepairedBehind(world, _RETIREMENT_READING, **{_VERDICT: _LAUNCHED_VERDICT.recorded()})

        with patch.object(world.github, "read_pinned_state", side_effect=repaired):
            held = _dispatch.observed(world, _dispatch.RoadOwner())

        self.assertEqual(_support.read_capture(held.after), captured)
        self.assertEqual(held.writes, 0, "nothing is written over the capture")
        self.assertEqual((held.ran, held.handed), ((), ()))
        self.assertIn("EVIDENCE_MOVED", held.said)
        handed = _dispatch.observed(world, _dispatch.RoadOwner()).handed
        self.assertEqual([admitted.capture for admitted in handed], [captured])

    def test_an_unreadable_frozen_debt_holds_it(self) -> None:
        # The frozen debt, hand-damaged after the launch, is spelled otherwise
        # but as nothing its reader takes: damage, not another road's move,
        # so the capture is held with nothing written -- on the refresh that
        # answers the debt and on a road that only froze it.
        for route in _DEBT_ROADS:
            with self.subTest(route=route):
                world, captured = _debt_world(route)

                seen = _dispatch.observed(world, _dispatch.RoadOwner(), _DAMAGED_DEBT)

                self._held(seen, captured)

    def test_an_undecidable_move_holds_it(self) -> None:
        # The change request hand-damaged into a spelling its own reader
        # refuses, and a record no reader is registered for moved on: neither
        # can be told from damage, so the fix is kept, with nothing written,
        # handed on, or run.
        for launched, turn in _UNDECIDED:
            with self.subTest(turn=turn):
                world, captured = _frozen_world(*launched)

                seen = _dispatch.observed(world, _dispatch.RoadOwner(), turn)

                self._held(seen, captured)

    def test_a_readable_move_of_it_retires_it(self) -> None:
        # The same debt carried onto another head another road wrote, read
        # whole: the handoff the drift resume answered is gone.
        world, captured = _debt_world(_routes.CompletionRoute.REQUIREMENTS_DRIFT)

        seen = _dispatch.observed(world, _dispatch.RoadOwner(), _CARRIED_DEBT)

        retired = _support.read_capture(seen.after)
        self.assertTrue(seen.says(_models.Reason.HANDOFF_MOVED), seen.said)
        self.assertEqual(retired.stage, _records.CaptureStage.RETIRED)
        self.assertEqual(retired.invocation, captured.invocation)

    def test_an_unmoved_frozen_record_hands_it_on(self) -> None:
        world, captured = _frozen_world()

        seen = _dispatch.observed(world, _dispatch.RoadOwner())

        self.assertEqual([admitted.capture for admitted in seen.handed], [captured])

    def _held(self, seen: _dispatch.Observed, captured: _records.CompletionCapture) -> None:
        """`captured` was held over a record nobody can read, with nothing written, handed on, or run."""
        self.assertTrue(seen.says(*_HELD), seen.said)
        self.assertEqual(_support.read_capture(seen.after), captured)
        self.assertEqual((seen.ran, seen.handed), ((), ()))
        self.assertTrue(seen.untouched)



class FrozenLateRecordTest(unittest.TestCase):
    """A late revision's frozen late record is read by the late domain's check for that very field."""

    def test_an_unreadable_or_unjudged_move_holds_it(self) -> None:
        # A hold's route bookkeeping hand-damaged into no group, and a late
        # record no check judges moved on, cannot be told from damage: the
        # revision is kept, with nothing written, handed on, or run.
        for launched, turn in _LATE_HOLDS:
            with self.subTest(turn=turn):
                world = _revision_world(launched)

                seen = _dispatch.observed(world, _dispatch.RoadOwner(), turn)

                self.assertTrue(seen.says(*_HELD), seen.said)
                self.assertEqual((seen.ran, seen.handed), ((), ()))
                self.assertTrue(seen.untouched)

    def test_a_readable_move_retires_it(self) -> None:
        # Another spend of the same round, and a ceiling the reading still
        # takes: another road's move, so the revision is stale.
        for launched, turn in _LATE_MOVES:
            with self.subTest(turn=turn):
                world = _revision_world(launched)

                seen = _dispatch.observed(world, _dispatch.RoadOwner(), turn)

                self.assertTrue(seen.says(_models.Reason.HANDOFF_MOVED), seen.said)
                self.assertEqual(_support.read_capture(seen.after).stage, _records.CaptureStage.RETIRED)


if __name__ == "__main__":
    unittest.main()
