# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A manifest correction against what moves between the reads and writes that carry it.

A session a human pins between the read-back and the rejected run's
disposition is never written back over, and no correction is armed for the
displaced one. A cycle moved right behind the exhaustion makes nothing of the
corrected answer and is kept as the human wrote it. A later tick's recovery
that reads the requirements moved on an issue GitHub answers apart from the
tick's snapshot hands that reading to the drift road, so the fresh
decomposition reads what moved, and one whose record moves on to another cycle,
or to a session a human pinned, while it reads the thread parks nothing and
says nothing over it. A moved attempt's retirement writes the tick's reset
only over the comment it read, so a pin or a claim a human wrote right before
that write is kept and the tick holds, and no fresh decomposer is charged
behind an attempt the retirement could not resolve. And a corrected split its
tick began and never handed off is finished by the split recovery, not parked
in its place.
"""
from __future__ import annotations

import copy
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition import correction_checkpoint as _checkpoint
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, LABEL_READY
from tests.workflow.stages.decomposition import correction_tick_support as support

_HUMAN_PIN = "human-pinned-session"

_SESSION_PIN = "decomposer_session_id"

_CYCLE = "late_cycle_id"

_CHANGED = "Changed requirements: deliver one command only; do not split."

_BLOCKED = "workflow:blocked"

_HANDOFF_LOST = "simulated process loss before the split's handoff"

# What a shutdown-killed correction reports.
_KILLED = MappingProxyType({"interrupted": True, "exit_code": support.SHUTDOWN_EXIT})

# What moves the record while a later tick's recovery reads the thread: the
# thread read it lands during -- the receipt's, then the issue's last read
# behind the comment's check -- the field, and what it is moved to.
_MID_RECOVERY = (
    ("a cycle during the receipt's read", 1, _CYCLE, 1),
    ("a session during the last live read", 2, _SESSION_PIN, _HUMAN_PIN),
)

# What a human writes right before the retirement writes the tick's reset: a
# session pinned in place of the one the reset clears, and the claim edited to
# a `null` nothing can read.
# The strict edit that drops the notice a retired attempt left held: the
# second of the retiring tick, behind the retirement's own.
_THE_DROP = 2

# The pinned field a park's notice is held under before its post.
_HELD_NOTICE = "decomposer_correction_notice"

_BEFORE_THE_RESET = (
    ("a session pinned", _SESSION_PIN, _HUMAN_PIN),
    ("a claim damaged", support.FIELD, None),
)


class TickMoveTest(unittest.TestCase, support.CorrectionTickCase):
    """What a human writes between the reads and writes of a correction's own tick is kept, and acted on by nothing."""

    def test_a_pin_behind_the_read_back_arms_nothing(self) -> None:
        # The human pins another session right behind the read-back the
        # rejected run's disposition is written over: that write lands
        # nowhere, so the pin stands and no correction is armed for, or
        # launched on, the displaced one.
        self.opened()
        self._pinned = False
        self._read_back = _checkpoint.read_back
        runner = self.decomposer(support.UNLISTED, support.SINGLE)
        with patch.object(_checkpoint, "read_back", side_effect=self._pins_behind_the_read_back):
            self.tick(runner)

        self.assertTrue(self._pinned, "the disposition's read-back was reached")
        self.assertEqual(len(runner.launches), 1)
        self.assertEqual(self.pinned()[_SESSION_PIN], _HUMAN_PIN)
        self.assertIsNone(self.stage())
        self.assertEqual(self.said(), [])
        self.assertEqual(self.label(), support.LABEL_DECOMPOSING)

    def test_a_moved_cycle_makes_nothing(self) -> None:
        # The record moves on to another cycle right behind the write that
        # spends the correction: its usable answer makes no child, and no
        # whole-state write puts the earlier cycle back.
        self.opened()
        with support.CountedEdit.landing(self, support.EXHAUSTION, self._moves_the_cycle):
            self.tick(self.decomposer(support.UNLISTED, support.LISTED))

        self.assertEqual(self.pinned().get(_CYCLE), 1, "the later cycle is kept")
        self.assertEqual(self.children(), 0)
        self.assertFalse(set(support.SPLIT_MARKERS) & set(self.pinned()))
        self.assertEqual(self.said(), [])
        self.assertEqual(self.label(), support.LABEL_DECOMPOSING)

    def _pins_behind_the_read_back(self, gh, issue, state):
        """The read-back, with a human pinning another session right behind the tick's first."""
        read = self._read_back(gh, issue, state)
        if not self._pinned:
            self._pinned = True
            reading = gh.read_pinned_state(issue)
            reading.set(_SESSION_PIN, _HUMAN_PIN)
            gh.write_pinned_state(issue, reading)
        return read

    def _moves_the_cycle(self, world: support.CorrectionTickCase) -> None:
        """A human moves the record onto the next cycle."""
        reading = world.github.read_pinned_state(world.issue)
        reading.set(_CYCLE, 1)
        world.github.write_pinned_state(world.issue, reading)


class RecoveryReadTest(unittest.TestCase, support.CorrectionTickCase):
    """A later tick's recovery acts on what it read, and leaves a begun split to the split recovery."""

    def test_a_moved_body_reaches_the_fresh_run(self) -> None:
        # GitHub answers the issue apart from the tick's snapshot, its body
        # changed: the recovery reads the requirements moved, spends the
        # attempt, and the drift road's fresh decomposition is handed the
        # changed body rather than the snapshot's.
        self.opened()
        self.tick(self.decomposer(support.UNLISTED, _KILLED))
        self._current = copy.deepcopy(self.issue)
        self._current.body = _CHANGED
        self._fetch = self.github.get_issue
        later = self.decomposer(support.SINGLE)
        with patch.object(self.github, "get_issue", side_effect=self._fetches_apart):
            self.tick(later)

        launched, *again = later.launches
        self.assertEqual(again, [])
        self.assertIsNone(launched.resumed, "a fresh conversation, not the correction")
        self.assertIn(_CHANGED, launched.prompt)
        self.assertEqual(self.stage(), support.EXHAUSTED)

    def test_a_begun_split_is_handed_off(self) -> None:
        # The corrected split recorded every child and was lost before the
        # parent's handoff: the next tick's split recovery finalizes it, with
        # no decomposer launched and no park for a human taking its place.
        self.opened()
        self._relabel = self.github.set_workflow_label
        lost = patch.object(self.github, "set_workflow_label", side_effect=self._loses_the_handoff)
        with lost, self.assertRaisesRegex(RuntimeError, _HANDOFF_LOST):
            self.tick(self.decomposer(support.UNLISTED, support.LISTED))
        self.assertEqual(self.children(), support.SLICES)
        self.assertEqual(self.stage(), support.EXHAUSTED)
        later = self.decomposer(support.LISTED)

        self.tick(later)

        self.assertEqual(later.launches, [])
        self.assertEqual(self.label(), _BLOCKED)
        self.assertFalse(self.pinned().get(KEY_AWAITING_HUMAN))

    def test_a_mid_recovery_move_parks_nothing(self) -> None:
        # The record moves while the recovery reads the thread -- onto another
        # cycle during the receipt's read, or a human pinning another session
        # during the issue's last read behind the comment's check: the attempt
        # is no longer this record's to park, no notice is posted, and the
        # recovery's whole-state write never puts the earlier record back.
        for name, during, field, moved_to in _MID_RECOVERY:
            with self.subTest(name):
                self.opened()
                self.tick(self.decomposer(support.UNLISTED, _KILLED))
                self._move = [during, field, moved_to]
                self._read = self.github.comments_after
                with patch.object(self.github, "comments_after", side_effect=self._moves_while_reading):
                    self.tick(self.decomposer(support.SINGLE))

                self.assertEqual(self.pinned().get(field), moved_to, "the record is kept as it was moved")
                self.assertEqual(self.said(), [])
                self.assertFalse(self.pinned().get(KEY_AWAITING_HUMAN))

    def _fetches_apart(self, number: int):
        """The issue as GitHub answers it now: an object apart from the tick's snapshot, carrying the changed body."""
        if number == support.ISSUE_NUMBER:
            return copy.deepcopy(self._current)
        return self._fetch(number)

    def _moves_while_reading(self, *args, **kwargs):
        """The thread read, with the record's field moved while the read it names is out, once."""
        self._move[0] -= 1
        if not self._move[0]:
            reading = self.github.read_pinned_state(self.issue)
            reading.set(self._move[1], self._move[2])
            self.github.write_pinned_state(self.issue, reading)
        return self._read(*args, **kwargs)

    def _loses_the_handoff(self, issue, label):
        """The labeller, lost on the parent's handoff to `workflow:blocked`."""
        if issue.number == support.ISSUE_NUMBER and str(label) == _BLOCKED:
            raise RuntimeError(_HANDOFF_LOST)
        return self._relabel(issue, label)


class RetirementTest(unittest.TestCase, support.CorrectionTickCase):
    """A requirements edit retires the attempt its rejected run left owed before any fresh decomposer is charged.

    The arming's response is lost, so the attempt stands owed and eligible on
    the next tick, whose drift reset -- the body edited -- is the move the
    retirement rests on, written by the retirement itself.
    """

    def test_a_move_before_the_reset_holds(self) -> None:
        # The reset lands only over the comment the retirement read: what a
        # human wrote right before it is kept as written, nothing is launched
        # or charged, and the attempt is neither retired nor replaced.
        for name, field, written in _BEFORE_THE_RESET:
            with self.subTest(name):
                self._owed_behind_an_edit()
                self._move = [field, written]
                self._edit = self.github.edit_pinned_state
                fresh = self.decomposer(support.SINGLE)
                with patch.object(self.github, "edit_pinned_state", side_effect=self._moves_before_the_reset):
                    self.tick(fresh)

                self.assertFalse(self._move, "the reset's edit was reached")
                self.assertEqual(self.pinned()[field], written, "the human's write is kept")
                self.assertEqual((fresh.launches, self.runs()), ([], 1))
                self.assertEqual(self.label(), support.LABEL_DECOMPOSING)

    def test_an_unresolved_attempt_holds(self) -> None:
        # A charge count nobody can read refuses the retirement: the attempt
        # stays pending, and no fresh decomposer is charged behind it, tick
        # after tick, until the count is repaired.
        self._owed_behind_an_edit()
        state = self.github.read_pinned_state(self.issue)
        state.set("agent_runs_used", None)
        self.github.write_pinned_state(self.issue, state)
        fresh = self.decomposer(support.SINGLE)

        self.tick(fresh)
        self.tick(fresh)

        self.assertEqual(fresh.launches, [])
        self.assertEqual(self.stage(), support.PENDING)
        self.assertEqual(self.label(), support.LABEL_DECOMPOSING)

    def test_an_unconfirmed_drop_is_taken_later(self) -> None:
        # A second invalid answer's notice held behind a hold, then a session
        # a human pins in place of the saved one: the retirement lands, and
        # the drop of the notice nothing will post is refused or lands
        # unconfirmed, holding the tick. The next tick drops what is left of
        # it before the fresh decomposition it then makes.
        for name, refused in (("refused", True), ("unconfirmed", False)):
            with self.subTest(name):
                self._retired_behind_a_held_notice(refused=refused)
                fresh = self.decomposer(support.SINGLE)

                self.tick(fresh)

                self.assertNotIn(_HELD_NOTICE, self.pinned(), "the notice is dropped before the run")
                self.assertEqual(len(fresh.launches), 1)
                self.assertEqual(self.label(), LABEL_READY)

    def _retired_behind_a_held_notice(self, *, refused: bool) -> None:
        """A held notice's attempt retired over a human's pin, the notice's drop left unanswered, nothing launched."""
        self.opened()
        with support.OnFetch.patch(self, support.BEHIND_THE_NOTICE, support.CorrectionTickCase.hold):
            self.tick(self.decomposer(support.UNLISTED, support.SELF_EDGE))
        self.lift()
        reading = self.github.read_pinned_state(self.issue)
        reading.set(_SESSION_PIN, _HUMAN_PIN)
        self.github.write_pinned_state(self.issue, reading)
        held = self.decomposer(support.SINGLE)
        with support.CountedEdit.losing(self.github, _THE_DROP, refused=refused):
            self.tick(held)
        self.assertEqual((held.launches, self.stage()), ([], support.RETIRED))

    def _owed_behind_an_edit(self) -> None:
        """An attempt left owed by an arming nobody confirmed, and the issue's body edited behind it."""
        self.opened()
        with support.CountedEdit.losing(self.github, support.ARMING):
            self.tick(self.decomposer(support.UNLISTED))
        self.assertEqual(self.stage(), support.PENDING)
        self.issue.body = _CHANGED

    def _moves_before_the_reset(self, issue, state, **kwargs):
        """The strict editor, with a human's write landing right before the edit carrying the tick's reset, once."""
        attempt = state.get(support.FIELD) or {}
        pending = attempt.get("stage") == support.PENDING
        if self._move and pending and state.get(_SESSION_PIN) is None:
            field, written = self._move
            self._move = []
            reading = self.github.read_pinned_state(issue)
            reading.set(field, written)
            self.github.write_pinned_state(issue, reading)
        return self._edit(issue, state, **kwargs)


if __name__ == "__main__":
    unittest.main()
