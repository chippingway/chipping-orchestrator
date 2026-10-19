# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A run the dormant proof before a park retires for good once it finds the checkout gone from disk.

The guarded recovery case (`guarded_recovery_support`): issue #7's run captured, or settled and its finish killed
before its announcement, the recovery context read off the comment handed straight to the dormant proof before a park
(`rewrite_recovery_parks.proves_before_a_park`), or the git owner's abort taken over it. The checkout goes from disk
under one of the proof's own git requests, or a road's (`RecordsALostCheckout`), so that loss is recorded and the run
retired whole however soon it is back; every write refused, the loss stays owed, so the next proof over the checkout
put back still retires the run; with no history room the run and its attempt stand beside the blanked tip until room
is made. A run written back behind its retirement is retired again over the comment read afresh, the proof holding;
and where another road pins a fresh attempt or settles a newer run ahead of the retirement -- at once, or past two
usage writes -- what it wrote stands and the checkout is not reset over it. Nothing is run again, pushed, or launched.
"""
from __future__ import annotations

import copy
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import (
    rewrite_recovery_parks as _parks,
    rewrite_recovery_readings as _readings,
    verification_durable as _durable,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_evidence_test_support as fixtures,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    settled_finish_support as settled_support,
)

_EDITS = "edit_pinned_state"
_CURRENT = "verification_evidence_current"

# Where the checkout goes, and what keeps a retirement over its loss from landing: a refusal, or a full history.
_AWAY = "checkout-away"
_CROWDS = (("refused", False), ("refused", True), ("full", False))

# The usage total another road's write moves, crowding a retirement out of its first askings.
_USAGE_TOTAL = "issue_total_tokens"


def _retires(staged, *, over: dict, **_options) -> bool:
    """Whether a pinned-comment edit retires the run the comment it is decided on carries current."""
    return bool(over.get(_CURRENT)) and not staged.get(_CURRENT)


def _blanks(_issue, staged, *, over: dict, **_options) -> bool:
    """Whether a pinned-comment edit blanks the base tip the comment it is decided on records."""
    tip = readings.KEY_REWRITE_BASE
    return bool(over.get(tip)) and not staged.get(tip)


# The edit blanking the base tip, behind which another road fills the comment to its limit.
_BEHIND_THE_BLANK = handoff.Boundary("behind the blank", _EDITS, _blanks)


class _LostCheckoutCase(guarded.GuardedRecoveryCase):
    """The finish case whose checkout the proof finds gone from disk, put back once that proof answered."""

    def setUp(self) -> None:
        super().setUp()
        self._away = self._wt.parent / _AWAY

    def vanishes_behind(self, live, *asked, **options):
        """`live`, a call, its answer handed back once the checkout is gone from disk."""
        answered = live(*asked, **options)
        if self._wt.is_dir():
            self._wt.rename(self._away)
        return answered

    def assert_retired(self, run, *, captured: bool) -> None:
        """`run` retired whole with the checkout away, and nothing standing for the checkout put back to prove."""
        self.assertFalse(self._wt.is_dir())
        (self.assert_abandoned if captured else self.assert_invalidated)(run)
        self._away.rename(self._wt)
        self.assertTrue(self.proves())
        self.assertEqual(readings.pinned_records(self)[:2], (None, None))


class LostCheckoutTest(_LostCheckoutCase, unittest.TestCase):
    """A checkout the proof finds gone from disk has its run retired, however soon it is back."""

    def test_a_request_inside_the_proof(self) -> None:
        # The checkout goes right behind one of the proof's issue reads, missing for its next git request: that loss is
        # recorded and the run retired rather than the failure raised past it.
        for captures in (False, True):
            with self.subTest(captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                context = guarded.recovery_context(self)
                with patch.object(self.gh, "get_issue", partial(self.vanishes_behind, self.gh.get_issue)):
                    self.assertTrue(_parks.proves_before_a_park(context))
                self.assert_retired(run, captured=captures)

    def test_a_road_records_its_loss(self) -> None:
        # A road's git request finding the checkout gone has that loss recorded and the run retired, the tick's state
        # withheld from any write behind; over a comment with nothing for the head the failure goes on.
        run = self.settles_then_dies()[1]
        context = guarded.recovery_context(self)
        self._wt.rename(self._away)
        with _readings.RecordsALostCheckout(context, _parks.records_the_reset):
            self._git("status", cwd=self._wt)
        self.assertTrue(context.state.withheld)
        self.assert_retired(run, captured=False)
        self._wt.rename(self._away)
        bare = _readings.RecordsALostCheckout(guarded.recovery_context(self), _parks.records_the_reset)
        with self.assertRaises(FileNotFoundError), bare:
            self._git("status", cwd=self._wt)

    def test_a_refused_loss_stays_owed(self) -> None:
        # Every write refused, or a settled run's history full, the run stands beside its attempt; the checkout back on
        # the head, the next proof still takes the loss up and retires it, once room is made where it had none.
        for crowds, captures in _CROWDS:
            with self.subTest(crowds=crowds, captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                self._proves_unrecorded(full=crowds == "full")
                standing = readings.pinned_records(self)[0 if captures else 1]
                anchored = self.pinned_fields(readings.KEY_PENDING_PUSH)
                self.assertEqual((standing, anchored), (run, (self.anchor,)))
                self._away.rename(self._wt)
                self.assertTrue(self.proves())
                (self.assert_abandoned if captures else self.assert_invalidated)(run)

    def test_a_run_written_back_behind(self) -> None:
        # The run and attempt another road writes back right behind the retirement are retired again over the comment
        # read afresh, and the proof holds the tick rather than let a park go on over them.
        run = self.settles_then_dies()[1]
        self._written = copy.deepcopy(readings.pinned(self))
        context = guarded.recovery_context(self)
        self._wt.rename(self._away)
        with patch.object(self.gh, _EDITS, partial(self._writes_back_behind, self.gh.edit_pinned_state)):
            self.assertFalse(_parks.proves_before_a_park(context))
        self.assertIsNone(self._written)
        self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (self.anchor,))
        self.assert_retired(run, captured=False)

    def _proves_unrecorded(self, *, full: bool) -> None:
        """Prove over the checkout gone, every write refused or, where `full`, the history with no room until after."""
        context = guarded.recovery_context(self)
        self._wt.rename(self._away)
        refused = set() if full else {self.issue.number}
        edits = self.gh.edit_pinned_state
        if full:
            edits = _BEHIND_THE_BLANK.moving(edits, partial(moves.fills_the_comment, self))
        refusing = patch.object(self.gh.pinned_failures, "refused", refused)
        with refusing, patch.object(self.gh, _EDITS, edits):
            self.assertFalse(_parks.proves_before_a_park(context))
        if full:
            moves.makes_room(self)

    def _writes_back_behind(self, live, issue, staged, **options):
        """`live`, the pinned-comment edit, the run and its attempt written back right behind the first to retire it."""
        answered = live(issue, staged, **options)
        if answered is PinnedEdit.EDITED and _retires(staged, **options) and self._written:
            state = self.gh.read_pinned_state(issue)
            for field in (*readings.ATTEMPT_KEYS, *_durable._EVIDENCE_RECORDS):
                state.set(field, self._written.get(field))
            self.gh.write_pinned_state(issue, state)
            self._written = None
        return answered


class RacedRetirementTest(_LostCheckoutCase, unittest.TestCase):
    """A run retired over a checkout gone from disk, another road writing right ahead of that retirement."""

    def test_another_road_retires_the_run_ahead(self) -> None:
        # The fetch fails and the checkout goes behind the reset's blank; ahead of the retirement, or its third try past
        # two usage writes, another road pins a fresh attempt or a newer run, the checkout back: what it wrote stands.
        races = (
            ("attempt", self._replaces_the_attempt),
            ("successor", partial(settled_support.records_a_newer_run, settles=True)),
            ("last", partial(self._replaces_the_attempt, spends=2)),
        )
        for race, writes in races:
            with self.subTest(race=race):
                self.setUp()
                self._run = self.settles_then_dies()
                self._onto = self.pinned_fields(readings.KEY_REWRITE_BASE)[0]
                self._blanked = False
                self._written = None
                self._spent = 0
                edits = partial(self._races_the_retirement, writes, self.gh.edit_pinned_state)
                with (
                    patch.object(branch_transport, "_authed_fetch", guarded.unfetched),
                    patch.object(self.gh, _EDITS, edits),
                ):
                    self.recovers()
                self._assert_held_as_written(race)

    def _assert_held_as_written(self, race: str) -> None:
        """What another road wrote ahead of the retirement standing as it wrote it, the checkout left on the head."""
        self.assertTrue(self._blanked and self._written)
        self.assertEqual(self._wt_head(), self._run[0], "the checkout was reset over what another road wrote")
        if race == "successor":
            current = readings.pinned_records(self)[1]
            self.assertEqual(current.receipt, self._written.receipt)
            self.assertEqual(self.pinned_fields(readings.KEY_PENDING_PUSH), (self.anchor,))
        else:
            pinned = self.pinned_fields(*self._written)
            self.assertEqual(pinned, tuple(self._written.values()))
        self.assert_made_once()

    def _races_the_retirement(self, writes, live, issue, staged, **options):
        """`live`, the pinned-comment edit: the checkout gone behind the reset's blank, `writes` ahead of the run's."""
        if self._blanked and self._written is None and _retires(staged, **options):
            self._written = writes(self)
            if self._written is not None:
                self._away.rename(self._wt)
        answered = live(issue, staged, **options)
        tip = readings.KEY_REWRITE_BASE
        blanks = options["over"].get(tip) is not None
        blanks = blanks and staged.get(tip) is None
        if answered is PinnedEdit.EDITED and blanks and not self._blanked:
            self._blanked = True
            self._wt.rename(self._away)
        return answered

    def _replaces_the_attempt(self, _case, spends: int = 0) -> dict | None:
        """Retire the run and pin another attempt, as another road would; it, or None for its first `spends` calls."""
        state = self.gh.read_pinned_state(self.issue)
        if self._spent < spends:
            self._spent += 1
            state.set(_USAGE_TOTAL, (state.get(_USAGE_TOTAL) or 0) + 1)
            self.gh.write_pinned_state(self.issue, state)
            return None
        replacement = fixtures.attempt_record(
            self._run[0], None, git_support.PR_NUMBER, git_support.REVIEWING, self._onto,
        )
        self.assertTrue(_settlement.retire_current_evidence(state))
        _attempts._clears_the_attempt(state)
        for key, member in replacement.items():
            state.set(key, member)
        self.gh.write_pinned_state(self.issue, state)
        return replacement


if __name__ == "__main__":
    unittest.main()
