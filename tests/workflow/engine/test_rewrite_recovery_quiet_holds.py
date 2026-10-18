# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An anchor the dispatcher holds with nothing parked or posted, proving the run it keeps first.

On the real-git finish case, its run captured or settled and the finish killed, a hold posting nothing proves the run
first (`git/base_sync/persistence._proves_before_the_park`) -- under a label the refresh drives, or beside its own
stranded park standing: an issue edited and put back has it retired whole, the next recovery routing the head, nothing
current. A run another finish settles mid-proof is invalidated too, or recorded by its base tip in a full comment; a
newer run settled over it is kept. A clear under a label the refresh does not drive, over a checkout back on the anchor,
retires the run in the guarded write clearing the attempt, keeps the attempt where history has no room, and a newer run
settled meanwhile refuses it; one a usage write refuses records the reset by base tip. Nothing is run again or pushed.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.git.verification import probes as _probes
from orchestrator.workflow.engine import verification_durable as _durable
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    settled_finish_support as settled,
)
from tests.workflow.interleaving import _RacesTheStep

_EDITED_BODY = "Also cover a base that moved twice."

# The checkout's head reading, read before any case stands in for it.
_HEAD_SHA = _probes._head_sha

# A label the refresh does not drive, under which the dispatcher's hold strands the attempt.
_UNDRIVEN = "workflow:resolving_conflict"


def _strands(case) -> None:
    """Relabel `case`'s issue out of the refresh's stages and have the dispatcher's hold take its stranded park."""
    case.issue.labels = [FakeLabel(_UNDRIVEN)]
    guarded.answers_a_held_anchor(case)
    case.assertTrue(case.pinned_fields(guarded.AWAITING)[0])


def _puts_the_label_back(case) -> None:
    """Put `case`'s issue back on the stage it was reviewed in and reply to the park."""
    case.issue.labels = [FakeLabel(git_support.REVIEWING)]
    case.continues()


class _ChargesTheClear:
    """`case`'s pinned-comment edit, behind a usage write landed first the first time it sends the clear."""

    def __init__(self, case) -> None:
        self._gh = case.gh
        self._live = case.gh.edit_pinned_state
        self.raced = False

    def __call__(self, issue, staged, **options):
        """Answer the edit, a usage write landing right ahead of the clear the first time."""
        if not staged.get(readings.KEY_PENDING_PUSH) and not self.raced:
            self.raced = True
            fresh = self._gh.read_pinned_state(issue)
            fresh.set("issue_total_tokens", (fresh.get("issue_total_tokens") or 0) + 1)
            self._gh.write_pinned_state(issue, fresh)
        return self._live(issue, staged, **options)


# What answers an anchor under an undriven label: the dispatcher's hold, or a whole refresh's eligibility gate.
_CLEARS = (
    ("the dispatcher's hold", guarded.answers_a_held_anchor),
    ("the eligibility gate", lambda case: case.recovers()),
)


class _Road(NamedTuple):
    """Where the dispatcher's quiet hold stands: what brings it there, and what releases the anchor after it."""

    name: str
    stands: Callable
    releases: Callable


_ROADS = (
    _Road("a label the refresh drives", lambda _case: None, lambda _case: None),
    _Road("a stranded park already standing", _strands, _puts_the_label_back),
)


class QuietHoldProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A hold that posts nothing proves the run it keeps, so restoring what moved revives nothing."""

    def test_a_quiet_hold_proves_the_run(self) -> None:
        # The run, captured or settled, is retired whole by the hold that read the edit, with the attempt kept and
        # nothing posted; the head is then routed once with nothing current.
        for road, captures in product(_ROADS, (True, False)):
            with self.subTest(road=road.name, captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                self._holds_over_an_edit(road)

                self._assert_retired(run, captured=captures)
                road.releases(self)
                self.recovers()

                self.assert_routed(head)

    def _holds_over_an_edit(self, road: _Road) -> None:
        """Bring the hold to `road`; the dispatcher holds its anchor over an issue edit put back, posting nothing."""
        road.stands(self)
        noticed = len(self.gh.posted_comments)
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        guarded.answers_a_held_anchor(self)
        self.issue.body = written
        self.assertEqual(len(self.gh.posted_comments), noticed)

    def _assert_retired(self, run, *, captured: bool) -> None:
        """`run` abandoned whole where it was only `captured`, else invalidated whole, the attempt on its anchor."""
        self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH)[0], self.anchor)
        if captured:
            self.assert_abandoned(run)
        else:
            self.assert_invalidated(run)


class SettledUnderTheProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A captured run another finish settles while the stranded park's proof abandons it over an edited issue."""

    def test_the_settled_run_is_invalidated(self) -> None:
        # The park is taken over the run invalidated whole, and continued, routes the head with nothing current.
        head, captured = self._holds_over_a_settlement()
        self.assertTrue(self.pinned_fields(guarded.AWAITING)[0])
        self.assert_invalidated(captured)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.continues()
        self.recovers()
        self.assert_routed(head)

    def test_a_full_comment_records_the_movement(self) -> None:
        # No room for the invalidation: the tip is blanked, nothing parked, and the room freed takes it asked again.
        head, captured = self._holds_over_a_settlement(finish_moves.fills_the_comment)
        self.assertEqual(self.pinned_fields(guarded.AWAITING, readings.KEY_REWRITE_BASE), (None, None))
        current, retired = readings.pinned_records(self)[1:]
        invalidated = (captured.receipt, readings.INVALIDATED)
        self.assertEqual((current, retired[-1]), (None, invalidated))
        finish_moves.makes_room(self)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]
        self.recovers()
        self.assert_routed(head)

    def test_a_successor_settled_meanwhile_is_kept(self) -> None:
        # The newer run stays current, the captured one superseded as that road left it, and nothing is parked.
        captured = self._holds_over_a_settlement(partial(settled.records_a_newer_run, settles=True))[1]
        current, retired = readings.pinned_records(self)[1:]
        self.assertNotEqual(current.receipt, captured.receipt)
        self.assertEqual(retired[-1], (captured.receipt, "superseded"))
        self.assertIsNone(self.pinned_fields(guarded.AWAITING)[0])

    def _holds_over_a_settlement(self, then=None) -> tuple:
        """Capture a run, edit the issue, and strand the attempt while another finish settles it; head and run."""
        head, captured = self.captures()
        written = self.issue.body
        self.issue.body = _EDITED_BODY
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        raced: list = []
        elsewhere = partial(guarded.settles_elsewhere, self, head, written, raced, then)
        with patch.object(_durable, "durable_comment", _RacesTheStep(_durable.durable_comment, elsewhere)):
            guarded.answers_a_held_anchor(self)
        self.assertEqual(raced, [head])
        return head, captured


class IneligibleClearTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A clear under a label the refresh does not drive retires the run with the attempt it releases."""

    def test_a_clear_retires_the_run(self) -> None:
        # The run, captured or settled, is retired whole in the write that clears the attempt, so the checkout put
        # back on the landed head and the reconciliation revive nothing.
        for (name, clears), captures in product(_CLEARS, (True, False)):
            with self.subTest(cleared_by=name, captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                self._unnamed_on_the_anchor()
                clears(self)
                self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
                self.reconciles()

                self.assertEqual(self.pinned_fields(guarded.AWAITING, readings.KEY_PENDING_PUSH), (None, None))
                if captures:
                    self.assert_abandoned(run)
                else:
                    self.assert_invalidated(run)

    def test_a_successor_refuses_the_clear(self) -> None:
        # A newer run settles while the checkout's head is read: the clear is refused, the newer run kept with its
        # revision floor, and the next answer clears the attempt beside it.
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
                self._assert_kept_beside_a_clear(newer[0])

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
                self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
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
        self._git("reset", "--quiet", "--hard", self.anchor, cwd=self._wt)
        self.issue.labels = [FakeLabel(_UNDRIVEN)]

    def _assert_kept_beside_a_clear(self, newer) -> None:
        """`newer` current with the revision floor it raised, the attempt cleared beside it."""
        current = readings.pinned_records(self)[1].receipt
        floor, anchored = self.pinned_fields(readings.KEY_REVISION_FLOOR, readings.KEY_PENDING_PUSH)
        self.assertEqual((current, floor, anchored), (newer.receipt, newer.revision, None))

    def _settles_on_the_anchor(self, newer: list, *called, **options):
        """The checkout's head read, a newer run settled over the run into `newer` the first time it is the anchor."""
        head = _HEAD_SHA(*called, **options)
        if head == self.anchor and not newer:
            newer.append(settled.records_a_newer_run(self, settles=True))
        return head


if __name__ == "__main__":
    unittest.main()
