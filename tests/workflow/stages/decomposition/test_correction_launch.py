# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one launch a decomposer manifest correction buys, owed once at the run circuit.

Driven through the tracked spawn, whose run circuit is the only charging
system: an eligible attempt's launch is charged and started there, its start
recording the count it was owed at before any process runs, and every launch
asked behind it -- in the same tick, after a restart, or over an attempt
resolved or moved since -- is refused with nothing charged. A start the
circuit refused leaves its charge reserved, which the attempt's next launch
honors rather than paying again. A dropped record of the start leaves the
started charge behind the source saying a process ran, so a restart launches
nothing. A launch is granted only where its charge, its start, and the
exhaustion recording what it answered all still fit the comment.
"""
from __future__ import annotations

import dataclasses
import unittest
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import models as _agent_models, runner as _agent_runner
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.workflow.engine import run_charge_state as _run_charge_state, usage as _usage
from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_room as _room,
    correction_standing as _standing,
)
from tests.workflow.stages.decomposition import correction_test_support as support

_STANDING = support.STANDING
_CORRECTED = support.SOURCE + 1

# A source charged where the launch's own charge keeps the count's width and a
# second one would widen it: the edge a launch at the limit is measured across.
_DIGIT_EDGE = 8

# Moves another road lands between the arming and the launch.
_MOVES = ({support.BASELINE: support.EDITED}, {support.SESSION_PIN: None})

# The launch the attempt buys, as its caller would ask it: the pinned command
# resuming the saved session.
_REQUEST = (
    ("agent_role", "decomposer"),
    ("stage", "decomposing"),
    ("backend", "codex"),
    ("prompt", "Return one complete corrected manifest."),
    ("cwd", Path("/tmp/fake-decompose-worktree")),
    ("agent_spec", support.COMMAND),
    ("resume_session_id", support.SESSION),
)


@dataclasses.dataclass
class _Runner:
    """The runner seam: what the comment carried each time a process was invoked, and what each returned."""

    world: support.CorrectionWorld
    observed: list = dataclasses.field(default_factory=list)
    returned: list = dataclasses.field(default_factory=list)

    def __call__(self, *spawn_args, **spawn_fields) -> _agent_models.AgentResult:
        self.observed.append(self.world.record())
        self.returned.append(_agent_models.AgentResult(
            session_id=support.SESSION, last_message="", exit_code=0, timed_out=False, stdout="", stderr="",
        ))
        return self.returned[-1]


def _launches(
    world: support.CorrectionWorld,
    resolves: Callable[[], bool] | None = None,
    ordinal: int = support.SOURCE,
) -> _Runner:
    """Ask the tracked spawn for the launch of the attempt armed for the run charged at `ordinal`, with no ceiling."""
    runner = _Runner(world)
    armed = support.attempt(world, ordinal)
    owed = _standing.owed_launch(support.ISSUE, armed, resolves)
    budget = _run_charge_state.AgentRunBudget(issue=world.issue, state=world.state, owed=owed)
    with patch.object(config, "MAX_AGENT_RUNS_PER_ISSUE", 0), patch.object(_agent_runner, "run_agent", runner):
        _usage._run_agent_tracked(world.github, budget, **dict(_REQUEST))
    return runner


def _armed() -> support.CorrectionWorld:
    """A world whose rejected run's attempt is armed, as a fresh process reads it."""
    world = support.seeded()
    world.arms()
    return world.restarted()


def _filled(past: int) -> support.CorrectionWorld:
    """A world whose run charged at the digit edge is rejected, its comment filled `past` beyond its launch's room."""
    world = support.seeded(**{support.USED: _DIGIT_EDGE, support.METERED: _DIGIT_EDGE})
    pending = support.attempt(world, _DIGIT_EDGE)
    low, high = 0, MAX_PINNED_BODY
    while low < high:
        middle = (low + high + 1) // 2
        if _room.launches({**world.record(), "operator_note": "x" * middle}, pending):
            low = middle
        else:
            high = middle - 1
    world.moves(operator_note="x" * (low + past))
    return world.restarted()


def _dropped(world: support.CorrectionWorld, **fields) -> support.CorrectionWorld:
    """A hand edit drops the circuit's record of the start and lays `fields` over it, as a fresh process reads it."""
    edited = world.github.read_pinned_state(world.issue)
    edited.state_data.pop(support.OWED_STARTED)
    edited.state_data.update(fields)
    world.github.write_pinned_state(world.issue, edited)
    return world.restarted()


class OwedLaunchTest(unittest.TestCase):
    """The attempt's launch is made once, by the circuit's own charge."""

    def test_an_eligible_attempt_launches_once(self) -> None:
        world = _armed()

        first = _launches(world)
        again = _launches(world)
        restarted = _launches(world.restarted())

        self.assertEqual(len(first.observed), 1)
        self.assertEqual(first.observed[0][support.OWED_STARTED], support.SOURCE, "the start is recorded first")
        self.assertEqual((again.observed, restarted.observed), ([], []))
        self.assertEqual(world.record()[support.USED], _CORRECTED, "no launch behind it is charged")
        started = _standing.CorrectionReading(_STANDING.STARTED, support.attempt(world))
        self.assertEqual(world.reads(), started)

    def test_a_moved_attempt_charges_nothing(self) -> None:
        # None is the attempt exhausted before its launch was asked for.
        for move in (*_MOVES, None):
            with self.subTest(move=move):
                world = _armed()
                if move is None:
                    world.asks(_checkpoint.exhaust, support.attempt(world))
                else:
                    world.moves(**move)
                launched = _launches(world)
                self.assertEqual(launched.observed, [])
                self.assertEqual(world.record()[support.USED], support.SOURCE)

    def test_a_refused_start_keeps_its_charge(self) -> None:
        # The caller's own question behind the charge answers no (`bool()`):
        # the charge stands unstarted, which is no start, so the attempt is
        # still eligible and its next launch honors that charge.
        world = _armed()

        refused = _launches(world, resolves=bool)
        reserved = world.record()
        honored = _launches(world.restarted())

        self.assertEqual(refused.observed, [])
        self.assertEqual(reserved[support.RESERVATION], "reserved")
        self.assertEqual(reserved[support.USED], _CORRECTED)
        self.assertNotIn(support.OWED_STARTED, reserved)
        self.assertEqual(len(honored.observed), 1)
        self.assertEqual(world.record()[support.USED], _CORRECTED)

    def test_a_dropped_start_record_launches_nothing(self) -> None:
        # A hand edit drops the circuit's record of the start: the started
        # charge behind the source still says a process ran, so a restart
        # neither launches nor charges again.
        world = _armed()
        first = _launches(world)
        restarted = _dropped(world)

        again = _launches(restarted)

        self.assertEqual(len(first.observed), 1)
        self.assertEqual(again.observed, [])
        self.assertEqual(world.record()[support.USED], _CORRECTED)
        self.assertEqual(restarted.reads().standing, _STANDING.STARTED)

    def test_a_surviving_meter_launches_nothing(self) -> None:
        # The start record dropped, the receipts trimmed, and the charge set
        # back to `reserved`: the usage meter still counts the process that
        # returned under it, so a restart launches no second one.
        world = _armed()
        first = _launches(world)
        trimmed = {"floor": support.SOURCE, "recent": []}
        restarted = _dropped(world, **{support.RECEIPTS: trimmed, support.RESERVATION: "reserved"})

        again = _launches(restarted)

        self.assertEqual(len(first.observed), 1)
        self.assertEqual(world.record()[support.METERED], _CORRECTED)
        self.assertEqual(again.observed, [])
        self.assertEqual(restarted.reads().standing, _STANDING.STARTED)


class LaunchRoomTest(unittest.TestCase):
    """A launch is granted only where its charge, its start, and its exhaustion all fit the comment."""

    def test_a_roomy_launch_records_its_exhaustion(self) -> None:
        world = _filled(0)
        armed = world.arms(support.source(world, _DIGIT_EDGE))

        launched = _launches(world, ordinal=_DIGIT_EDGE)
        correction = launched.returned[0].invocation
        exhausted = world.asks(_checkpoint.exhaust, support.attempt(world, _DIGIT_EDGE), correction)

        self.assertTrue(armed.reading.grants)
        self.assertEqual(len(launched.observed), 1)
        self.assertEqual(exhausted.status, support.STATUS.LANDED)
        self.assertEqual(world.reads().standing, _STANDING.EXHAUSTED)

    def test_a_launch_without_room_charges_nothing(self) -> None:
        # Room enough to arm and to resolve, not to charge and start beside
        # that: the attempt stands armed and grants nothing.
        world = _filled(1)
        armed = world.arms(support.source(world, _DIGIT_EDGE))

        launched = _launches(world, ordinal=_DIGIT_EDGE)

        self.assertEqual(armed.status, support.STATUS.LANDED)
        self.assertEqual(armed.reading.standing, _STANDING.CROWDED)
        self.assertEqual(launched.observed, [])
        self.assertEqual(world.record()[support.USED], _DIGIT_EDGE)

    def test_a_charge_held_at_the_limit_still_starts(self) -> None:
        # The launch's own charge, reserved at the limit and refused its start,
        # is measured as that charge's start alone, not as a second, wider
        # charge: across a restart the attempt stays eligible and that very
        # charge starts its one process.
        world = _filled(0)
        world.arms(support.source(world, _DIGIT_EDGE))
        refused = _launches(world, resolves=bool, ordinal=_DIGIT_EDGE)
        restarted = world.restarted()
        standing = restarted.reads().standing

        honored = _launches(restarted, ordinal=_DIGIT_EDGE)

        self.assertEqual(refused.observed, [])
        self.assertEqual(standing, _STANDING.ELIGIBLE)
        self.assertEqual(len(honored.observed), 1)
        self.assertEqual(world.record()[support.USED], _DIGIT_EDGE + 1, "the held charge is started, not paid again")


if __name__ == "__main__":
    unittest.main()
