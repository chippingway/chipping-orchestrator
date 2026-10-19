# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""An anchor the dispatcher holds with nothing parked or posted, proving the run it keeps first.

A hold posting nothing over the real-git finish case's captured or settled run, its finish killed, proves the run first
(`git/base_sync/persistence._proves_before_the_park`), under a driven label or beside its standing stranded park: an
edited issue put back retires it whole, the head then routed with nothing current. A run settled mid-proof is
invalidated, or recorded by base tip in a full comment; a newer run over it is kept. An undriven clear over a checkout
back on the anchor retires the run as it clears the attempt, keeps the attempt with no history room, yields to a newer
run, and records the reset by base tip if a usage write refuses it. Nothing is run again or pushed.
"""
from __future__ import annotations

import unittest
from collections.abc import Callable
from functools import partial
from itertools import product
from typing import NamedTuple
from unittest.mock import patch

from orchestrator.git.verification import probes as _probes
from orchestrator.workflow.engine import rewrite_recovery_readings as _readings, verification_durable as _durable
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled,
)
from tests.workflow.interleaving import _RacesTheStep

_EDITED_BODY = "Also cover a base that moved twice."

# The checkout's head reading, read before any case stands in for it.
_HEAD_SHA = _probes._head_sha

# The checkout leaves behind the proof's issue read or reading client, back at that loss's reading or the block's end.
_BEHIND_A_READ = handoff.Boundary("behind an issue read", "get_issue", lambda *_called: True)

_EXITS = "__exit__"

_AT_ITS_LOSS = handoff.Boundary("at its loss", _EXITS, lambda _held, kind, *_rest: kind is FileNotFoundError)

_BEHIND_THE_CLIENT = handoff.Boundary("behind the proof's client", "asks_every_reading", lambda *_called: True)

_BEHIND_THE_BLOCK = handoff.Boundary("behind the proof's block", _EXITS, lambda *_called: True)

# The handoff a movement mark takes the place of, and the usage total another road's write moves.
_HANDOFF = "verification_evidence_handoff"

_USAGE = "issue_total_tokens"

# How a case resets the checkout, and the undriven label under which the dispatcher's hold strands the attempt.
_PUTS_BACK = ("reset", "--quiet", "--hard")

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
        handoff = self._races(issue)
        answered = self._live(issue, staged, **options)
        if self._marks:
            self.sets(issue, _HANDOFF, handoff)
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
            return guarded.settles_elsewhere(case, self._settles, case.issue.body, [])
        self.newer = settled.records_a_newer_run(case, settles=True)
        handoff = case.gh.read_pinned_state(issue).get(_HANDOFF)
        self.sets(issue, readings.KEY_EVIDENCE_RECEIPT, self.newer.receipt)
        self.sets(issue, _HANDOFF, {"moved": self.newer.receipt})
        return handoff


# The dispatcher's hold of an anchor, and what answers one under an undriven label: that hold or the eligibility gate.
_HOLDS = guarded.answers_a_held_anchor

_CLEARS = (
    ("the dispatcher's hold", guarded.answers_a_held_anchor),
    ("the eligibility gate", lambda case: case.recovers()),
)


class _Road(NamedTuple):
    """Where the dispatcher's quiet hold stands: what brings it there, what releases the anchor, whether it edits."""

    name: str
    stands: Callable
    releases: Callable
    edits: bool = True


_ROADS = (
    _Road("a label the refresh drives", lambda _case: None, lambda _case: None),
    _Road("a stranded park already standing", _strands, _puts_the_label_back),
    _Road(
        "a checkout gone from disk, brought back",
        lambda case: case._git(
            "worktree", "remove", "--force", str(case._wt), cwd=case._work,
        ),
        lambda _case: None,
        edits=False,
    ),
)


class QuietHoldProofTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A hold that posts nothing proves the run it keeps, so restoring what moved revives nothing."""

    def test_a_quiet_hold_proves_the_run(self) -> None:
        # The hold reading the edit, or the checkout gone before it brings it back, retires the run and posts nothing.
        for road, captures in product(_ROADS, (True, False)):
            with self.subTest(road=road.name, captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                self._holds_over_an_edit(road)

                self._assert_retired(run, captured=captures)
                road.releases(self)
                self.recovers()

                self.assert_routed(head)

    def test_a_refused_record_keeps_the_checkout_away(self) -> None:
        # Every write refused, nothing restores the checkout; the next hold retires the run before bringing it back.
        head, run = self.settles_then_dies()
        _ROADS[-1].stands(self)
        with patch.object(self.gh.pinned_failures, "refused", {self.issue.number}):
            guarded.answers_a_held_anchor(self)
        self.assertFalse(self._wt.is_dir())
        self.assertEqual(readings.pinned_records(self)[1], run)
        guarded.answers_a_held_anchor(self)
        self._assert_retired(run, captured=False)
        self.assertTrue(self._wt.is_dir())
        self.recovers()
        self.assert_routed(head)

    def test_a_checkout_back_under_a_refused_record(self) -> None:
        # The checkout returns as the hold's reset record goes out refused; the loss it was asked over abandons the run.
        head, run = self.captures()
        away = self._wt.parent / guarded.AWAY
        self._wt.rename(away)
        edits = partial(guarded.returns_under_the_blank, self, self.gh.edit_pinned_state)
        with patch.object(self.gh, "edit_pinned_state", edits):
            guarded.answers_a_held_anchor(self)
        self._assert_retired(run, captured=True)
        self.recovers()
        self.assert_routed(head)

    def test_a_loss_the_proof_read_retires_the_run(self) -> None:
        # The checkout goes behind a proof's issue read and returns as that loss is read: the run is still invalidated.
        head, kept = self.settles_then_dies()
        away = self._wt.parent / guarded.AWAY
        vanishes = _BEHIND_A_READ.moving(self.gh.get_issue, partial(self._wt.rename, away))
        exits = _AT_ITS_LOSS.moving(_readings.LosesTheCheckout.__exit__, partial(away.rename, self._wt))
        with (
            patch.object(self.gh, "get_issue", vanishes),
            patch.object(_readings.LosesTheCheckout, _EXITS, autospec=True, side_effect=exits),
        ):
            _HOLDS(self)
        self.assertTrue(self._wt.is_dir())
        self._assert_retired(kept, captured=False)
        self.recovers()
        self.assert_routed(head)

    def test_a_directory_read_gone_retires_the_run(self) -> None:
        # The proof reads the checkout gone at its directory check, back before any later read: still invalidated whole.
        head, kept = self.settles_then_dies()
        away = self._wt.parent / guarded.AWAY
        vanishes = _BEHIND_THE_CLIENT.moving(_readings.asks_every_reading, partial(self._wt.rename, away))
        exits = _BEHIND_THE_BLOCK.moving(_readings.LosesTheCheckout.__exit__, partial(away.rename, self._wt))
        with (
            patch("orchestrator.workflow.engine.rewrite_landing_retirement.asks_every_reading", vanishes),
            patch.object(_readings.LosesTheCheckout, _EXITS, autospec=True, side_effect=exits),
        ):
            _HOLDS(self)
        self.assertTrue(self._wt.is_dir())
        self._assert_retired(kept, captured=False)
        self.recovers()
        self.assert_routed(head)

    def _holds_over_an_edit(self, road: _Road) -> None:
        """Bring the hold to `road`; the dispatcher holds its anchor over any edit it makes, put back, posting none."""
        road.stands(self)
        noticed = len(self.gh.posted_comments)
        written = self.issue.body
        self.issue.body = _EDITED_BODY if road.edits else written
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
                if captures:
                    self.assert_abandoned(run)
                else:
                    self.assert_invalidated(run)

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
                kept = (
                    readings.pinned_records(self)[1].receipt,
                    *self.pinned_fields(readings.KEY_REVISION_FLOOR, readings.KEY_PENDING_PUSH),
                )
                expected = newer[0]
                self.assertEqual(kept, (expected.receipt, expected.revision, None))

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
