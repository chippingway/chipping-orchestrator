# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A dormant guarded clear of an attempt whose checkout is back on its anchor: relabelled, or never started.

The guarded recovery case (`guarded_recovery_support`): issue #7's run captured, or settled and its finish killed before
its announcement, then its replay unnamed, the checkout put back on the anchor, and the issue relabelled out of the
refresh's stages. The dispatcher's hold, or the refresh's eligibility gate, clears the attempt, each handed the dormant
clear and the settled-aware retirement it asks first (`rewrite_recovery_parks.lands_a_clear`); so does the unmoved-head
road under the label the run was reviewed in (`replay_cleanup._finish_an_unmoved_head`), the attempt never started.

The write clearing the attempt retires the run with it, so reconciling the head put back revives nothing; a newer run
settling as the clear reads HEAD refuses the clear and keeps its floor; another finish settling the run, or a newer run
marked moved and unmarked, refuses the clear and the move read invalidates it; a usage write refusing the clear has the
reset recorded by base tip; with no history room nothing is cleared, the run current beside its blanked tip. A newer
run and another attempt, or a revision floor raised alone, written right behind a clear that landed hold the tick, its
state withheld from writing over them; usage another road adds there lets either clear go on, laid over that state.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.git.base_sync import replay_cleanup as _replay_cleanup, snapshot as _snapshot
from orchestrator.git.base_sync.models import _AutoRebaseRecoverySnapshot
from orchestrator.git.verification import probes as _probes
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_evidence_test_support as fixtures,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
)

# The checkout's head reading, read before any case stands in for it.
_HEAD_SHA = _probes._head_sha

# The handoff a movement mark takes the place of, the usage total another road's write moves, and the strict edit.
_HANDOFF = "verification_evidence_handoff"
_USAGE = "issue_total_tokens"
_EDITS = "edit_pinned_state"

# How a case resets the checkout, and the undriven label under which the attempt is cleared.
_PUTS_BACK = ("reset", "--quiet", "--hard")
_UNDRIVEN = "workflow:resolving_conflict"

# What clears an attempt under an undriven label: the dispatcher's hold, or the refresh's eligibility gate.
_CLEARS = (
    ("the dispatcher's hold", guarded.answers_a_held_anchor),
    ("the eligibility gate", lambda case: case.recovers()),
)

# The clear's own edit, the first that carries no anchor, behind which another road writes.
_BEHIND_THE_CLEAR = handoff.Boundary(
    "behind the clear", _EDITS, lambda _issue, staged, **_options: not staged.get(readings.KEY_PENDING_PUSH),
)


class _ChargesTheClear:
    """The edit, its first clear raced by a usage write, a finish settling `settles`, or a newer run `marks` moved."""

    def __init__(self, case, settles: str | None = None, *, marks: bool = False) -> None:
        self._case = case
        self._live = case.gh.edit_pinned_state
        self._settles = settles
        self._marks = marks
        self.raced = False
        self.newer = None

    def __call__(self, issue, staged, **options):
        """Answer the edit, the race landing right ahead of the first clear, a mark taken back behind it."""
        if staged.get(readings.KEY_PENDING_PUSH) or self.raced:
            return self._live(issue, staged, **options)
        self.raced = True
        handed = self._races(issue)
        answered = self._live(issue, staged, **options)
        if self._marks:
            self.sets(issue, _HANDOFF, handed)
        return answered

    def sets(self, issue, field: str, member) -> None:
        """Write `field` as `member` on `issue`'s comment, as another road would."""
        fresh = self._case.gh.read_pinned_state(issue)
        fresh.set(field, member)
        self._case.gh.write_pinned_state(issue, fresh)

    def _races(self, issue):
        """Land the race under the label the run was reviewed in; the handoff a mark replaced."""
        case = self._case
        if self._settles is None:
            spent = case.gh.read_pinned_state(issue).get(_USAGE) or 0
            self.sets(issue, _USAGE, spent + 1)
            return None
        case._git(*_PUTS_BACK, self._settles, cwd=case._wt)
        case.issue.labels = [FakeLabel(git_support.REVIEWING)]
        if not self._marks:
            handoff.dies_at(case.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(
                case.finishes, self._settles, FinishRoad.RECOVERY,
            ))
            return None
        self.newer = settled.records_a_newer_run(case, settles=True)
        handed = case.gh.read_pinned_state(issue).get(_HANDOFF)
        self.sets(issue, readings.KEY_EVIDENCE_RECEIPT, self.newer.receipt)
        self.sets(issue, _HANDOFF, {"moved": self.newer.receipt})
        return handed


def _assert_kept(case, newer) -> None:
    """`newer` current on `case`'s comment, the revision floor it raised kept, and the attempt cleared."""
    floor = case.pinned_fields(readings.KEY_REVISION_FLOOR, readings.KEY_PENDING_PUSH)
    kept = (readings.pinned_records(case)[1].receipt, *floor)
    case.assertEqual(kept, (newer.receipt, newer.revision, None))


def _unnames(case) -> None:
    """Blank the replay `case`'s attempt names and put its checkout back on the anchor."""
    state = case.gh.read_pinned_state(case.issue)
    state.set(readings.KEY_REWRITE_SHA, None)
    case.gh.write_pinned_state(case.issue, state)
    case._git(*_PUTS_BACK, case.anchor, cwd=case._wt)


class IneligibleClearTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A guarded clear under a label the refresh does not drive retires the run with the attempt it releases."""

    def test_a_clear_retires_the_run(self) -> None:
        # The write clearing the attempt retires the run; the checkout put back and reconciling revive nothing.
        for (name, clears), captures in product(_CLEARS, (True, False)):
            with self.subTest(cleared_by=name, captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                self._unnamed_on_the_anchor()
                clears(self)
                self._git(*_PUTS_BACK, head, cwd=self._wt)
                self.reconciles()
                self.assertEqual(self.pinned_fields(guarded.AWAITING, readings.KEY_PENDING_PUSH), (None, None))
                (self.assert_abandoned if captures else self.assert_invalidated)(run)

    def test_a_successor_refuses_the_clear(self) -> None:
        # A newer run settling at the HEAD read refuses the clear and keeps its floor; the next clears the attempt.
        for name, clears in _CLEARS:
            with self.subTest(cleared_by=name):
                self.setUp()
                self.settles_then_dies()
                self._unnamed_on_the_anchor()
                newer: list = []
                with patch.object(_probes, "_head_sha", partial(self._settles_on_the_anchor, newer)):
                    clears(self)
                self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (self.anchor,))
                clears(self)
                _assert_kept(self, newer[0])

    def test_a_racing_settlement_is_invalidated(self) -> None:
        # Another finish settling the captured run, or a newer run marked moved then unmarked, refuses the sent clear;
        # the move read invalidates that settlement: the replay named again, the checkout on it, leaves nothing current.
        for marks in (False, True):
            with self.subTest(marked=marks):
                self.setUp()
                head, run = self.settles_then_dies() if marks else self.captures()
                self._unnamed_on_the_anchor()
                racing = _ChargesTheClear(self, settles=head, marks=marks)
                with patch.object(self.gh, _EDITS, racing):
                    guarded.answers_a_held_anchor(self)
                racing.sets(self.issue, readings.KEY_REWRITE_SHA, head)
                self.recovers()
                settlement = getattr(racing.newer, "receipt", run.receipt)
                self.assertIsNone(readings.pinned_records(self)[1])
                self.assertIn((settlement, readings.INVALIDATED), readings.pinned_records(self)[2])

    def test_a_refused_clear_records_the_reset(self) -> None:
        # A usage write refuses the sent clear, the reset recorded by base tip: the checkout put back revives nothing.
        for name, clears in _CLEARS:
            with self.subTest(cleared_by=name):
                self.setUp()
                head, run = self.settles_then_dies()
                self._unnamed_on_the_anchor()
                with patch.object(self.gh, _EDITS, _ChargesTheClear(self)):
                    clears(self)
                fields = (readings.KEY_PENDING_PUSH, readings.KEY_REWRITE_BASE)
                self.assertEqual(self.pinned_fields(*fields), (self.anchor, None))
                self._git(*_PUTS_BACK, head, cwd=self._wt)
                clears(self)
                self.assert_invalidated(run)

    def test_a_full_comment_keeps_the_attempt(self) -> None:
        # No history room: nothing cleared, the run current with its base tip blanked, so later proofs read it moved.
        for name, clears in _CLEARS:
            with self.subTest(cleared_by=name):
                self.setUp()
                run = self.settles_then_dies()[1]
                self._unnamed_on_the_anchor()
                finish_moves.fills_the_comment(self)
                clears(self)
                standing = self.pinned_fields(readings.KEY_PENDING_PUSH, readings.KEY_REWRITE_BASE)
                self.assertEqual(standing, (self.anchor, None))
                self.assertEqual(readings.pinned_records(self)[1], run)

    def _unnamed_on_the_anchor(self) -> None:
        """Blank the replay the attempt names, put the checkout back on the anchor, and relabel out of the refresh."""
        _unnames(self)
        self.issue.labels = [FakeLabel(_UNDRIVEN)]

    def _settles_on_the_anchor(self, newer: list, *called, **options):
        """The checkout's head read, a newer run settled over the run into `newer` the first time it is the anchor."""
        head = _HEAD_SHA(*called, **options)
        if head == self.anchor and not newer:
            newer.append(settled.records_a_newer_run(self, settles=True))
        return head


class WrittenBehindTheClearTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """What another road writes right behind a guarded clear that landed: a record the clear was decided on holds the
    tick, its state withheld, and anything else is laid over that state."""

    def test_a_successor_and_attempt_behind_the_clear(self) -> None:
        # A newer run settles on the run's binding and another attempt is pinned right behind the clear's edit: the
        # clear reads the comment afresh and holds, the tick's state withheld, so writing it whole keeps that newer
        # run, the revision floor it raised, and that attempt.
        head, run = self.settles_then_dies()
        self._binding = run.binding
        self._pinned = fixtures.attempt_record(head, None, git_support.PR_NUMBER, git_support.REVIEWING)
        self._newer = None
        context = self._clears_behind(self._settles_and_pins)
        self.assertTrue(context.state.withheld)
        self.gh.write_pinned_state(self.issue, context.state)
        current = readings.pinned_records(self)[1]
        self.assertEqual(current.receipt, self._newer.receipt)
        kept = self.pinned_fields(readings.KEY_REVISION_FLOOR, *self._pinned)
        self.assertEqual(kept, (self._newer.revision, *self._pinned.values()))

    def test_a_floor_raised_behind_the_clear(self) -> None:
        # Another road raises the revision floor alone right behind the clear's edit: the clear reads it afresh and
        # holds, the tick's state withheld, so writing that state whole lowers no floor.
        floor = self.settles_then_dies()[1].revision + 1
        self._pinned = {readings.KEY_REVISION_FLOOR: floor}
        context = self._clears_behind(self._pins)
        self.assertTrue(context.state.withheld)
        self.gh.write_pinned_state(self.issue, context.state)
        kept = self.pinned_fields(readings.KEY_REVISION_FLOOR, readings.KEY_PENDING_PUSH)
        self.assertEqual(kept, (floor, None))

    def test_usage_behind_either_clear(self) -> None:
        # Another road adds 2 of usage right behind the clear's edit, under an undriven label or over an attempt that
        # never started: nothing the clear was decided on moved, so it goes on, the comment read afresh behind it laid
        # over the tick's state, and writing that state whole keeps the usage beside the attempt cleared.
        for clears in (_snapshot._clear_ineligible_recovery, _snapshot._clear_unchanged_recovery):
            with self.subTest(clears=clears.__name__):
                self.setUp()
                self.settles_then_dies()
                counted = self.pinned_fields(_USAGE)[0] or 0
                self._pinned = {_USAGE: counted + 2}
                context = self._clears_behind(self._pins, clears)
                self.assertFalse(context.state.withheld)
                self.gh.write_pinned_state(self.issue, context.state)
                kept = self.pinned_fields(_USAGE, readings.KEY_PENDING_PUSH)
                self.assertEqual(kept, (self._pinned[_USAGE], None))

    def _clears_behind(self, writes, clears=_snapshot._clear_ineligible_recovery):
        """Clear the attempt unnamed on its anchor by `clears`, guarded, `writes` made right behind the clear's edit;
        its state."""
        _unnames(self)
        context = guarded.recovery_context(self)
        with patch.object(self.gh, _EDITS, _BEHIND_THE_CLEAR.moving(self.gh.edit_pinned_state, writes)):
            clears(context)
        return context

    def _settles_and_pins(self) -> None:
        """Settle a newer run on the run's binding, then pin `_pinned` over it, as another road would."""
        self._newer = settled.records_a_newer_run(self, settles=True, binding=self._binding)
        self._pins()

    def _pins(self) -> None:
        """Write each of `_pinned` over the comment as it stands, as another road would."""
        fresh = self.gh.read_pinned_state(self.issue)
        for key, pinned in self._pinned.items():
            fresh.set(key, pinned)
        self.gh.write_pinned_state(self.issue, fresh)


class UnmovedClearTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A guarded clear of an attempt that never started, its checkout on the anchor, retires the run it releases."""

    def test_a_clear_retires_the_run(self) -> None:
        # The write clearing the attempt retires a captured or settled run with it, and the ordinary rebase goes on:
        # the checkout put back and reconciling revive nothing.
        for captures in (True, False):
            with self.subTest(captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                self.assertFalse(self._clears())
                self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (None,))
                self._git(*_PUTS_BACK, head, cwd=self._wt)
                self.reconciles()
                (self.assert_abandoned if captures else self.assert_invalidated)(run)

    def test_a_full_comment_keeps_the_attempt(self) -> None:
        # No history room: nothing cleared and the tick held, the run current with its base tip blanked.
        run = self.settles_then_dies()[1]
        self.assertTrue(self._clears(full=True))
        standing = self.pinned_fields(readings.KEY_PENDING_PUSH, readings.KEY_REWRITE_BASE)
        self.assertEqual(standing, (self.anchor, None))
        self.assertEqual(readings.pinned_records(self)[1], run)

    def _clears(self, *, full: bool = False) -> bool:
        """The unmoved-head road over the attempt unnamed on its anchor -- the comment filled to its limit where `full`
        -- handed the dormant guarded clear; whether it holds the tick."""
        _unnames(self)
        if full:
            finish_moves.fills_the_comment(self)
        observed = _AutoRebaseRecoverySnapshot(branch=self.pull_request.head_branch, local_head=self.anchor)
        return _replay_cleanup._finish_an_unmoved_head(guarded.recovery_context(self), observed)


if __name__ == "__main__":
    unittest.main()
