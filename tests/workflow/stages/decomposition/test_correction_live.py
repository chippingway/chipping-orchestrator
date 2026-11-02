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


# Owners the issue moves to, by the label it is left reading.
_MOVED_OWNERS = (("closed", _close, support.LABEL_DECOMPOSING), ("relabelled", _relabel, LABEL_READY))


class BeforeLaunchTest(unittest.TestCase, support.CorrectionTickCase):
    """What lands between the rejection and the correction's start invokes nothing."""

    def test_an_edit_takes_the_fresh_decomposition(self) -> None:
        # The body edited while the rejected run was out: its correction is
        # never launched, and the next tick's reset retires the attempt and
        # spawns the fresh decomposition the edit buys.
        self.opened()
        self.tick(self.decomposer(support.UNLISTED, during={0: _edit}))
        self.assertEqual(self.stage(), support.PENDING)
        fresh = self.decomposer(support.SINGLE)

        self.tick(fresh)

        launched = fresh.launches[0]
        self.assertEqual(len(fresh.launches), 1)
        self.assertIsNone(launched.resumed, "a fresh conversation, not the correction")
        self.assertIn(_EDITED, launched.prompt)
        self.assertEqual(self.stage(), support.RETIRED)
        self.assertEqual(self.label(), LABEL_READY)

    def test_a_hold_defers_the_launch(self) -> None:
        # A hold applied behind the arming refuses the start with its charge
        # kept; once lifted, the next tick starts that very charge.
        self._held_behind_the_charge()
        self.lift()
        later = self.decomposer(support.LISTED)

        self.tick(later)

        self.assertEqual(len(later.launches), 1)
        self.assertEqual(later.launches[0].resumed, support.SESSION)
        self.assertEqual(self.runs(), 2, "the held charge is started, not paid again")
        self.assertEqual(self.children(), support.SLICES)

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
        for name, move, label in _MOVED_OWNERS:
            with self.subTest(name):
                self.opened()
                runner = self.decomposer(support.UNLISTED, support.LISTED)
                with support.OnFetch.patch(self, support.BEFORE_ACTING, move):
                    self.tick(runner)

                self.assertEqual(len(runner.launches), 2)
                self.assertEqual(self.children(), 0)
                self.assertFalse(set(support.SPLIT_MARKERS) & set(self.pinned()))
                self.assertEqual(self.label(), label)
                self.assertEqual(self.stage(), support.EXHAUSTED)

    def test_a_held_answer_parks_once_it_can(self) -> None:
        # A hold met as the correction returns, or an issue GitHub would not
        # answer for before its answer is used, makes nothing and spends
        # nothing: the next readable, unheld tick parks for a human rather
        # than launching the correction again.
        for name, during, fetched in (
            ("a hold", {1: lambda world: world.hold()}, None),
            ("an unread issue", {}, _unreadable),
        ):
            with self.subTest(name):
                self._answer_held(during, fetched)
                later = self.decomposer(support.LISTED)

                self.tick(later)

                self.assertEqual(later.launches, [])
                self.assertTrue(self.pinned()[KEY_AWAITING_HUMAN])
                self.assertEqual(self.stage(), support.EXHAUSTED)
                self.assertEqual(len(self.said()), 1)

    def _answer_held(self, during: dict, fetched) -> None:
        """A tick whose correction's answer a hold, or an unread issue, kept from being used; the hold lifted after."""
        self.opened()
        runner = self.decomposer(support.UNLISTED, support.LISTED, during=during)
        if fetched is None:
            self.tick(runner)
        else:
            with support.OnFetch.patch(self, support.BEFORE_ACTING - 1, fetched):
                self.tick(runner)
        self.assertEqual(self.stage(), support.PENDING)
        self.assertEqual(self.children(), 0)
        self.lift()


if __name__ == "__main__":
    unittest.main()
