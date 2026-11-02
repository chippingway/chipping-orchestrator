# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Arming a decomposer manifest correction: one allowance per rejected run, landed through its own guarded commit.

What an arming lands -- its own field, every counter, pin, park, and unknown
field kept as the comment carries them -- and what it refuses with nothing
written: another source's pending attempt, a resolved one covering this
source's charge, a source something was charged or started behind, a source
whose requirements or saved conversation the record does not carry, a damaged
or displaced claim, a comment admission refuses or that is not the caller's, a
comment with no room for the attempt's widest resolution, and a record another
road moved between the reading the arming was decided on and its commit.
"""
from __future__ import annotations

import dataclasses
import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY, AdmissionStatus, PinnedState, pinned_state_body
from orchestrator.workflow.engine.pinned_commit_models import CommitRefusal
from orchestrator.workflow.stages.decomposition import (
    correction_records as _records,
    correction_standing as _standing,
)
from tests.workflow.stages.decomposition import correction_test_support as support

_STATUS = support.STATUS
_REFUSAL = support.REFUSAL
_STAGE = support.STAGE
_READING = _standing.CorrectionReading
_EARLIER = support.SOURCE - 1
_LATER = support.SOURCE + 1
_CYCLE = "late_cycle_id"

# How far below the ceiling a filled comment stands: inside the room the
# pending spelling needs, short of what its widest resolution would.
_FILLED_MARGIN = 8


@dataclasses.dataclass(frozen=True)
class _RefusedArm:
    """One arming refused before its commit: what the comment carries, how the source differs, and why."""

    refusal: _REFUSAL
    fields: tuple = ()
    recorded: tuple | None = None
    invocation: tuple = ()
    context: tuple = ()

    def seeds(self, world: support.CorrectionWorld) -> None:
        """Pin what this case's comment carries on `world`, the caller reading it as it then stands."""
        moved = dict(self.fields)
        if self.recorded is not None:
            moved[support.FIELD] = _recorded(world, *self.recorded).spelled()
        if moved:
            world.moves(**moved)
            world.state = world.restarted().state

    def source(self, world: support.CorrectionWorld) -> _records.CorrectionSource:
        """The source this case asks to arm."""
        charged = support.invocation(world, **dict(self.invocation))
        named = support.source(world, **dict(self.context))
        return dataclasses.replace(named, invocation=charged)


def _recorded(world: support.CorrectionWorld, stage: _STAGE, ordinal: int, comment: int | None):
    """The attempt of a source charged at `ordinal` -- on `comment` where named -- at `stage`."""
    invocation = support.invocation(world, ordinal, comment=comment or world.state.comment_id)
    pending = _records.CorrectionAttempt(dataclasses.replace(support.source(world), invocation=invocation))
    return pending if stage is _STAGE.PENDING else pending.resolved(stage, ordinal)


_REFUSED_ARMS = (
    _RefusedArm(_REFUSAL.UNRESOLVED, recorded=(_STAGE.PENDING, _EARLIER, None)),
    _RefusedArm(_REFUSAL.SUPERSEDED, recorded=(_STAGE.EXHAUSTED, support.SOURCE, None)),
    _RefusedArm(_REFUSAL.SUPERSEDED, recorded=(_STAGE.RETIRED, support.SOURCE, None)),
    _RefusedArm(_REFUSAL.DISPLACED, recorded=(_STAGE.RETIRED, _EARLIER, 1)),
    _RefusedArm(_REFUSAL.SUPERSEDED, fields=((support.USED, _LATER),)),
    _RefusedArm(_REFUSAL.SUPERSEDED, fields=((support.OWED_STARTED, support.SOURCE),)),
    _RefusedArm(_REFUSAL.SUPERSEDED, fields=((support.OWED_STARTED, None),)),
    _RefusedArm(_REFUSAL.SUPERSEDED, fields=((support.USED, "unreadable"),)),
    _RefusedArm(_REFUSAL.UNSAVED, fields=((support.BASELINE, support.EDITED),)),
    _RefusedArm(_REFUSAL.UNSAVED, fields=((support.BASELINE, None),)),
    _RefusedArm(_REFUSAL.UNSAVED, fields=((support.SESSION_PIN, None),)),
    _RefusedArm(_REFUSAL.UNSAVED, fields=((support.COMMAND_PIN, "claude"),)),
    _RefusedArm(_REFUSAL.UNSAVED, context=(("session", "decomposer-session-2"),)),
    _RefusedArm(_REFUSAL.UNRECORDABLE, invocation=(("nonce", "not-a-nonce"),)),
    _RefusedArm(_REFUSAL.DAMAGED, fields=((support.FIELD, None),)),
    _RefusedArm(_REFUSAL.DAMAGED, fields=((_CYCLE, "seven"),)),
    _RefusedArm(_REFUSAL.FOREIGN, invocation=(("issue", support.ISSUE + 1),)),
    _RefusedArm(_REFUSAL.FOREIGN, invocation=(("repo", "someone/else"),)),
    _RefusedArm(_REFUSAL.FOREIGN, invocation=(("comment", 1),)),
    _RefusedArm(_REFUSAL.OTHER_CYCLE, invocation=(("cycle", 3),)),
)

# A human's note landed behind the reading an arming was decided on.
_HAND_NOTE = "edited by hand while the arming was out"

# Moves another road lands right behind the reading an arming was decided on.
_MOVES = (
    {support.BASELINE: support.EDITED},
    {support.SESSION_PIN: "decomposer-session-2"},
    {support.COMMAND_PIN: "claude"},
    {support.USED: _LATER},
    {support.OWED_STARTED: support.SOURCE},
    {_CYCLE: 2},
)


def _unpinned(world: support.CorrectionWorld, status: AdmissionStatus | None) -> None:
    """A hand edit leaves the comment unparseable or under version 2, or deletes it where `status` is None.

    `SUPPORTED` re-pins the record whole under a new comment instead: a
    supported record pinned in place of the one the caller read.
    """
    if status is AdmissionStatus.SUPPORTED:
        world.github.seed_state(world.issue, **world.record())
        return
    if status is None:
        world.github._pinned.pop(support.ISSUE)
        return
    world.github._pinned[support.ISSUE] = PinnedState(
        comment_id=world.state.comment_id,
        state_data={**world.record(), "schema_version": 2},
        parsed=status is not AdmissionStatus.MALFORMED,
        supported=False,
        admission_status=status,
    )


class ArmLandsTest(unittest.TestCase):
    """An arming lands its own field and nothing else, once however often it is asked."""

    def test_arming_lands_the_field_alone(self) -> None:
        world = support.seeded()
        before = world.record()
        world.state.set("awaiting_human", True)

        outcome = world.arms()

        armed = support.attempt(world)
        self.assertEqual(outcome.status, _STATUS.LANDED)
        self.assertEqual(outcome.reading, _READING(support.STANDING.ELIGIBLE, armed))
        self.assertEqual(world.record(), {**before, support.FIELD: armed.spelled()})
        self.assertEqual(world.state.get(support.FIELD), armed.spelled())
        self.assertTrue(world.state.get("awaiting_human"), "the caller's own staging is its own to write")
        self.assertFalse(world.state.withheld)

    def test_asking_again_sends_nothing(self) -> None:
        world = support.seeded()
        world.arms()
        before = world.snapshot()

        repeated = world.arms()

        self.assertEqual(repeated.status, _STATUS.STANDING)
        self.assertTrue(repeated.reading.grants)
        self.assertEqual(world.snapshot(), before)


class ArmRefusedTest(unittest.TestCase):
    """What an arming refuses, writing nothing."""

    def test_refused_arms_write_nothing(self) -> None:
        for case in _REFUSED_ARMS:
            with self.subTest(case=case):
                world = support.seeded()
                case.seeds(world)
                before = world.snapshot()
                outcome = world.arms(case.source(world))
                self.assertEqual((outcome.status, outcome.refusal), (_STATUS.REFUSED, case.refusal))
                self.assertEqual(world.snapshot(), before)

    def test_refused_admission_grants_nothing(self) -> None:
        edits = (
            (AdmissionStatus.MALFORMED, CommitRefusal.MALFORMED),
            (AdmissionStatus.UNSUPPORTED, CommitRefusal.UNSUPPORTED),
            (None, CommitRefusal.REPLACED),
            (AdmissionStatus.SUPPORTED, CommitRefusal.REPLACED),
        )
        for status, refusal in edits:
            with self.subTest(status=status):
                world = support.seeded()
                _unpinned(world, status)
                outcome = world.arms()
                self.assertEqual((outcome.status, outcome.refusal), (_STATUS.REFUSED, refusal))
                self.assertTrue(world.state.withheld)
                self.assertNotIn(support.FIELD, world.record())

    def test_a_full_comment_refuses_for_room(self) -> None:
        # Room for the pending spelling alone would grant a launch whose
        # answer nothing could record.
        world = support.seeded()
        armed = support.attempt(world).spelled()
        spelled = {**world.record(), support.FIELD: armed, "operator_note": ""}
        room = MAX_PINNED_BODY - len(pinned_state_body(spelled))
        world.moves(operator_note="x" * (room - _FILLED_MARGIN))
        world.state = world.restarted().state

        outcome = world.arms()

        self.assertEqual((outcome.status, outcome.refusal), (_STATUS.REFUSED, _REFUSAL.NO_ROOM))
        self.assertNotIn(support.FIELD, world.record())
        self.assertFalse(world.state.withheld, "a comment simply too full leaves the caller writable")


class ArmPrerequisiteTest(unittest.TestCase):
    """An arming is decided on the record, the cycle, the requirements, the pins, and the ledger it read."""

    def test_a_move_behind_the_reading_refuses_it(self) -> None:
        for moved in _MOVES:
            with self.subTest(moved=moved):
                world = support.seeded()
                with support.interfering(world, **moved):
                    outcome = world.arms()
                self.assertEqual(outcome.refusal, CommitRefusal.PREREQUISITE_CHANGED)
                self.assertEqual({**world.record(), **moved}, world.record(), "the other road's move is kept")
                self.assertNotIn(support.FIELD, world.record())
                self.assertTrue(world.state.withheld)

    def test_another_roads_arming_behind_it_is_kept(self) -> None:
        world = support.seeded()
        earlier = _recorded(world, _STAGE.PENDING, _EARLIER, None).spelled()
        with support.interfering(world, **{support.FIELD: earlier}):
            outcome = world.arms()

        self.assertEqual(outcome.refusal, CommitRefusal.PREREQUISITE_CHANGED)
        self.assertEqual(world.record()[support.FIELD], earlier)

    def test_an_unrelated_move_behind_it_withholds(self) -> None:
        # A field the arming is not decided on lands, kept by the commit; the
        # caller read the comment before it and does not hold it, so its own
        # whole-state write is withheld rather than writing it away.
        world = support.seeded()
        with support.interfering(world, operator_note=_HAND_NOTE):
            outcome = world.arms()
        world.github.write_pinned_state(world.issue, world.state)

        self.assertEqual(outcome.status, _STATUS.LANDED)
        self.assertTrue(world.state.withheld)
        armed = support.attempt(world).spelled()
        self.assertEqual(world.record()["operator_note"], _HAND_NOTE)
        self.assertEqual(world.record()[support.FIELD], armed)


if __name__ == "__main__":
    unittest.main()
