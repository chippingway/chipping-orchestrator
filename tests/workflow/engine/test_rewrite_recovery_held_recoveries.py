# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence a whole recovery keeps the attempt over, proved ready before it holds, parks, or stops.

The held-run case (`held_run_support`), its run settled -- or only captured --
and its finish killed: a whole recovery that keeps the attempt over a candidate
head nobody could prove, a stranded park whose notice raised, or a debt park
with no room proves the run first, so movement retires it whole and putting
what moved back routes the head once with nothing current. A newer run
settled right behind -- or, refusing it, ahead of -- the landed road's
abandonment of a captured run is proved on its own readings.
"""
from __future__ import annotations

import unittest
from dataclasses import replace
from functools import partial
from unittest.mock import patch

from orchestrator.git.base_sync import rewrite_facts
from orchestrator.git.publication.probes import _BranchDivergence
from orchestrator.github.pinned_state import PinnedEdit
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    held_run_support as held,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
    settled_finish_support as settled,
)

# The evidence handoff's place on the pinned comment.
_HANDOFF = "verification_evidence_handoff"


def _unproved_first(original, calls: list, *args):
    """Answer `original`, its first reading proving no head, as a failed head proof reads."""
    reading = original(*args)
    calls.append(reading)
    if len(calls) > 1:
        return reading
    return replace(reading, head="", tree="", base=_BranchDivergence())


class _SettlesBehindTheAbandonment:
    """The checkout read off its head once, and `newer` settled right behind the edit abandoning `captured`.

    `marks` settles it right ahead of that edit instead, refusing it, the mark
    of movement in its handoff's place (`handoff` kept).
    """

    def __init__(self, case, captured, *, moves_again: bool = False, marks: bool = False) -> None:
        self._case = case
        self._captured = captured
        self._moves_again = moves_again
        self._marks = marks
        self._head = case._wt_head()
        self._edits = case.gh.edit_pinned_state
        self._reads = rewrite_facts._reads_the_checkout
        self.newer = None
        self.handoff = None

    def __call__(self, issue, staged, **options):
        """The strict edit, a newer run settled right behind -- or ahead of -- the one abandoning the captured run."""
        retired = readings.records(staged.data)[2]
        abandoning = (self._captured.receipt, readings.ABANDONED) in retired
        abandoning = abandoning and self.newer is None
        if abandoning and self._marks:
            self._settles()
        answered = self._edits(issue, staged, **options)
        if abandoning and not self._marks and answered is PinnedEdit.EDITED:
            self._settles()
        return answered

    def recovers(self) -> None:
        """One whole recovery of the case, its checkout read and its comment edited through this race."""
        with (
            patch.object(rewrite_facts, "_reads_the_checkout", self.reads),
            patch.object(self._case.gh, "edit_pinned_state", self),
        ):
            self._case.recovers()

    def reads(self, *read):
        """The checkout's reading, a stray commit made on it the first time."""
        if self.newer is None and self._case._wt_head() == self._head:
            self._case._git(*support.STRAY_COMMIT, cwd=self._case._wt)
        return self._reads(*read)

    def _settles(self) -> None:
        """Put the checkout back, settle `newer` -- marked moved where `marks` -- and move the checkout again."""
        case = self._case
        case._git("reset", "--quiet", "--hard", self._head, cwd=case._wt)
        self.newer = settled.records_a_newer_run(case, settles=True, binding=self._captured.binding)
        if self._marks:
            state = case.gh.read_pinned_state(case.issue)
            self.handoff = state.get(_HANDOFF)
            state.set(_HANDOFF, {"moved": self.newer.receipt})
            case.gh.write_pinned_state(case.issue, state)
        if self._moves_again:
            case._git(*support.STRAY_COMMIT, cwd=case._wt)


class RecoveryHoldProofTest(held.HoldCase, unittest.TestCase):
    """A whole recovery that keeps the attempt over the settled run proves it first, as a direct finish does."""

    def test_an_unproved_head_proves_first(self) -> None:
        # The landed road cannot prove the candidate's head, so it finishes
        # nothing, and the issue was edited: the run is invalidated before the
        # attempt is kept, and with the issue and the reading back the head is
        # routed with nothing current.
        head = self.settles_then_dies()
        written = self.issue.body
        self.issue.body = held.EDITED_BODY
        unproved = partial(_unproved_first, rewrite_facts._reads_the_checkout, [])
        with patch.object(rewrite_facts, "_reads_the_checkout", side_effect=unproved):
            self.recovers()

        self.assert_invalidated(standing=self.anchor)
        self.issue.body = written
        self.recovers()

        self.assert_invalidated(standing=None)
        self.assert_routed_once(head)

    def test_a_raised_stranded_notice_proves(self) -> None:
        # The issue is relabelled out from under the attempt, and while the
        # stranded park's notice is posted report 3 of the head is settled
        # and the post's answer lost: the run is invalidated before the error
        # goes on, so report 2 and the label put back route the head with
        # nothing current.
        head = self.settles_then_dies()
        self.issue.labels = [FakeLabel("workflow:resolving_conflict")]
        replaced = self.settles_under_the_notice(head, raises=True, recovered=True)

        self.assert_invalidated(standing=self.anchor)
        self.assertFalse(readings.pinned(self).get("awaiting_human"))
        self.puts_back_records(replaced)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.recovers()

        self.assert_invalidated(standing=None)
        self.assert_routed_once(head)

    def test_a_debt_park_notice_proves_the_run(self) -> None:
        # The finish's own debt park, reached by a whole recovery: report 3
        # settled while its notice is posted, refused or raising, invalidates
        # the run before the recovery stops, and the next one routes the head
        # with nothing current once room is made.
        for raises in (False, True):
            with self.subTest(raised=raises):
                self.setUp()
                head = self.settles_then_dies()
                finish_moves.fills_the_comment(self, held.SHORT_OF_THE_DEBT)
                replaced = self.settles_under_the_notice(head, raises=raises, recovered=True)

                self.assert_invalidated(standing=self.anchor)
                self.puts_back_records(replaced)
                finish_moves.makes_room(self)
                self.recovers()

                self.assert_invalidated(standing=None)
                self.assert_routed_once(head)

    def test_a_debt_park_abandons_a_captured_run(self) -> None:
        # The run only captured, the debt park's record refused over report 3
        # with report 2 put back right behind that refusal: a whole recovery
        # abandons the run, and the next one routes the head once room is made.
        head, captured = self.captures()
        finish_moves.fills_the_comment(self, held.SHORT_OF_THE_DEBT)
        self.puts_back_records(self.settles_under_the_notice(head, raises=False, restores=True, recovered=True))

        self.assert_abandoned(captured)
        finish_moves.makes_room(self)
        self.recovers()
        self.assert_abandoned(captured)
        self.assert_routed_once(head)

    def test_a_successor_is_proved_on_its_own(self) -> None:
        # The landed road reads the checkout off the captured run's head and
        # abandons the run; a newer run settled right behind that write is
        # proved on its own readings, not over that movement: kept current
        # over the checkout back on the head, invalidated over one moved again.
        for moves_again in (False, True):
            with self.subTest(moved_again=moves_again):
                self.setUp()
                captured = self.captures()[1]
                races = _SettlesBehindTheAbandonment(self, captured, moves_again=moves_again)
                races.recovers()

                self._assert_proved_on_its_own(captured, races.newer, moved=moves_again)

    def test_a_marked_successor_behind_a_refusal(self) -> None:
        # The newer run settles right ahead of the abandonment, refusing it,
        # marked moved: the recovery reads it afresh behind that refusal and
        # retires it whole, so its handoff put back routes nothing current.
        captured = self.captures()[1]
        races = _SettlesBehindTheAbandonment(self, captured, marks=True)
        races.recovers()
        self.puts_back_records({_HANDOFF: races.handoff})
        self.recovers()

        self._assert_proved_on_its_own(captured, races.newer, moved=True)

    def _assert_proved_on_its_own(self, captured, newer, *, moved: bool) -> None:
        """`captured` abandoned, and `newer` current -- or, where the checkout `moved` again, invalidated behind it."""
        current, retired = readings.pinned_records(self)[1:]
        expected = [(captured.receipt, readings.ABANDONED)]
        if moved:
            expected.append((newer.receipt, readings.INVALIDATED))
        kept = None if moved else newer.receipt
        standing = getattr(current, "receipt", None)
        self.assertEqual(retired[-len(expected):], tuple(expected))
        self.assertEqual(standing, kept)

if __name__ == "__main__":
    unittest.main()
