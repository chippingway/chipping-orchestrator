# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The correction a rejected manifest asks for: its run's disposition written, its attempt armed, and its launch.

Asked of the road directly, as the manifest dispatch asks it
(`test_correction_road` drives it through the `decomposing` handler). The
run's own disposition -- here its
session pin and stamp, staged by its caller -- lands whole before anything is
armed, and only over the comment the caller last synced with, so a session a
human pinned meanwhile is never written back over and no attempt is armed
for a conversation the record no longer names. The armed attempt is launched
at once: the saved session resumed under its pinned command with the exact
error, charged once with its daily retry. An unearned answer writes nothing,
and an arming refused asks no launch.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import decomposition_prompts as _prompts, park_watermarks as _park_watermarks
from orchestrator.workflow.stages.decomposition import correction_road as _road
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.stages.decomposition import (
    correction_launch_support as launch_support,
    correction_test_support as support,
)

# What the rejected run's caller staged as its disposition before asking.
_STAMP = "last_agent_action_at"
_STAMPED = "2026-11-03T00:00:00+00:00"

# A session a human pins in place of the rejected run's while it is out.
_REPINNED = "decomposer-pinned-by-hand"

# What the correction's run found on the comment as it ran: its rejected run's
# disposition, its attempt, its charge's start, and its daily retry.
_LANDED_FIRST = (support.SESSION_PIN, _STAMP, support.FIELD, support.OWED_STARTED, launch_support.RETRIES)

# The run count its one charge leaves.
_CHARGED = support.SOURCE + 1

# A saved session spread over two lines.
_TWO_LINES = "decomposer-session-1\n--resume elsewhere"

# What earns no correction over a staged disposition, by the session its caller
# staged and its run's answer: a question, a run that returned no session while
# an older pin stands, and a saved session no resume may name -- one an option
# parser would take for a flag, or one over two lines.
_UNEARNED = (
    ("a question", support.SESSION, {"last_message": "Split or not?"}),
    ("no returned session beside an older pin", support.SESSION, {"session_id": None}),
    ("an option-shaped session", "--last", {"session_id": "--last"}),
    ("a session over two lines", _TWO_LINES, {"session_id": _TWO_LINES}),
)

# What it ran as: the pinned backend, asked with the exact error, in the saved checkout.
_RESUMED = ("codex", _prompts._build_correction_prompt(support.DIAGNOSTIC), launch_support.CHECKOUT)

# The reply boundary the seeded record carries, and a trusted reply written past it.
_BOUNDARY = "last_action_comment_id"
_PAST_IT = 950
_TRUSTED = "alice"


def _unsaved() -> support.CorrectionWorld:
    """A world whose rejected run's session pin and stamp are its caller's staged disposition, not on the comment."""
    world = support.seeded()
    reading = world.github.read_pinned_state(world.issue)
    reading.state_data.pop(support.SESSION_PIN)
    world.github.write_pinned_state(world.issue, reading)
    staged = world.restarted()
    staged.state.set(support.SESSION_PIN, support.SESSION)
    staged.state.set(_STAMP, _STAMPED)
    return staged


def _repinned(behind: bool) -> tuple[support.CorrectionWorld, launch_support.Runner, _road.CorrectionAsk]:
    """The correction asked over a session pinned by hand while the run was out, or `behind` the read-back."""
    world = _unsaved()
    runner = launch_support.Runner(world)
    repinned = {support.SESSION_PIN: _REPINNED}
    if not behind:
        world.moves(**repinned)
        return world, runner, runner.requests(launch_support.rejected(world))
    with support.interfering(world, **repinned):
        return world, runner, runner.requests(launch_support.rejected(world))


def _landed(world: support.CorrectionWorld) -> tuple:
    """What `_LANDED_FIRST` reads as once the disposition, the arming, the charge, and its start have landed."""
    return (support.SESSION, _STAMPED, support.attempt(world).spelled(), support.SOURCE, 1)


def _unearned(session: str, answer: dict) -> tuple[_road.CorrectionAsk, bool, list]:
    """The correction asked over a staged disposition whose session is `session`, its run answering `answer`.

    Answered with what the ask came to, whether the comment, the writes sent,
    and the caller's state all stand as they were, and the processes invoked.
    """
    world = _unsaved()
    world.state.set(support.SESSION_PIN, session)
    before = world.snapshot()
    runner = launch_support.Runner(world)
    asked = runner.requests(launch_support.rejected(world, **answer))
    return asked, world.snapshot() == before, runner.launches


class DispositionTest(unittest.TestCase):
    """The run's disposition lands before its attempt is armed, and only over the comment it was read from."""

    def test_the_disposition_lands_before_the_arming(self) -> None:
        world = _unsaved()
        runner = launch_support.Runner(world)

        asked = runner.requests(launch_support.rejected(world))

        launched = runner.launches[0]
        found = tuple(launched[-1].get(key) for key in _LANDED_FIRST)
        self.assertEqual(found, _landed(world), "each landed before the correction ran")
        self.assertEqual(launched[:3], _RESUMED)
        self.assertEqual(launched[3].resume_session_id, support.SESSION)
        self.assertEqual(asked.attempt, support.attempt(world))
        self.assertTrue(asked.bounded)
        self.assertFalse(asked.held)
        self.assertEqual(world.record()[support.USED], _CHARGED, "charged once")

    def test_a_moved_comment_arms_nothing(self) -> None:
        for behind in (False, True):
            with self.subTest(behind_the_read_back=behind):
                world, runner, asked = _repinned(behind)

                self.assertEqual(asked, _road.CorrectionAsk(held=True))
                self.assertEqual(runner.launches, [])
                self.assertEqual(world.record()[support.SESSION_PIN], _REPINNED)
                self.assertNotIn(support.FIELD, world.record())
                self.assertNotIn(_STAMP, world.record(), "the disposition is not written over the move")
                self.assertTrue(world.state.withheld)

    def test_an_unearned_answer_writes_nothing(self) -> None:
        for name, *answered in _UNEARNED:
            with self.subTest(name):
                asked, untouched, launches = _unearned(*answered)

                self.assertEqual(asked, _road.CorrectionAsk())
                self.assertTrue(untouched, "nothing written, armed, or staged")
                self.assertEqual(launches, [])

    def test_a_refused_arming_asks_no_launch(self) -> None:
        # A charge another road took behind the rejected run: its disposition
        # lands, but no attempt is armed for a source something ran behind,
        # and nothing is launched or held, so its caller parks as before.
        world = support.seeded(**{support.USED: _CHARGED})
        world.state.set(_STAMP, _STAMPED)
        runner = launch_support.Runner(world)

        asked = runner.requests(launch_support.rejected(world))

        self.assertEqual(asked, _road.CorrectionAsk())
        self.assertEqual(world.record()[_STAMP], _STAMPED)
        self.assertNotIn(support.FIELD, world.record())
        self.assertEqual(runner.launches, [])


class BoundsTest(unittest.TestCase):
    """A launch's parks are bounded where the scope bounds them or the boundary is the one its baseline settled."""

    def test_bounds_follow_the_settled_boundary(self) -> None:
        # A reply past the boundary leaves the thread through it the revision
        # the run was handed; with no boundary there is no settled stretch.
        self.enterContext(patch.object(config, "ALLOWED_ISSUE_AUTHORS", (_TRUSTED,)))
        world = support.seeded()
        reply = FakeComment(id=_PAST_IT, body="Keep streaming.", user=FakeUser(_TRUSTED))
        world.issue.comments.append(reply)
        asked = (world.github, world.issue, world.state, support.source(world))

        bounded = [_road.bounds(*asked)]
        world.state.state_data.pop(_BOUNDARY)
        bounded.append(_road.bounds(*asked))
        with _park_watermarks.bounded_parks(True):
            bounded.append(_road.bounds(*asked))

        self.assertEqual(bounded, [True, False, True], "settled, unsettled, and scoped")


if __name__ == "__main__":
    unittest.main()
