# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence a whole recovery keeps the attempt over, proved ready before it holds or parks.

The held-run case (`held_run_support`), its run settled -- or only captured -- and its finish killed: a whole recovery
keeping the attempt over a candidate head nobody could prove, or a stranded park whose notice raised, proves the run
first, so movement retires it whole and putting what moved back routes the head once with nothing current. A newer run
settled right behind -- or, refusing it, ahead of -- the landed road's abandonment of a captured run is proved on its
own readings, a mark of movement the refused edit read under it standing however soon it is put back.
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

    `marks` settles it right ahead, refusing that edit, the mark of movement in its handoff's place (`handoff` kept).
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


class _PutsTheMarkBack(_SettlesBehindTheAbandonment):
    """That race, the newer run's mark of movement put back as the edit it refused returns."""

    def __call__(self, issue, staged, **options):
        """The strict edit and the race around it, the handoff put back behind the first edit the mark refused."""
        marked = self.handoff is None
        answered = super().__call__(issue, staged, **options)
        if marked and self.handoff is not None:
            self._case.puts_back_records({_HANDOFF: self.handoff})
        return answered


class RecoveryHoldProofTest(held.HoldCase, unittest.TestCase):
    """A whole recovery that keeps the attempt over the settled run proves it first, as a direct finish does."""

    def test_an_unproved_head_proves_first(self) -> None:
        # The landed road proves no candidate head, the issue edited: the run is invalidated before the attempt is kept.
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
        # Report 3 settles under the stranded notice, its answer lost: the run is invalidated before the error goes on.
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

    def test_a_successor_is_proved_on_its_own(self) -> None:
        # A newer run settled right behind the abandonment is proved on its own readings, not over that movement.
        for moves_again in (False, True):
            with self.subTest(moved_again=moves_again):
                self.setUp()
                captured = self.captures()[1]
                races = _SettlesBehindTheAbandonment(self, captured, moves_again=moves_again)
                races.recovers()

                self._assert_proved_on_its_own(captured, races.newer, moved=moves_again)

    def test_a_marked_successor_behind_a_refusal(self) -> None:
        # A newer run settling right ahead of the abandonment, refusing it, marked moved -- the mark standing, or put
        # back as the refused edit returns -- is retired on the movement read under its own receipt.
        for race in (_SettlesBehindTheAbandonment, _PutsTheMarkBack):
            with self.subTest(race=race.__name__):
                self.setUp()
                captured = self.captures()[1]
                races = race(self, captured, marks=True)
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
