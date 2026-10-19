# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A checkout gone from disk under a dormant guarded park or hold, its settled run's movement recorded around it.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. Then the checkout goes from disk and the issue is
relabelled to a stage the refresh does not drive, so the dispatcher's anchor
hold answers it with the stranded park that keeps the attempt -- handed the
workflow's dormant proof and park (`guarded_recovery_support`), which no
production road hands it yet.

With no checkout there is nothing to prove the landing over, so the movement
is recorded against the run first, by blanking the base tip the attempt
recorded its replay as made onto in a write of its own, and the run retired
whole in another ahead of the park's record: a park record GitHub refuses, or
a process killed before it, leaves nothing current for the head put back to
route. A checkout a caller read gone, or the proof read gone itself, back
before the proof or its record reads it again, is retired over all the same.

The dormant guarded hold a publication gate's hold of a recovery's push would
be recorded through takes that proof too, so with the checkout gone the reset
is recorded ahead of the hold's record, and a hold record GitHub refuses
leaves the run read moving once the checkout is back. A checkout that goes
from disk only as a hold's or a park's record lands, or as a park's notice
raises, leaves nothing behind it to prove the run over, so the reset is
recorded against the run there instead. A record of that retirement refused,
or cut short, leaves the run read moving once the checkout is back. Nothing is
run again, pushed, or launched, nor announced or relabelled before a route.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.workflow.engine import rewrite_recovery_parks as _parks
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
)

# A label the refresh does not drive, under which the dispatcher's hold strands the attempt.
_UNDRIVEN = "workflow:resolving_conflict"

_AWAY = "checkout-away"

# The client step a pinned-comment edit is.
_EDITS = "edit_pinned_state"

# How a record never lands: GitHub refuses it, or the process is killed before it.
_KILLED = "killed"
_NEVER_LANDS = ("refused", _KILLED)

# The park a case hands the dormant guarded park, and why.
_NOTICE = "The auto rebase needs a human."
_REASON = "auto_base_rebase_push_failed"

# A record a publication gate staged for the hold to land, as one holding over a reading of its own does.
_GATE = "late_gate_hold"


def _refuses_the_park(refused: set, live, issue, state, **options):
    """`live`, the client's pinned-comment edit, refused by GitHub where it is a park's record."""
    if guarded.parking(issue, state, **options):
        refused.add(issue.number)
    answered = live(issue, state, **options)
    refused.discard(issue.number)
    return answered


def _records(_issue, state, **options) -> bool:
    """Whether a pinned-comment edit is a hold's or a park's record, rather than the blank of the attempt's base tip."""
    tip = readings.KEY_REWRITE_BASE
    read = options["over"].get(tip)
    return read is None or state.get(tip) is not None


def _refuses_the_record(refused: set, live, issue, state, **options):
    """`live`, the client's pinned-comment edit, refused by GitHub where it is a hold's or a park's record."""
    if _records(issue, state, **options):
        refused.add(issue.number)
    answered = live(issue, state, **options)
    refused.discard(issue.number)
    return answered


# A hold's or a park's record: the process killed before it, or the checkout going from disk right behind it.
_AT_THE_RECORD = handoff.Boundary("at the record", _EDITS, _records)

# The proof's staging guard, the checkout put back right behind it, before the proof reads the directory itself; and
# any step's first call, a move made right ahead of it or behind.
_AHEAD_OF_THE_PROOF = handoff.Boundary("ahead of the proof", "keeps_the_staging", lambda *_called, **_options: True)
_FIRST_CALL = handoff.Boundary("at the first call", "", lambda *_called, **_options: True)


def _raises_behind(move, *_posted, **_options):
    """The issue-thread post of a park's notice, `move` made and then a raise as GitHub not answering."""
    move()
    raise RuntimeError("GitHub did not answer the notice's post")


class MissingCheckoutTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A checkout gone from disk has the movement recorded against the run before the stranded park retires it."""

    def test_a_landed_park_retires_the_run(self) -> None:
        # The stranded park keeps the attempt and lands the run's
        # invalidation in its own record, over the tip already blanked.
        settled = self._settles_then_strands()
        guarded.answers_a_held_anchor(self)
        self._returns()

        standing = self.pinned_fields(*guarded.ATTEMPT_FIELDS)
        self.assertEqual(standing, (True, self.anchor, None))
        self.assert_invalidated(settled)

    def test_a_park_that_never_lands(self) -> None:
        # The stranded park's record is refused, or the process is killed
        # ahead of it: the run, retired first in a write of its own beside
        # the blanked tip, has the head put back routed with nothing current.
        for failing in _NEVER_LANDS:
            with self.subTest(record=failing):
                self.setUp()
                head, settled = self.settles_then_dies()
                self._strands()
                self._strands_unrecorded(failing)
                self._returns()

                self.assertIsNone(readings.pinned_records(self)[1])
                self.assertEqual(self.pinned_fields(readings.KEY_REWRITE_BASE), (None,))
                self.recovers()
                self._assert_routed_past(head, settled)

    def _assert_routed_past(self, head: str, settled) -> None:
        """`settled` invalidated whole into history, and `head` routed past it with nothing current, run once."""
        records = readings.pinned_records(self)
        self.assertIn((settled.receipt, readings.INVALIDATED), records[2])
        self.assertEqual(records[:2], (None, None))
        self.assert_recovered(head)
        self.assert_made_once()

    def _settles_then_strands(self):
        """Settle a reviewed rebase's run, kill its finish, move the checkout away, and relabel; the settled run."""
        settled = self.settles_then_dies()[1]
        self._strands()
        return settled

    def _strands(self) -> None:
        """Move the checkout away and relabel the issue out of the stages the refresh drives."""
        self._wt.rename(self._wt.parent / _AWAY)
        self.issue.labels = [FakeLabel(_UNDRIVEN)]

    def _strands_unrecorded(self, failing: str) -> None:
        """Have the dispatcher's hold answer the issue, its park's record refused or the process killed before it."""
        if failing == _KILLED:
            handoff.dies_at(self.gh, guarded.BEFORE_THE_RECORD, partial(guarded.answers_a_held_anchor, self))
            return
        refusing = partial(_refuses_the_park, self.gh.pinned_failures.refused, self.gh.edit_pinned_state)
        with patch.object(self.gh, _EDITS, refusing):
            guarded.answers_a_held_anchor(self)

    def _returns(self) -> None:
        """Put the checkout and the issue's label back where they stood."""
        (self._wt.parent / _AWAY).rename(self._wt)
        self.issue.labels = [FakeLabel(git_support.REVIEWING)]


class MissingCheckoutRecordTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A checkout gone from disk around a dormant hold's or park's own record has the reset recorded against the run."""

    def test_a_hold_that_never_lands(self) -> None:
        # The checkout is gone before the hold: the reset is recorded against
        # the run first, in a write of its own, and the hold's record, which
        # would retire the run, is refused, or the process is killed ahead of
        # it. With the checkout back the run reads moved, and the proof
        # invalidates it whole.
        for failing in _NEVER_LANDS:
            with self.subTest(record=failing):
                self.setUp()
                settled = self.settles_then_dies()[1]
                context = guarded.recovery_context(self)
                self._wt.rename(self._wt.parent / _AWAY)
                self._holds_unrecorded(context, failing)
                (self._wt.parent / _AWAY).rename(self._wt)

                self.assertEqual(readings.pinned_records(self)[1], settled)
                self._assert_read_moving(settled)

    def test_a_checkout_gone_behind_a_record(self) -> None:
        # The checkout goes from disk right as a hold's or a park's record
        # lands, or as a park's notice raises: nothing is left to prove the
        # run over behind it, so the reset is recorded against the run there,
        # and with the checkout back the proof invalidates it whole.
        for record in ("hold", "park", "notice"):
            with self.subTest(record=record):
                self.setUp()
                settled = self.settles_then_dies()[1]
                self._loses_the_checkout_behind(record)
                (self._wt.parent / _AWAY).rename(self._wt)

                self._assert_read_moving(settled)

    def test_a_loss_back_before_the_record(self) -> None:
        # A caller hands the proof a checkout it read gone, or the proof reads it gone itself, back before the proof or
        # its record reads it again, the first blank refused: the run, captured or settled, is still retired whole.
        for handed, captures in product((True, False), (False, True)):
            with self.subTest(handed=handed, captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                self._answers_a_loss_back(handed=handed)
                (self.assert_abandoned if captures else self.assert_invalidated)(run)
                self.assertTrue(self._wt.is_dir())
                self.assertTrue(self.proves())
                self.assertEqual(readings.pinned_records(self)[:2], (None, None))

    def _answers_a_loss_back(self, *, handed: bool) -> None:
        """The proof handed a checkout read gone, or reading it gone, back ahead of the proof or of its record."""
        context = guarded.recovery_context(self)
        away = self._wt.with_name(_AWAY)
        self._wt.rename(away)
        back = partial(away.rename, self._wt)
        races = ("records_the_reset", _FIRST_CALL.racing(_parks.records_the_reset, back, lambda: None))
        if handed:
            races = ("keeps_the_staging", _AHEAD_OF_THE_PROOF.moving(_parks.keeps_the_staging, back))
        blank = _FIRST_CALL.racing(
            self.gh.edit_pinned_state,
            partial(self.gh.pinned_failures.refused.add, self.issue.number),
            partial(self.gh.pinned_failures.refused.discard, self.issue.number),
        )
        with patch.object(_parks, *races), patch.object(self.gh, _EDITS, blank):
            _parks.proves_before_a_park(context, lost=(context.worktree,) if handed else ())

    def _holds_unrecorded(self, context, failing: str) -> None:
        """Hand the dormant hold `context`, its record refused or the process killed before it."""
        if failing == _KILLED:
            handoff.dies_at(self.gh, _AT_THE_RECORD, partial(_parks.lands_a_hold, context))
            return
        refusing = partial(_refuses_the_record, self.gh.pinned_failures.refused, self.gh.edit_pinned_state)
        with patch.object(self.gh, _EDITS, refusing):
            self.assertFalse(_parks.lands_a_hold(context))

    def _loses_the_checkout_behind(self, record: str) -> None:
        """Hand the dormant hold or park a context read off the comment, the checkout going behind `record`."""
        context = guarded.recovery_context(self)
        context.state.set(_GATE, self.anchor)
        away = partial(self._wt.rename, self._wt.parent / _AWAY)
        if record == "notice":
            with patch.object(self.gh, "comment", partial(_raises_behind, away)):
                self.assertRaises(RuntimeError, _parks.lands_a_park, context, _NOTICE, _REASON)
            return
        lands = partial(_parks.lands_a_park, message=_NOTICE, reason=_REASON)
        if record == "hold":
            lands = _parks.lands_a_hold
        edits = _AT_THE_RECORD.moving(self.gh.edit_pinned_state, away)
        with patch.object(self.gh, _EDITS, edits):
            lands(context)

    def _assert_read_moving(self, settled) -> None:
        """The attempt's base tip blanked against `settled`, which the proof then reads moved and invalidates whole."""
        standing = self.pinned_fields(readings.KEY_PENDING_PUSH, readings.KEY_REWRITE_BASE)
        self.assertEqual(standing, (self.anchor, None))
        self.assertTrue(self.proves())
        self.assert_invalidated(settled)


if __name__ == "__main__":
    unittest.main()
