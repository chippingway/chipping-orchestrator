# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The manifest correction's pinned record: what each stage spells, what reads as none, and what a reading grants.

Read strictly and whole, so a hand edit or a member out of its bound is a
damaged claim rather than an absence. Only a pending attempt bound to its own
record, its context standing, its launch's start ruled out, and its widest
resolution fitting the comment grants the one launch; a start the run ledger
shows or cannot rule out, a context a reading proves moved, one nobody can
read, and a resolved, displaced, or damaged record each grant nothing.
"""
from __future__ import annotations

import copy
import dataclasses
import unittest

from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState, pinned_state_body
from orchestrator.workflow.stages.decomposition import (
    correction_records as _records,
    correction_standing as _standing,
)
from tests.workflow.stages.decomposition import correction_test_support as support

_STANDING = support.STANDING
_STAGE = support.STAGE
_SOURCE = "source"
_FLOOR = "floor"
_CORRECTION = "correction"
_ORDINAL = "ordinal"
_LATER = support.SOURCE + 1
_EARLIER = support.SOURCE - 1
_OTHER_SESSION = "decomposer-session-2"
_SHORT_DIGEST = 40
_READING = _standing.CorrectionReading

# A session pin its own reader refuses: two lines, no session at all.
_MALFORMED_SESSION = "decomposer\nsession"

# A usage receipt of a process charged after the source: one returned since.
_LATER_RECEIPT = (("floor", support.SOURCE), ("recent", [[_LATER, "00000000000000ff"]]))

# A member removed rather than spelled.
_DROPPED = object()

_EXHAUSTED_AT = 1
_RETIRED_AT = 3

# Hand edits of one stage's spelling, as (the stage's place in `_spellings`,
# the member's path, what it is spelled as): each is no attempt this build writes.
_DAMAGED_EDITS = (
    (0, ("stage",), "started"),
    (0, ("session",), _DROPPED),
    (0, (_FLOOR,), support.SOURCE),
    (0, (_SOURCE, "nonce"), _DROPPED),
    (0, (_SOURCE, "nonce"), "not-a-nonce"),
    (0, (_SOURCE, _ORDINAL), 0),
    (0, (_SOURCE, _ORDINAL), True),
    (0, (_SOURCE, _ORDINAL), float(support.SOURCE)),
    (0, (_SOURCE, "repo"), "not a slug"),
    (0, ("requirements",), support.REQUIREMENTS[:_SHORT_DIGEST]),
    (0, ("command",), "codex\n--model gpt-5.5"),
    (0, ("session",), ""),
    (0, ("diagnostic",), _DROPPED),
    (0, ("diagnostic",), "child 1\nmissing depends_on"),
    (0, ("diagnostic",), "x" * (_records.MAX_DIAGNOSTIC + 1)),
    (_EXHAUSTED_AT, (_CORRECTION, _ORDINAL), support.SOURCE),
    (_EXHAUSTED_AT, (_CORRECTION, "comment"), 1),
    (_EXHAUSTED_AT, (_CORRECTION, "cycle"), 1),
    (_EXHAUSTED_AT, (_FLOOR,), support.SOURCE),
    (_EXHAUSTED_AT, (_CORRECTION,), _DROPPED),
    (_RETIRED_AT, (_FLOOR,), True),
    (_RETIRED_AT, (_FLOOR,), _EARLIER),
    (_RETIRED_AT, (_CORRECTION,), None),
)

# Readings of a pending attempt, as (what the comment carries beside it, what
# it says of the attempt).
_PENDING_READINGS = (
    ({}, _STANDING.ELIGIBLE),
    ({support.USED: _LATER, support.RESERVATION: "reserved"}, _STANDING.ELIGIBLE),
    ({support.USED: _LATER, support.METERED: _LATER, support.RESERVATION: "reserved"}, _STANDING.STARTED),
    ({support.OWED_STARTED: _EARLIER}, _STANDING.ELIGIBLE),
    ({support.OWED_STARTED: support.SOURCE}, _STANDING.STARTED),
    ({support.OWED_STARTED: _LATER}, _STANDING.STARTED),
    ({support.OWED_STARTED: None}, _STANDING.STARTED),
    ({support.USED: _EARLIER, support.METERED: _EARLIER}, _STANDING.STARTED),
    ({support.USED: _LATER}, _STANDING.STARTED),
    ({support.USED: _LATER, support.RESERVATION: "launched"}, _STANDING.STARTED),
    ({support.USED: _LATER + 1, support.RESERVATION: "reserved"}, _STANDING.STARTED),
    ({support.RECEIPTS: dict(_LATER_RECEIPT)}, _STANDING.STARTED),
    ({support.RECEIPTS: None}, _STANDING.STARTED),
    ({support.BASELINE: support.EDITED}, _STANDING.STALE),
    ({support.BASELINE: support.EDITED, support.OWED_STARTED: support.SOURCE}, _STANDING.STALE),
    ({support.SESSION_PIN: None}, _STANDING.STALE),
    ({support.SESSION_PIN: _OTHER_SESSION}, _STANDING.STALE),
    ({support.COMMAND_PIN: "claude"}, _STANDING.STALE),
    ({support.BASELINE: "not a digest"}, _STANDING.UNPROVED),
    ({support.BASELINE: None}, _STANDING.UNPROVED),
    ({support.SESSION_PIN: 7}, _STANDING.UNPROVED),
    ({support.SESSION_PIN: _MALFORMED_SESSION}, _STANDING.UNPROVED),
    ({support.COMMAND_PIN: ""}, _STANDING.UNPROVED),
    ({support.USED: "unreadable"}, _STANDING.STARTED),
    ({support.USED: None}, _STANDING.STARTED),
    ({support.METERED: "four"}, _STANDING.STARTED),
    ({support.SESSION_PIN: 7, support.COMMAND_PIN: "claude"}, _STANDING.STALE),
    ({"late_cycle_id": 3}, _STANDING.DISPLACED),
)

# How far below the ceiling a filled comment stands: inside the room a pending
# spelling needs, short of what its widest resolution would.
_FILLED_MARGIN = 8


def _pending(world: support.CorrectionWorld, **fields) -> _records.CorrectionAttempt:
    """Pin the seeded source's pending attempt on `world`'s comment beside `fields`, and hand it back."""
    pending = support.attempt(world)
    world.moves(**{support.FIELD: pending.spelled(), **fields})
    return pending


def _spellings(world: support.CorrectionWorld) -> tuple[_records.CorrectionAttempt, ...]:
    """The seeded source's attempt at every stage a writer leaves it at."""
    pending = support.attempt(world)
    return (
        pending,
        pending.resolved(_STAGE.EXHAUSTED, _LATER, support.invocation(world, _LATER)),
        pending.resolved(_STAGE.EXHAUSTED, support.SOURCE),
        pending.resolved(_STAGE.RETIRED, _LATER),
    )


def _edited(spellings: list[dict], edit: tuple) -> dict:
    """The spelling `edit` names among `spellings`, its member at the path spelled as given, or dropped."""
    at, path, spelled = edit
    edited = copy.deepcopy(spellings[at])
    owner = edited[path[0]] if len(path) > 1 else edited
    if spelled is _DROPPED:
        owner.pop(path[-1])
    else:
        owner[path[-1]] = spelled
    return edited


def _damaged_claims(world: support.CorrectionWorld) -> list:
    """Every claim the field may hold that is no attempt this build writes."""
    spellings = [pending.spelled() for pending in _spellings(world)]
    edits = [_edited(spellings, edit) for edit in _DAMAGED_EDITS]
    return [None, [], *edits]


def _unbound(world: support.CorrectionWorld) -> tuple:
    """Records that grant nothing whatever stands beside them, as (the attempt, what a reading says of it)."""
    spellings = _spellings(world)
    charged_elsewhere = support.invocation(world, comment=1)
    elsewhere = dataclasses.replace(support.source(world), invocation=charged_elsewhere)
    return (
        (spellings[_EXHAUSTED_AT], _STANDING.EXHAUSTED),
        (spellings[_RETIRED_AT], _STANDING.RETIRED),
        (_records.CorrectionAttempt(elsewhere), _STANDING.DISPLACED),
    )


class SpellingTest(unittest.TestCase):
    """What each stage is written as, and what reads back as no attempt at all."""

    def test_each_stage_reads_back_as_itself(self) -> None:
        for spelled in _spellings(support.seeded()):
            with self.subTest(stage=spelled.stage, correction=spelled.correction):
                state = PinnedState(state_data={support.FIELD: spelled.spelled()})
                self.assertEqual(_records.read(state), spelled)
                self.assertTrue(spelled.recordable())

    def test_damaged_spellings_read_as_none(self) -> None:
        for claim in _damaged_claims(support.seeded()):
            with self.subTest(claim=claim):
                state = PinnedState(state_data={support.FIELD: claim})
                self.assertTrue(_records.carries(state))
                self.assertIsNone(_records.read(state))


class StandingTest(unittest.TestCase):
    """What one reading grants the attempt it carries."""

    def test_what_a_reading_says_of_a_pending_attempt(self) -> None:
        for fields, standing in _PENDING_READINGS:
            with self.subTest(fields=fields):
                world = support.seeded()
                pending = _pending(world, **fields)
                self.assertEqual(world.reads(), _READING(standing, pending))
                self.assertEqual(world.reads().grants, standing is _STANDING.ELIGIBLE)

    def test_resolved_or_displaced_grants_nothing(self) -> None:
        world = support.seeded()
        for unbound, standing in _unbound(world):
            with self.subTest(standing=standing):
                world.moves(**{support.FIELD: unbound.spelled()})
                self.assertEqual(world.reads(), _READING(standing, unbound))

    def test_absence_and_damage_are_told_apart(self) -> None:
        # Damage carries no attempt to act on, whether the claim or the cycle
        # it is bound to is what nobody can read.
        self.assertEqual(support.seeded().reads(), _READING(_STANDING.ABSENT))
        for damage in ({support.FIELD: None}, {"late_cycle_id": "seven"}):
            with self.subTest(damage=damage):
                world = support.seeded()
                _pending(world, **damage)
                self.assertEqual(world.reads(), _READING(_STANDING.DAMAGED))

    def test_a_full_comment_reads_crowded(self) -> None:
        # Room for the pending spelling is not enough: its launch could answer
        # with nothing able to record that it ran.
        world = support.seeded()
        pending = _pending(world, operator_note="")
        room = MAX_PINNED_BODY - len(pinned_state_body(world.record()))
        world.moves(operator_note="x" * (room - _FILLED_MARGIN))

        self.assertLessEqual(len(pinned_state_body(world.record())), MAX_PINNED_BODY)
        self.assertEqual(world.reads(), _READING(_STANDING.CROWDED, pending))


if __name__ == "__main__":
    unittest.main()
