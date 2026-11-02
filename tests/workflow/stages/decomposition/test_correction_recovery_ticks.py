# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A manifest correction across writes nobody confirmed, restarts, and the run-limit park, tick by tick.

Every tick here is a process holding nothing from the one before it. An
arming whose response was lost holds its tick, and the next one launches the
correction it reads back, once. A start that did not land leaves its charge for
the next tick to start rather than pay again. A correction whose accounting or
exhaustion was never confirmed is never launched again: the next tick parks
for a human, once, and a park whose own write was lost is recorded over the
notice it already posted rather than said twice. A spent run ledger parks the
correction's launch on the run limit, and only the grant that lifts it buys
that launch.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.engine import run_ledger_values as _run_ledger_values, run_limit_values as _run_limit_values
from tests.workflow.fixtures import KEY_AWAITING_HUMAN
from tests.workflow.stages.decomposition import correction_tick_support as support

# The parent's strict edits, by their place in a correction's tick.
_ARMING = 2
_CORRECTION_ACCOUNTING = 3
_EXHAUSTION = 4

_ADD_RUNS = "/orchestrator add-agent-runs 1"


class _LosesOnce:
    """The whole-state writer, failing once on the first write `losing` picks."""

    def __init__(self, write, losing) -> None:
        self._write = write
        self._losing = losing
        self.lost = False

    def __call__(self, issue, state):
        if not self.lost and self._losing(state):
            self.lost = True
            raise RuntimeError("502")
        return self._write(issue, state)


def _starting(state) -> bool:
    """Whether a whole-state write starts a launch owed once."""
    return state.get(_run_ledger_values.AGENT_RUN_OWED_STARTED) is not None


def _parking(state) -> bool:
    """Whether a whole-state write takes a park."""
    return bool(state.get(KEY_AWAITING_HUMAN))


class UnconfirmedWriteTest(unittest.TestCase, support.CorrectionTickCase):
    """Writes nobody confirmed neither charge twice nor authorize a second correction."""

    def test_a_lost_arming_launches_on_the_next_tick(self) -> None:
        self.opened()
        rejected = self.decomposer(support.UNLISTED)
        with support.LosingEdit.patch(self.github, _ARMING):
            self.tick(rejected)
        self.assertEqual(self.said(), [])
        later = self.decomposer(support.LISTED)

        self.tick(later)
        self.tick(later)

        self.assertEqual(len(later.launches), 1, "the correction read back, launched once")
        self.assertEqual(later.launches[0].resumed, support.SESSION)
        self.assertIn(f"> {support.UNLISTED_ERROR}", later.launches[0].prompt, "the error the record keeps")
        self.assertEqual(self.children(), support.SLICES)

    def test_a_lost_start_is_started_once(self) -> None:
        # The write that would start the correction's charge fails: nothing is
        # invoked, and the next tick starts the charge it reserved.
        self.opened()
        rejected = self.decomposer(support.UNLISTED)
        starting = _LosesOnce(self.github.write_pinned_state, _starting)
        with patch.object(self.github, "write_pinned_state", side_effect=starting):
            self.tick(rejected)
        later = self.decomposer(support.LISTED)

        self.tick(later)

        self.assertEqual(len(rejected.launches), 1)
        self.assertEqual(len(later.launches), 1)
        self.assertEqual(self.runs(), 2)
        self.assertEqual(self.children(), support.SLICES)

    def test_an_unsettled_correction_parks_once(self) -> None:
        # The correction ran, and its accounting or its exhaustion was never
        # confirmed: nothing is made of its answer, and the next tick parks
        # for a human rather than launching it again, once.
        for name, lost in (("its accounting", _CORRECTION_ACCOUNTING), ("its exhaustion", _EXHAUSTION)):
            with self.subTest(name):
                self._unsettled(lost)
                later = self.decomposer(support.LISTED)

                self.tick(later)
                self.tick(later)

                self.assertEqual(later.launches, [])
                self.assertEqual(len(self.said()), 1)
                self.assertIn(f"manifest invalid ({support.UNLISTED_ERROR})", self.said()[0])
                self.assertTrue(self.pinned()[KEY_AWAITING_HUMAN])
                self.assertEqual(self.stage(), support.EXHAUSTED)
                self.assertEqual(self.runs(), 2)

    def test_a_lost_park_is_said_once(self) -> None:
        # The second invalid answer's park posts its notice and loses its
        # write: the next tick finds the notice by its receipt and records the
        # park over it, saying nothing again.
        notice = self._loses_the_park()
        later = self.decomposer(support.LISTED)

        self.tick(later)

        pinned = self.pinned()
        self.assertEqual(later.launches, [])
        self.assertEqual(len(self.said()), 1, "the park is not said twice")
        self.assertTrue(pinned[KEY_AWAITING_HUMAN])
        self.assertEqual(pinned["last_action_comment_id"], notice.id)
        self.assertEqual(self.stage(), support.EXHAUSTED)

    def _unsettled(self, lost: int) -> None:
        """A tick whose correction ran and whose strict edit at `lost` went unconfirmed; nothing made of it."""
        self.opened()
        runner = self.decomposer(support.UNLISTED, support.LISTED)
        with support.LosingEdit.patch(self.github, lost):
            self.tick(runner)
        self.assertEqual(len(runner.launches), 2)
        self.assertEqual(self.children(), 0)

    def _loses_the_park(self):
        """A tick whose correction answered malformed again and whose park lost its write: the notice it posted."""
        self.opened()
        runner = self.decomposer(support.UNLISTED, support.SELF_EDGE)
        parking = _LosesOnce(self.github.write_pinned_state, _parking)
        with patch.object(self.github, "write_pinned_state", side_effect=parking), self.assertRaises(RuntimeError):
            self.tick(runner)
        notice = self.issue.comments[-1]
        self.assertIn(support.CORRECTED_PARK, notice.body)
        return notice


class RunLimitTest(unittest.TestCase, support.CorrectionTickCase):
    """A spent run ledger parks the correction's launch, and the grant that lifts it buys that launch alone."""

    def test_a_grant_buys_the_correction(self) -> None:
        self._refused_at_the_limit()
        self.reply(_ADD_RUNS)
        granted = self.decomposer(support.LISTED)

        self.dispatch(granted)

        self.assertEqual(len(granted.launches), 1)
        self.assertEqual(granted.launches[0].resumed, support.SESSION)
        self.assertEqual(self.children(), support.SLICES)
        self.assertEqual(self.runs(), 2)
        self.assertEqual(self.stage(), support.EXHAUSTED)

    def _refused_at_the_limit(self) -> None:
        """An issue allowed one run: its rejected run's correction refused at the limit, and a held tick behind it."""
        self.opened(**{_run_ledger_values.AGENT_RUN_ALLOWANCE: 1})
        rejected = self.decomposer(support.UNLISTED)
        self.dispatch(rejected)
        refused = self.pinned()
        held = self.decomposer(support.LISTED)
        self.dispatch(held)
        self.assertEqual(len(rejected.launches) + len(held.launches), 1)
        self.assertEqual(refused["park_reason"], _run_limit_values.PARK_AGENT_RUN_LIMIT)
        self.assertEqual(refused[support.FIELD]["stage"], support.PENDING)


if __name__ == "__main__":
    unittest.main()
