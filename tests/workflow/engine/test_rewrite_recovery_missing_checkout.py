# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A checkout gone from disk under a guarded park or hold, its settled run's movement recorded around it.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
rebased head reviewed, its run settled under the anchor, and the finish killed
before its announcement. Then the checkout goes from disk and the issue is
relabelled to a stage the refresh does not drive, so the dispatcher's anchor
hold answers it with the stranded park that keeps the attempt -- handed the
workflow's proof and park by the dispatcher (`guarded_recovery_support`).

With no checkout there is nothing to prove the landing over, so the movement is recorded against the run first, by
blanking the base tip in a write of its own, and the run retired whole in another ahead of the park's record.

The guarded hold recording a publication gate's hold of a recovery's push takes the proof, so with no checkout the reset
is recorded ahead of the hold's record, and a hold record GitHub refuses
leaves the run read moving once the checkout is back. A checkout that goes
from disk only as a hold's or a park's record lands, or as a park's notice
raises, leaves nothing behind it to prove the run over, so the reset is
recorded against the run there instead. Nothing is run again, pushed, launched, announced, or relabelled before a route;
a checkout gone right behind the landed road's reading off the head leaves no park, the retirement landing on its own.
"""
from __future__ import annotations

import unittest
from functools import partial
from itertools import product
from unittest.mock import patch

from orchestrator.git.base_sync import persistence, rewrite_facts
from orchestrator.git.verification import probes
from orchestrator.workflow.engine import (
    base_refresh,
    rewrite_landing_moved as _moved,
    rewrite_recovery_parks as _parks,
    verification_settlement_state as _settlement,
)
from tests.support.fakes import FakeLabel
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

# A label the refresh does not drive, under which the dispatcher's hold strands the attempt.
_UNDRIVEN = "workflow:resolving_conflict"

_AWAY = "checkout-away"

# The client step a pinned-comment edit is.
_EDITS = "edit_pinned_state"

# How a record never lands: GitHub refuses it, or the process is killed before it.
_KILLED = "killed"
_NEVER_LANDS = ("refused", _KILLED)

# The park a case hands the guarded park directly, and why.
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
_REMOVES = ("worktree", "remove", "--force")

# How the hold reads a move: the checkout gone behind its proof, or on the anchor, the replay recorded or not.
_BEHIND, _UNRECORDED = "gone behind the proof", "on the anchor, its replay unrecorded"
_MOVES = (_BEHIND, "on the anchor", _UNRECORDED)

# The reads a checkout goes from disk under, back as the failure unwinds: the candidate's, and the lag's count.
_UNWOUND_READS = ((rewrite_facts, "_reads_the_checkout"), (base_refresh, "_worktree_behind_base"))


def _raises_behind(move, *_posted, **_options):
    """The issue-thread post of a park's notice, `move` made and then a raise as GitHub not answering."""
    move()
    raise RuntimeError("GitHub did not answer the notice's post")


class MissingCheckoutTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A checkout gone from disk has the movement recorded against the run before the stranded park retires it."""

    def test_a_landed_park_retires_the_run(self) -> None:
        # The stranded park keeps the attempt and lands the run's
        # invalidation in its own record, over the tip already blanked.
        settled = self._settles_then_strands()[1]
        guarded.answers_a_held_anchor(self)
        self._returns()

        standing = self.pinned_fields(*guarded.ATTEMPT_FIELDS)
        self.assertEqual(standing, (True, self.anchor, None))
        self.assert_invalidated(settled)

    def test_a_park_that_never_lands(self) -> None:
        # The stranded park's record is refused, or the process is killed
        # ahead of it: the run, retired first in a write of its own, has the head put back routed with nothing current.
        for failing in _NEVER_LANDS:
            with self.subTest(record=failing):
                self.setUp()
                head, settled = self._settles_then_strands()
                self._strands_unrecorded(failing)
                self._returns()

                self.assertIsNone(readings.pinned_records(self)[1])
                self.assertEqual(self.pinned_fields(readings.KEY_REWRITE_BASE), (None,))
                self.recovers()
                self._assert_routed_past(head, settled)

    def test_a_loss_the_dispatcher_read_is_kept(self) -> None:
        # The hold's question under a driven stage, or its answer under this one, reads the checkout gone, back by the
        # proof: the run, captured or settled, is retired whole all the same, and the next poll finds nothing standing.
        for label, captures in product((git_support.REVIEWING, _UNDRIVEN), (False, True)):
            with self.subTest(label=label, captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                away = self._wt.with_name(_AWAY)
                self._wt.rename(away)
                self.issue.labels = [FakeLabel(label)]
                back = _AHEAD_OF_THE_PROOF.moving(_parks.keeps_the_staging, partial(away.rename, self._wt))
                with patch.object(_parks, "keeps_the_staging", back):
                    guarded.answers_a_held_anchor(self)
                self.assertTrue(self._wt.is_dir())
                (self.assert_abandoned if captures else self.assert_invalidated)(run)
                self.issue.labels = [FakeLabel(git_support.REVIEWING)]
                self.recovers()
                self.assertEqual(readings.pinned_records(self)[:2], (None, None))

    def _assert_routed_past(self, head: str, settled) -> None:
        """`settled` invalidated whole into history, its revision and binding kept, and `head` routed past it."""
        retired = readings.pinned_records(self)[2]
        self.assertIn((settled.receipt, readings.INVALIDATED), retired)
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        self.assert_routed(head)

    def _settles_then_strands(self) -> tuple:
        """Settle a reviewed rebase's run, kill its finish, move the checkout away, and relabel; the head, the run."""
        settled = self.settles_then_dies()
        self._wt.rename(self._wt.parent / _AWAY)
        self.issue.labels = [FakeLabel(_UNDRIVEN)]
        return settled

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
    """A checkout gone from disk around a hold's or park's own record has the reset recorded against the run."""

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
        # The landed road hands the proof a checkout it read gone, or the proof reads it gone itself, back before the
        # proof or its record reads it again, the first blank refused: the run is still retired whole.
        for delegates, captures in product((True, False), (False, True)):
            with self.subTest(delegated=delegates, captured=captures):
                self.setUp()
                run = (self.captures() if captures else self.settles_then_dies())[1]
                self._answers_a_loss_back(delegates=delegates)
                (self.assert_abandoned if captures else self.assert_invalidated)(run)
                self.recovers()
                self.assertEqual(readings.pinned_records(self)[:2], (None, None))

    def _answers_a_loss_back(self, *, delegates: bool) -> None:
        """The landed road delegating, or the proof reading, a checkout gone, back ahead of the proof or its record."""
        context = guarded.recovery_context(self)
        away = self._wt.with_name(_AWAY)
        self._wt.rename(away)
        back = partial(away.rename, self._wt)
        races = ("records_the_reset", _FIRST_CALL.racing(_parks.records_the_reset, back, lambda: None))
        if delegates:
            races = ("keeps_the_staging", _AHEAD_OF_THE_PROOF.moving(_parks.keeps_the_staging, back))
        blank = _FIRST_CALL.racing(
            self.gh.edit_pinned_state,
            partial(self.gh.pinned_failures.refused.add, self.issue.number),
            partial(self.gh.pinned_failures.refused.discard, self.issue.number),
        )
        with patch.object(_parks, *races), patch.object(self.gh, _EDITS, blank):
            (_moved.abandons if delegates else _parks.proves_before_a_park)(context)

    def _holds_unrecorded(self, context, failing: str) -> None:
        """Hand the guarded hold `context`, its record refused or the process killed before it."""
        if failing == _KILLED:
            handoff.dies_at(self.gh, _AT_THE_RECORD, partial(_parks.lands_a_hold, context))
            return
        refusing = partial(_refuses_the_record, self.gh.pinned_failures.refused, self.gh.edit_pinned_state)
        with patch.object(self.gh, _EDITS, refusing):
            _parks.lands_a_hold(context)

    def _loses_the_checkout_behind(self, record: str) -> None:
        """Hand the guarded hold or park a context read off the comment, the checkout going behind `record`."""
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


class MovedCandidateTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A checkout read off the landed head that goes from disk before its run is retired still retires it whole."""

    def test_a_vanished_checkout_retires_the_run(self) -> None:
        # No park: the run retires in its own record after the reset's or, back as it is refused, by the loss's proof.
        for captures, returns in product((False, True), (False, True)):
            with self.subTest(captured=captures, returned=returns):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                away = self._wt.parent / _AWAY
                self._recovers_past_the_head(away, returns=returns)
                if captures:
                    self.assert_abandoned(run)
                else:
                    self.assert_invalidated(run)
                if away.exists():
                    away.rename(self._wt)
                self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
                self.recovers()
                self.assert_routed(head)

    def test_a_loss_back_as_it_unwinds(self) -> None:
        # The candidate's read, or the refresh's count of the base lag, finds the checkout gone, back as that failure
        # unwinds: the run, captured or settled, is retired whole all the same, and the next poll routes the head.
        for (owner, read), captures in product(_UNWOUND_READS, (False, True)):
            with self.subTest(read=read, captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                with patch.object(owner, read, partial(self._gone_while_read, getattr(owner, read))):
                    self.recovers()
                (self.assert_abandoned if captures else self.assert_invalidated)(run)
                self.recovers()
                self.assert_routed(head)

    def test_a_move_the_hold_read_is_kept(self) -> None:
        # The hold reads the checkout on the anchor, its replay recorded or not, back on the head behind that read, or
        # finds it gone behind its proof: the run, captured or settled, is retired whole before anything restores it.
        for move, captures in product(_MOVES, (False, True)):
            with self.subTest(move=move, captured=captures):
                self.setUp()
                head, run = self.captures() if captures else self.settles_then_dies()
                self._holds_over_a_move(head, move)
                (self.assert_abandoned if captures else self.assert_invalidated)(run)
                self.recovers()
                self.assertEqual(readings.pinned_records(self)[:2], (None, None))

    def _holds_over_a_move(self, head: str, move: str) -> None:
        """The dispatcher's hold, the checkout gone right behind its proof, or read on the anchor and put back."""
        owner, read = (persistence, "_proves_before_the_park") if move == _BEHIND else (probes, "_head_sha")
        moves = partial(self._git, "reset", "--quiet", "--hard", head, cwd=self._wt)
        if move == _BEHIND:
            checkout = str(self._wt)
            moves = partial(self._git, *_REMOVES, checkout, cwd=self._work)
        else:
            self._git("reset", "--quiet", "--hard", self.anchor, cwd=self._wt)
        if move == _UNRECORDED:
            unrecorded = self.gh.read_pinned_state(self.issue)
            unrecorded.set(readings.KEY_REWRITE_SHA, None)
            self.gh.write_pinned_state(self.issue, unrecorded)
        with patch.object(owner, read, _FIRST_CALL.moving(getattr(owner, read), moves)):
            guarded.answers_a_held_anchor(self)

    def _gone_while_read(self, live, *read, **options):
        """`live`, the checkout's reading, taken with the checkout away, put back as the failure it meets unwinds."""
        away = self._wt.with_name(_AWAY)
        self._wt.rename(away)
        try:
            return live(*read, **options)
        except FileNotFoundError:
            away.rename(self._wt)
            raise

    def _recovers_past_the_head(self, away, *, returns: bool) -> None:
        """Recover over the checkout read past the head and gone behind that reading, back where it `returns`."""
        self._moved = False
        reads = partial(self._moves_then_vanishes, rewrite_facts._reads_the_checkout, away)
        edits = self.gh.edit_pinned_state
        edits = partial(guarded.returns_under_the_blank, self, edits) if returns else edits
        with patch.object(rewrite_facts, "_reads_the_checkout", reads), patch.object(self.gh, _EDITS, edits):
            self.recovers()

    def _moves_then_vanishes(self, live, away, *read, **options):
        """`live`, the checkout's reading, taken past a stray commit, the checkout moved to `away` behind it, once."""
        if self._moved:
            return live(*read, **options)
        self._moved = True
        self._git(*support.STRAY_COMMIT, cwd=self._wt)
        reading = live(*read, **options)
        self._wt.rename(away)
        return reading


if __name__ == "__main__":
    unittest.main()
