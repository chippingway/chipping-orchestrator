# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A manifest correction held to the issue as GitHub answers for it, behind its charge and before its answer is used.

A hold, a close, a relabel, or an edit landing between the rejection and the
launch invokes nothing, and one landing while the correction ran makes no
child, split marker, or label of its answer. A hold leaves the attempt to
launch or to give up once it is lifted; an edit is routed through the drift
reset's fresh decomposition with the attempt resolved, never replenished.
"""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.state import WorkflowLabel
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, LABEL_READY
from tests.workflow.stages.decomposition import correction_tick_support as support

_EDITED = "Ship ten slices, then document them."


def _edit(world: support.CorrectionTickCase) -> None:
    world.issue.body = _EDITED


def _close(world: support.CorrectionTickCase) -> None:
    world.issue.closed = True


def _relabel(world: support.CorrectionTickCase) -> None:
    world.github.set_workflow_label(world.issue, WorkflowLabel.READY)


def _unreadable(world: support.CorrectionTickCase) -> None:
    raise RuntimeError("502")


def _repin(world: support.CorrectionTickCase) -> None:
    """A human pins another decomposer session in place of the one the correction resumes."""
    reading = world.github.read_pinned_state(world.issue)
    reading.set("decomposer_session_id", _REPINNED)
    world.github.write_pinned_state(world.issue, reading)


_REPINNED = "dec-pinned-by-hand"

_GUIDANCE = "Requirements update: do not split; deliver one command-line entry point."

# The daily retry budget a held correction's charge is counted against, and what
# the rejected run and its correction leave counted there.
_DAILY_BUDGET = 3
_RETRIES_PAID = 2

_HELD_NOTICE = "decomposer_correction_notice"

# What the park behind an answer nothing could act on says.
_UNACTED = "was started, but nothing could act on its answer"

# A correction's answer kept from being used, beside what its next tick's park
# says: a hold met as it returns, an issue GitHub would not answer for before
# it is used, and a second invalid answer met by a hold behind the write
# holding its park's notice, which that park then says in its own words.
_HELD_ANSWERS = (
    ("a hold", support.LISTED, {1: lambda world: world.hold()}, None, _UNACTED),
    ("an unread issue", support.LISTED, {}, (support.BEHIND_THE_RETURN, _unreadable), _UNACTED),
    (
        "a hold behind the held notice",
        support.SELF_EDGE,
        {},
        (support.BEHIND_THE_NOTICE, lambda world: world.hold()),
        f"({support.SELF_EDGE_ERROR}) {support.CORRECTED_PARK}",
    ),
)

# A hold landing while a later read of a check was out, by the fetch it lands
# ahead of, beside how many runs that leaves launched: behind the thread read
# behind the charge, behind the reading the start is written over, and behind
# the saved context's read before a usable answer is acted on.
_LATE_WINDOWS = (
    ("the thread behind the charge", support.BEHIND_THE_THREAD, 1),
    ("the start's reading", support.BEFORE_THE_START, 1),
    ("the saved context", support.BEHIND_THE_CONTEXT, 2),
)

# Each of those windows met by a hold and by an edit of the requirements.
_LATE_MOVES = tuple(
    (f"{moved} during {window}", nth, move, launched)
    for window, nth, launched in _LATE_WINDOWS
    for moved, move in (("a hold", lambda world: world.hold()), ("an edit", _edit))
)

# The days a held correction waits out, past the daily retry window it was charged in.
_DAYS_LATER = 2

# What moves the requirements while the rejected run is out, beside the words
# the fresh decomposition is handed for it: its body edited, and a trusted
# reply on a thread with no reply boundary a reply could stand past.
_EDITS = (
    ("a body edit", _edit, _EDITED),
    ("a reply with no boundary", lambda world: world.reply(_GUIDANCE), _GUIDANCE),
)

# Owners the issue moves to, by the label it is left reading.
_MOVED_OWNERS = (("closed", _close, support.LABEL_DECOMPOSING), ("relabelled", _relabel, LABEL_READY))

# Each of those moves met by a usable correction and by a second invalid one.
_MOVED_ANSWERS = tuple(
    (f"{name}, {answered}", move, label, answer)
    for name, move, label in _MOVED_OWNERS
    for answered, answer in (("usable", support.LISTED), ("invalid", support.SELF_EDGE))
)


class BeforeLaunchTest(unittest.TestCase, support.CorrectionTickCase):
    """What lands between the rejection and the correction's start invokes nothing.

    Nor does a hold landing while any later read of a check was out: each
    check ends on the issue's controls, asked afresh behind its last read.
    """

    def test_an_edit_takes_the_fresh_decomposition(self) -> None:
        # The requirements moved while the rejected run was out -- the body
        # edited, or a trusted reply written where no reply boundary stands
        # for it to wait past: its correction is never launched, and the next
        # tick's reset retires the attempt and spawns the fresh decomposition
        # the edit buys, handed what moved.
        self.enterContext(patch.object(config, "ALLOWED_ISSUE_AUTHORS", (support.TRUSTED_AUTHOR,)))
        for name, move, edited in _EDITS:
            with self.subTest(name):
                self.opened()
                self.tick(self.decomposer(support.UNLISTED, during={0: move}))
                self.assertEqual(self.runs(), 1, "no correction is launched")
                fresh = self.decomposer(support.SINGLE)

                self.tick(fresh)

                launched = fresh.launches[0]
                self.assertIsNone(launched.resumed, "a fresh conversation, not the correction")
                self.assertIn(edited, launched.prompt)
                self.assertEqual(self.stage(), support.RETIRED)
                self.assertEqual(self.label(), LABEL_READY)

    def test_a_hold_defers_the_launch(self) -> None:
        # A hold applied behind the arming refuses the start with its charge
        # kept; once lifted, the next tick starts that very charge -- in the
        # same daily retry window, or after it rolled over, the launch being
        # the same one whatever retry count the window has rolled to, and the
        # daily retry it paid with that charge paid once.
        self.enterContext(patch.object(config, "MAX_RETRIES_PER_DAY", _DAILY_BUDGET))
        for name, rolled in (("the same window", False), ("the next window", True)):
            with self.subTest(name):
                self._held_behind_the_charge()
                self.lift()
                if rolled:
                    self._rolls_the_window()
                later = self.decomposer(support.LISTED)

                self.tick(later)

                self.assertEqual(len(later.launches), 1)
                self.assertEqual(later.launches[0].resumed, support.SESSION)
                paid = (self.runs(), self.pinned()["retry_count"])
                self.assertEqual(paid, (2, _RETRIES_PAID), "the held charge and its daily retry are not paid again")
                self.assertEqual(self.children(), support.SLICES)

    def test_a_late_hold_makes_nothing(self) -> None:
        # A hold or an edit landing while a later read of a check was out is
        # met by the issue fetched last, whose controls and requirements are
        # the ones judged: no stale correction is invoked, and no stale answer
        # is acted on.
        for name, nth, move, launched in _LATE_MOVES:
            with self.subTest(name):
                self.opened()
                runner = self.decomposer(support.UNLISTED, support.LISTED)
                with support.OnFetch.patch(self, nth, move):
                    self.tick(runner)

                self.assertEqual(len(runner.launches), launched)
                self.assertEqual(self.children(), 0)
                self.assertFalse(set(support.SPLIT_MARKERS) & set(self.pinned()))
                self.assertEqual(self.label(), support.LABEL_DECOMPOSING)
                self.assertEqual(self.said(), [])

    def test_a_repinned_source_arms_nothing(self) -> None:
        # A session a human pins in place of the rejected run's while it is
        # out: the run's disposition is not written back over the pin, and no
        # correction is armed for, or launched on, the displaced session.
        self.opened()
        runner = self.decomposer(support.UNLISTED, support.SINGLE, during={0: _repin})

        self.tick(runner)

        self.assertEqual(len(runner.launches), 1)
        self.assertEqual(self.pinned()["decomposer_session_id"], _REPINNED)
        self.assertIsNone(self.stage())
        self.assertEqual(self.said(), [])

    def test_a_moved_owner_launches_nothing(self) -> None:
        for name, move, label in _MOVED_OWNERS:
            with self.subTest(name):
                self.opened()
                runner = self.decomposer(support.UNLISTED)
                with support.OnFetch.patch(self, support.BEHIND_THE_CHARGE, move):
                    self.tick(runner)

                self.assertEqual(len(runner.launches), 1)
                self.assertEqual(self.said(), [])
                self.assertEqual(self.children(), 0)
                self.assertEqual(self.label(), label)

    def _held_behind_the_charge(self) -> None:
        """A tick whose correction a hold applied behind its charge refused, the charge left reserved."""
        self.opened()
        held = self.decomposer(support.UNLISTED)
        with support.OnFetch.patch(self, support.BEHIND_THE_CHARGE, lambda world: world.hold()):
            self.tick(held)
        self.assertEqual(len(held.launches), 1)
        self.assertEqual(self.runs(), 2)
        self.assertEqual(self.pinned()["agent_run_reservation"], "reserved")

    def _rolls_the_window(self) -> None:
        """The daily retry window the held correction was charged in runs out."""
        reading = self.github.read_pinned_state(self.issue)
        opened = datetime.now(UTC) - timedelta(days=_DAYS_LATER)
        reading.set("retry_window_start", opened.isoformat(timespec="seconds"))
        self.github.write_pinned_state(self.issue, reading)


class AfterReturnTest(unittest.TestCase, support.CorrectionTickCase):
    """What lands while the correction runs makes nothing of its answer."""

    def test_an_edit_spends_the_answer(self) -> None:
        self.opened()
        edited = self.decomposer(support.UNLISTED, support.LISTED, during={1: _edit})
        self.tick(edited)
        self.assertEqual(self.children(), 0)
        self.assertEqual(self.stage(), support.EXHAUSTED)
        fresh = self.decomposer(support.SINGLE)

        self.tick(fresh)

        self.assertEqual(len(fresh.launches), 1)
        self.assertIsNone(fresh.launches[0].resumed)
        self.assertIn(_EDITED, fresh.launches[0].prompt)
        self.assertEqual(self.label(), LABEL_READY)

    def test_a_moved_owner_makes_nothing(self) -> None:
        # Closed or handed to another label while the correction ran: neither a
        # usable answer nor a second invalid one makes a child, a split marker,
        # a label, or a park on an owner the answer no longer belongs to.
        for name, move, label, answer in _MOVED_ANSWERS:
            with self.subTest(name):
                self.opened()
                runner = self.decomposer(support.UNLISTED, answer, during={1: move})

                self.tick(runner)

                self.assertEqual(self.children(), 0)
                self.assertFalse(set(support.SPLIT_MARKERS) & set(self.pinned()))
                self.assertEqual(self.label(), label)
                self.assertEqual(self.stage(), support.EXHAUSTED)
                self.assertEqual(self.said(), [], "no park is taken on the owner it moved to")
                self.assertFalse(self.pinned().get(KEY_AWAITING_HUMAN))

    def test_a_moved_session_makes_nothing(self) -> None:
        # A session a human pinned in place of the saved one while the
        # correction ran is no conversation its answer belongs to: nothing is
        # made of a usable one, no park is taken on an invalid one, and the
        # pin is left as the human wrote it.
        for answered, answer in (("usable", support.LISTED), ("invalid", support.SELF_EDGE)):
            with self.subTest(answered):
                self.opened()
                runner = self.decomposer(support.UNLISTED, answer, during={1: _repin})

                self.tick(runner)

                self.assertEqual(len(runner.launches), 2)
                self.assertEqual(self.children(), 0)
                self.assertEqual(self.said(), [])
                self.assertFalse(self.pinned().get(KEY_AWAITING_HUMAN))
                self.assertEqual(self.label(), support.LABEL_DECOMPOSING)
                self.assertEqual(self.pinned()["decomposer_session_id"], _REPINNED)

    def test_a_held_answer_parks_once_it_can(self) -> None:
        # A hold met as the correction returns or behind the write holding its
        # park's notice, or an issue GitHub would not answer for before its
        # answer is used, makes nothing, says nothing, and spends nothing: the
        # next readable, unheld tick parks for a human, once, rather than
        # launching the correction again.
        for name, *answered, said in _HELD_ANSWERS:
            with self.subTest(name):
                self._answer_held(*answered)
                later = self.decomposer(support.LISTED)

                self.tick(later)

                self.assertEqual(later.launches, [])
                self.assertTrue(self.pinned()[KEY_AWAITING_HUMAN])
                self.assertEqual(self.stage(), support.EXHAUSTED)
                self.assertEqual(len(self.said()), 1)
                self.assertIn(said, self.said()[0])
                self.assertNotIn(_HELD_NOTICE, self.pinned(), "a notice held is dropped with its park")

    def test_a_hold_behind_the_exhaustion(self) -> None:
        # A hold landing right behind the write that spends the correction
        # makes nothing of its usable answer; once lifted, the next tick parks
        # for a human over the spent attempt rather than launching it again.
        self._held_behind_the_exhaustion()
        self.lift()
        later = self.decomposer(support.LISTED)

        self.tick(later)

        self.assertEqual(later.launches, [])
        self.assertEqual(len(self.said()), 1)
        self.assertIn("returned, but nothing was made of its answer", self.said()[0])
        self.assertTrue(self.pinned()[KEY_AWAITING_HUMAN])

    def _held_behind_the_exhaustion(self) -> None:
        """A tick whose correction answered usably, held right behind the write that spent it: nothing made."""
        self.opened()
        runner = self.decomposer(support.UNLISTED, support.LISTED)
        with support.CountedEdit.landing(self, support.EXHAUSTION, lambda world: world.hold()):
            self.tick(runner)
        self.assertEqual(self.children(), 0)
        self.assertFalse(set(support.SPLIT_MARKERS) & set(self.pinned()))
        self.assertEqual(self.label(), support.LABEL_DECOMPOSING)
        self.assertEqual(self.stage(), support.EXHAUSTED)

    def _answer_held(self, answer: str, during: dict, fetched: tuple | None) -> None:
        """A tick whose correction's `answer` a hold, or an unread issue, kept from being used; the hold lifted after.

        `fetched` is the issue fetch a move lands ahead of, and the move.
        """
        self.opened()
        runner = self.decomposer(support.UNLISTED, answer, during=during)
        if fetched is None:
            self.tick(runner)
        else:
            with support.OnFetch.patch(self, *fetched):
                self.tick(runner)
        self.assertEqual(self.stage(), support.PENDING)
        self.assertEqual(self.children(), 0)
        self.assertEqual(self.said(), [], "nothing is said of it")
        self.lift()


if __name__ == "__main__":
    unittest.main()
