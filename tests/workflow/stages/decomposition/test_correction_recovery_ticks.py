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
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, LABEL_READY
from tests.workflow.stages.decomposition import correction_tick_support as support

# The parent's strict edits, by their place in a correction's tick.
_ARMING = 2
_CORRECTION_ACCOUNTING = 3
_EXHAUSTION = 4

_ADD_RUNS = "/orchestrator add-agent-runs 1"

_ANSWER = "Please include every depends_on list."

_HELD_NOTICE = "decomposer_correction_notice"

_EDITED = "Ship ten slices, then document them."

_CORRECTION = "automatic correction"

_LATER = "Keep streaming too."


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

    @classmethod
    def starting(cls, write) -> _LosesOnce:
        """The writer, failing once on the write that starts a launch owed once."""
        return cls(
            write,
            lambda state: state.get(_run_ledger_values.AGENT_RUN_OWED_STARTED) is not None,
        )

    @classmethod
    def parking(cls, write) -> _LosesOnce:
        """The writer, failing once on the write that takes a park."""
        return cls(write, lambda state: bool(state.get(KEY_AWAITING_HUMAN)))


def _replies_later(world: support.CorrectionTickCase) -> None:
    """A human writes a further reply while a run is out."""
    world.reply(_LATER)


class UnconfirmedWriteTest(unittest.TestCase, support.CorrectionTickCase):
    """Writes nobody confirmed neither charge twice nor authorize a second correction."""

    def test_a_lost_arming_launches_on_the_next_tick(self) -> None:
        self.opened()
        rejected = self.decomposer(support.UNLISTED)
        with support.CountedEdit.losing(self.github, _ARMING):
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
        starting = _LosesOnce.starting(self.github.write_pinned_state)
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

    def test_a_refused_notice_is_said_from_the_record(self) -> None:
        # The second invalid answer's park notice is refused as it is posted:
        # the record still holds it, so the next tick posts it in its own
        # words -- the latest error and the rejected answer -- once.
        self.opened()
        refusing = _LosesOnce(self.github.comment, lambda body: support.CORRECTED_PARK in body)
        with patch.object(self.github, "comment", side_effect=refusing), self.assertRaises(RuntimeError):
            self.tick(self.decomposer(support.UNLISTED, support.SELF_EDGE))
        later = self.decomposer(support.LISTED)

        self.tick(later)
        self.tick(later)

        notice, *again = self.said()
        self.assertEqual((later.launches, again), ([], []))
        self.assertIn(f"manifest invalid ({support.SELF_EDGE_ERROR}) {support.CORRECTED_PARK}", notice)
        self.assertIn('"depends_on": [0]', notice, "the rejected answer is quoted")
        self.assertNotIn(_HELD_NOTICE, self.pinned(), "the held notice is dropped with the park")
        self.assertEqual(self.stage(), support.EXHAUSTED)

    def _unsettled(self, lost: int) -> None:
        """A tick whose correction ran and whose strict edit at `lost` went unconfirmed; nothing made of it."""
        self.opened()
        runner = self.decomposer(support.UNLISTED, support.LISTED)
        with support.CountedEdit.losing(self.github, lost):
            self.tick(runner)
        self.assertEqual(len(runner.launches), 2)
        self.assertEqual(self.children(), 0)

    def _loses_the_park(self):
        """A tick whose correction answered malformed again and whose park lost its write: the notice it posted."""
        self.opened()
        runner = self.decomposer(support.UNLISTED, support.SELF_EDGE)
        parking = _LosesOnce.parking(self.github.write_pinned_state)
        with patch.object(self.github, "write_pinned_state", side_effect=parking), self.assertRaises(RuntimeError):
            self.tick(runner)
        notice = self.issue.comments[-1]
        self.assertIn(support.CORRECTED_PARK, notice.body)
        return notice


class DamagedRecordTest(unittest.TestCase, support.CorrectionTickCase):
    """A correction record nobody can read holds the tick: what it still owes cannot be said, so nothing replaces it."""

    def test_a_damaged_record_holds(self) -> None:
        self._damaged()
        written = self.github.write_state_calls
        later = self.decomposer(support.LISTED)

        self.tick(later)
        self.tick(later)

        self.assertEqual(later.launches, [])
        self.assertEqual(self.children(), 0)
        self.assertEqual(self.said(), [])
        self.assertIsNone(self.pinned()[support.FIELD], "the claim is kept as it stands")
        self.assertEqual(self.github.write_state_calls, written, "nothing is written in its place")

    def _damaged(self) -> None:
        """A rejected run whose arming went unconfirmed, and a hand edit leaving its attempt `null`."""
        self.opened()
        with support.CountedEdit.losing(self.github, _ARMING):
            self.tick(self.decomposer(support.UNLISTED))
        state = self.github.read_pinned_state(self.issue)
        state.set(support.FIELD, None)
        self.github.write_pinned_state(self.issue, state)


class DeferredReplyTest(unittest.TestCase, support.CorrectionTickCase):
    """A correction a later tick launches keeps a reply written past its rejected run's boundary that run's session's.

    The rejected run here is a resume of a park, which settled the boundary
    through the reply it was handed; its arming went unconfirmed, so a later
    tick owes the launch. A reply written before that launch is no edit
    retiring the saved session, and one written during it is left past the
    park the correction's answer takes -- each the next resume's to deliver.
    """

    def test_a_reply_before_the_launch_waits(self) -> None:
        self._owed_behind_a_reply({0: _replies_later})
        later = self.decomposer(support.SINGLE)

        self.tick(later)

        launched = later.launches[0]
        self.assertEqual(len(later.launches), 1)
        self.assertEqual(launched.resumed, support.SESSION)
        self.assertIn(support.UNLISTED_ERROR, launched.prompt)
        self.assertNotIn(_LATER, launched.prompt)
        self.assertEqual(self.stage(), support.EXHAUSTED)

    def test_a_reply_during_the_launch_waits(self) -> None:
        answered = self._owed_behind_a_reply({})
        runner = self.decomposer(support.SELF_EDGE, during={0: _replies_later})
        self.tick(runner)
        parked = self.pinned()
        after = self.decomposer(support.SINGLE)

        self.tick(after)

        self.assertEqual(parked["last_action_comment_id"], answered.id, "the park stops short of the later reply")
        self.assertTrue(parked[KEY_AWAITING_HUMAN])
        self.assertEqual(after.launches[0].resumed, support.SESSION)
        self.assertIn(_LATER, after.launches[0].prompt)

    def _owed_behind_a_reply(self, during: dict):
        """A failed correction's park answered by a reply whose resume answered malformed, its arming unconfirmed."""
        self.opened()
        self.tick(self.decomposer(support.UNLISTED, support.SELF_EDGE))
        answered = self.reply(_ANSWER)
        with support.CountedEdit.losing(self.github, _ARMING):
            self.tick(self.decomposer(support.UNLISTED, during=during))
        self.assertEqual(self.stage(), support.PENDING)
        return answered


class RecoveryLiveTest(unittest.TestCase, support.CorrectionTickCase):
    """A park a later tick owes a correction is taken only over an issue that still stands, read afresh.

    An edit that spent the correction's answer is the drift road's, not a park
    announcing a correction nobody will act on; a hold landing while the
    recovery reads the thread leaves the park, its notice and its write, for
    the tick that finds the hold lifted.
    """

    def test_an_edit_takes_no_park(self) -> None:
        self.opened()
        edits = self.decomposer(support.UNLISTED, support.LISTED, during={1: self._edits})
        self.tick(edits)
        fresh = self.decomposer(support.SINGLE)

        self.tick(fresh)

        self.assertIsNone(fresh.launches[0].resumed, "the edit takes a fresh decomposition")
        self.assertFalse([body for body in self.said() if _CORRECTION in body], "no correction park is announced")
        self.assertIn("issue content changed", self.said()[0])
        self.assertEqual(self.label(), LABEL_READY)

    def test_a_hold_during_recovery_parks_nothing(self) -> None:
        self.opened()
        killed = {"interrupted": True, "exit_code": support.SHUTDOWN_EXIT}
        self.tick(self.decomposer(support.UNLISTED, killed))
        self._read = self.github.comments_after
        with patch.object(self.github, "comments_after", side_effect=self._holds_while_reading):
            self.tick(self.decomposer(support.SINGLE))
        held = self.pinned()
        self.lift()

        self.tick(self.decomposer(support.SINGLE))

        self.assertFalse(held.get(KEY_AWAITING_HUMAN), "no park is written over the hold")
        self.assertEqual(held[support.FIELD]["stage"], support.PENDING)
        self.assertEqual(len(self.said()), 1, "the park is said once, behind the lifted hold")
        self.assertTrue(self.pinned()[KEY_AWAITING_HUMAN])

    def _edits(self, world: support.CorrectionTickCase) -> None:
        """A human edits the issue's body while the correction is out."""
        world.issue.body = _EDITED

    def _holds_while_reading(self, *args, **kwargs):
        """The thread read, with a hold landing on the issue while it is out."""
        self.hold()
        return self._read(*args, **kwargs)


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
