# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A dormant guarded clear of an attempt under a label the refresh does not drive, the checkout back on its anchor.

The guarded recovery case (`guarded_recovery_support`): issue #7's run captured, or settled and its finish killed before
its announcement, then its replay unnamed, the checkout put back on the anchor, and the issue relabelled out of the
refresh's stages. The dispatcher's hold, or the refresh's eligibility gate, clears the attempt, each handed the dormant
clear and the settled-aware retirement it asks first (`rewrite_recovery_parks.lands_a_clear`).

The write clearing the attempt retires the run with it, so reconciling the head put back revives nothing; a newer run
settling as the clear reads HEAD refuses the clear and keeps its floor; another finish settling the run, or a newer run
marked moved and unmarked, refuses the clear and the move read invalidates it; a usage write refusing the clear has the
reset recorded by base tip; with no history room nothing is cleared, the run current beside its blanked tip.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.git.verification import probes as _probes
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
)

# The checkout's head reading, read before any case stands in for it.
_HEAD_SHA = _probes._head_sha

# The handoff a movement mark takes the place of, and the usage total another road's write moves.
_HANDOFF = "verification_evidence_handoff"
_USAGE = "issue_total_tokens"

# How a case resets the checkout, and the undriven label under which the attempt is cleared.
_PUTS_BACK = ("reset", "--quiet", "--hard")
_UNDRIVEN = "workflow:resolving_conflict"

# What clears an attempt under an undriven label: the dispatcher's hold, or the refresh's eligibility gate.
_CLEARS = (
    ("the dispatcher's hold", guarded.answers_a_held_anchor),
    ("the eligibility gate", lambda case: case.recovers()),
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
                with patch.object(self.gh, "edit_pinned_state", racing):
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
                with patch.object(self.gh, "edit_pinned_state", _ChargesTheClear(self)):
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
        state = self.gh.read_pinned_state(self.issue)
        state.set(readings.KEY_REWRITE_SHA, None)
        self.gh.write_pinned_state(self.issue, state)
        self._git(*_PUTS_BACK, self.anchor, cwd=self._wt)
        self.issue.labels = [FakeLabel(_UNDRIVEN)]

    def _settles_on_the_anchor(self, newer: list, *called, **options):
        """The checkout's head read, a newer run settled over the run into `newer` the first time it is the anchor."""
        head = _HEAD_SHA(*called, **options)
        if head == self.anchor and not newer:
            newer.append(settled.records_a_newer_run(self, settles=True))
        return head


if __name__ == "__main__":
    unittest.main()
