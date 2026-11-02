# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A decomposer manifest correction across writes nobody confirmed and processes that restarted.

A write sent and never confirmed withholds the caller's state and is settled
by its read-back alone: one that landed is found standing, and asking again
sends nothing; one that did not land is found absent, and lands once asked
again. A comment nobody can read settles nothing, grants nothing, and retires
nothing. A process that restarted holding nothing reconstructs the attempt
from the comment, and a spent one stays spent.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine.pinned_commit_models import CommitRefusal
from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_standing as _standing,
)
from tests.workflow.stages.decomposition import correction_test_support as support

_STATUS = support.STATUS
_STANDING = support.STANDING
_READING = _standing.CorrectionReading
_CORRECTED = support.SOURCE + 1


def _armed() -> support.CorrectionWorld:
    """A world whose rejected run's attempt is armed, as a fresh process reads it."""
    world = support.seeded()
    world.arms()
    return world.restarted()


def _attempt(world: support.CorrectionWorld):
    """The seeded rejected run's pending attempt."""
    return support.attempt(world)


class UnconfirmedWriteTest(unittest.TestCase):
    """A write nobody confirmed is settled by what its read-back finds."""

    def test_a_lost_acknowledgement_is_read_back(self) -> None:
        world = support.seeded()
        world.github.pinned_failures.lost.add(support.ISSUE)
        sent = world.arms()
        world.github.pinned_failures.lost.clear()
        self.assertEqual(sent.status, _STATUS.UNCONFIRMED)
        self.assertTrue(world.state.withheld, "a write that may have landed holds every whole-state write")
        world.state = world.restarted().state

        read = world.asks(_checkpoint.read_back)
        writes = world.github.write_state_calls
        again = world.arms()

        self.assertEqual(read.reading, _READING(_STANDING.ELIGIBLE, _attempt(world)))
        self.assertEqual(again.status, _STATUS.STANDING)
        self.assertEqual(world.github.write_state_calls, writes)

    def test_an_edit_that_did_not_land_is_read_back(self) -> None:
        world = support.seeded()
        world.github.pinned_failures.refused.add(support.ISSUE)
        sent = world.arms()
        world.github.pinned_failures.refused.clear()
        restarted = world.restarted()

        read = restarted.asks(_checkpoint.read_back)
        again = restarted.arms()

        self.assertEqual(sent.status, _STATUS.UNCONFIRMED)
        self.assertTrue(world.state.withheld)
        self.assertEqual(read.reading, _READING(_STANDING.ABSENT))
        self.assertEqual(again.reading, _READING(_STANDING.ELIGIBLE, _attempt(world)))
        self.assertEqual(again.status, _STATUS.LANDED)

    def test_a_lost_exhaustion_never_rearms(self) -> None:
        world = _armed()
        world.moves(**{support.OWED_STARTED: support.SOURCE, support.USED: _CORRECTED})
        world.github.pinned_failures.lost.add(support.ISSUE)
        world.state = world.restarted().state
        sent = world.asks(_checkpoint.exhaust, _attempt(world))
        world.github.pinned_failures.lost.clear()

        read = world.restarted().asks(_checkpoint.read_back)
        rearmed = world.restarted().arms(support.source(world, _CORRECTED))

        self.assertEqual(sent.status, _STATUS.UNCONFIRMED)
        self.assertEqual(read.reading.standing, _STANDING.EXHAUSTED)
        self.assertEqual(rearmed.refusal, support.REFUSAL.SUPERSEDED)


class UnreadableTest(unittest.TestCase):
    """A comment nobody can read settles nothing."""

    def test_an_unreadable_comment_settles_nothing(self) -> None:
        world = _armed()
        world.github.pinned_failures.unreadable.add(support.ISSUE)
        asked = (
            (_checkpoint.read_back,),
            (_checkpoint.exhaust, _attempt(world)),
            (_checkpoint.retire, _attempt(world)),
            (_checkpoint.arm, support.source(world)),
        )
        for operation, *arguments in asked:
            with self.subTest(operation=operation.__name__):
                outcome = world.asks(operation, *arguments)
                self.assertEqual((outcome.status, outcome.refusal), (_STATUS.REFUSED, CommitRefusal.UNREADABLE))
                self.assertTrue(world.state.withheld)
        self.assertEqual(world.github.write_state_calls, 1)


class RestartTest(unittest.TestCase):
    """What a process holding nothing finds on the comment."""

    def test_a_restart_reconstructs_what_stands(self) -> None:
        # A process holding nothing of the attempt finds it on the comment, and
        # finds a launch the run ledger shows started spent rather than owed.
        world = _armed()
        fresh = world.restarted()
        fresh.state.state_data.pop(support.FIELD)

        pending = fresh.asks(_checkpoint.read_back)
        world.moves(**{support.OWED_STARTED: support.SOURCE, support.USED: _CORRECTED})
        started = world.restarted().asks(_checkpoint.read_back)

        armed = _attempt(world)
        self.assertEqual(pending.reading, _READING(_STANDING.ELIGIBLE, armed))
        self.assertEqual(fresh.state.get(support.FIELD), armed.spelled())
        self.assertEqual(started.reading, _READING(_STANDING.STARTED, armed))


if __name__ == "__main__":
    unittest.main()
