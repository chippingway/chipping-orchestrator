# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Evidence a guarded reset moves under, recorded before the reset and kept whole where history has no room.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
reviewed rebase, its run settled under the anchor, and the finish killed
before its announcement. The next tick's recovery cannot fetch the branch, so
it takes the git owner's fail-closed abort, handed the workflow's guarded
operations as every recovery is (`guarded_recovery_support`): the reset is recorded first,
by blanking the base tip the attempt recorded its replay as made onto, so every
later proof of the run reads movement, and only then does the checkout go back
onto the anchor. A process killed behind the reset leaves the reset recorded,
so the checkout put back on the landed head revives nothing: the proof a park
that keeps the attempt asks reads the run moved and invalidates it whole, and
abandons a run the finish captured and never settled rather than keep it for a
finish to settle.

Where another road filled the pinned comment behind that record, the settled
run has no room for its history entry, so it is neither dropped nor left
behind a released attempt: it stays current, its binding whole, beside the
attempt that keeps every reader off it, and nothing is released, parked, or
noticed, however often the tick comes back. Put back on the landed head, the
checkout still finds it moved, and once room is made it is invalidated whole
into history, its revision and binding kept -- by the abort that then releases
the attempt and parks, or by that proof.

A blank GitHub refuses, or a process killed before it, holds the tick with
nothing reset, and so does a run another road settles while the recovery's
fetch fails, which the tick never read: the blank is decided on the evidence
records as the tick read them. The next tick records the reset, makes it, and
invalidates the run in the write that parks. So does a blank that lands with
its answer lost ahead of the park over a dirty checkout, which resets and
cleans: neither the reset nor the clean is made, and the tick's state, which
still carries the tip, is withheld from every write behind it, so it never
puts the tip back over the blank that landed. The run is never made again, and
nothing is announced, relabelled, pushed, or launched.
"""
from __future__ import annotations

import contextlib
import sys
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.git.base_sync import outcomes
from orchestrator.git.base_sync.models import _AutoRebaseRecoverySnapshot
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad
from tests.workflow.engine import (
    guarded_recovery_support as guarded,
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
)

_FETCH = branch_transport._authed_fetch

_FETCHES = "_authed_fetch"

_EDITS = "edit_pinned_state"

_RESET = "reset"

_KILLED = "killed"

# A hard reset of the checkout, as somebody putting it back on a head would make it.
_PUTS_BACK = (_RESET, "--quiet", "--hard")

# An untracked file the dead tick left in the checkout, which only the clean behind a reset removes.
_LEFTOVER = "leftover.txt"


def _blanking(_issue, state, *, over: dict) -> bool:
    """Whether a pinned-comment edit blanks the base tip the comment still records."""
    blanks = state.get(readings.KEY_REWRITE_BASE) is None
    return blanks and over.get(readings.KEY_REWRITE_BASE) is not None


_BEFORE_THE_BLANK = handoff.Boundary("before the base tip is blanked", _EDITS, _blanking)

# The recovery's fetch of issue #7's branch, behind which another road settles the run.
_BEHIND_THE_FETCH = handoff.Boundary(
    "behind the branch's fetch", _FETCHES, lambda _spec, ref, **_options: "issue-7" in ref,
)

# The reset git made, behind which the process is killed before anything else is written.
_RESETTING = handoff.Boundary("behind the reset", "_git_hardened", lambda verb, *_args, **_kwargs: verb == _RESET)


def _dies_behind_the_reset(case) -> None:
    """Take `case`'s guarded abort over an unfetched branch, the process killed behind the reset it makes."""
    dies = _RESETTING.moving(commands._git_hardened, partial(sys.exit, "the process was killed behind the reset"))
    with (
        patch.object(branch_transport, _FETCHES, guarded.unfetched),
        patch.object(commands, "_git_hardened", dies),
        contextlib.suppress(SystemExit),
    ):
        case.recovers()


def _loses_the_blank(live, issue, state, **options):
    """`live`, the client's pinned-comment edit, landed with its answer lost where it is the base tip's blank."""
    blanks = _blanking(issue, state, over=options["over"])
    answered = live(issue, state, **options)
    return PinnedEdit.UNCONFIRMED if blanks else answered


def _refuses_the_blank(refused: set, live, issue, state, **options):
    """`live`, the client's pinned-comment edit, refused by GitHub where it is the base tip's blank."""
    if _blanking(issue, state, over=options["over"]):
        refused.add(issue.number)
    answered = live(issue, state, **options)
    refused.discard(issue.number)
    return answered


class ResetRoomTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A run a recorded reset moved under, on a full comment, is kept whole until room is made."""

    def test_a_full_comment_keeps_the_run(self) -> None:
        # Every poll over the full comment leaves the run current and whole
        # beside the standing attempt, the tip blank, and nothing released,
        # parked, or noticed.
        settled = self._records_then_fills()
        noticed = len(self.gh.posted_comments)
        with patch.object(branch_transport, _FETCHES, guarded.unfetched):
            self.recovers()
            self.recovers()

        self._assert_kept(settled)
        self.assertEqual(len(self.gh.posted_comments), noticed)

    def test_room_made_releases_it_whole(self) -> None:
        # Room is made with the fetch still failing: the abort retires the run
        # whole into history in the write that releases the attempt and parks.
        settled = self._records_then_fills()
        with patch.object(branch_transport, _FETCHES, guarded.unfetched):
            self.recovers()
            finish_moves.makes_room(self)
            self.recovers()

        self.assert_invalidated(settled)
        self.assert_released()

    def test_a_landing_put_back_revives_nothing(self) -> None:
        # The checkout is put back on the landed head: the proof reads the
        # blank tip as movement, and with no room still keeps the run whole
        # and refuses the park; once room is made it invalidates it whole.
        settled = self._records_then_fills()
        self._git(*_PUTS_BACK, self.head, cwd=self._wt)

        self.assertFalse(self.proves())
        self._assert_kept(settled)
        finish_moves.makes_room(self)
        self.assertTrue(self.proves())

        self.assert_invalidated(settled)
        self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)

    def _records_then_fills(self):
        """Settle a reviewed rebase's run, kill the finish, die behind a recorded reset, and fill the comment.

        The settled run, current beside the attempt with the tip blank, on a
        comment with no room left for its history entry.
        """
        head, settled = self.settles_then_dies()
        self.head = head
        _dies_behind_the_reset(self)
        finish_moves.fills_the_comment(self)
        self._assert_kept(settled)
        return settled

    def _assert_kept(self, settled) -> None:
        """`settled` current and whole beside the standing attempt, the tip blank, nothing released, parked, or run."""
        kept = (None, settled, git_support.invalidated(self))
        self.assertEqual(readings.pinned_records(self), kept)
        parked, anchor, tip = self.pinned_fields(*guarded.ATTEMPT_FIELDS)
        self.assertFalse(parked)
        self.assertEqual((anchor, tip), (self.anchor, None))
        self.assert_made_once()


class ResetRecordTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A reset is recorded against a run before it moves the checkout, so nothing behind it revives the run."""

    def test_a_reset_lost_behind_revives_nothing(self) -> None:
        # The process dies behind the reset: the reset is already recorded,
        # so with the checkout put back on the landed head the proof reads the
        # run moved and invalidates it whole.
        head, settled = self.settles_then_dies()
        _dies_behind_the_reset(self)
        self._assert_standing(self.anchor, settled, blank=True)

        self._git(*_PUTS_BACK, head, cwd=self._wt)
        self.assertTrue(self.proves())

        self.assert_invalidated(settled)

    def test_a_captured_run_is_recorded_too(self) -> None:
        # The run was captured and never settled when the process died behind
        # the reset: the reset is recorded against it all the same, so with
        # the checkout put back on the landed head the proof abandons it
        # rather than keep it for a finish to settle, nothing run again.
        head, captured = self.captures()
        _dies_behind_the_reset(self)
        recorded = (self._wt_head(), *self.pinned_fields(readings.KEY_REWRITE_BASE))
        self.assertEqual(recorded, (self.anchor, None))
        self.assertEqual(readings.pinned_records(self)[0], captured)

        self._git(*_PUTS_BACK, head, cwd=self._wt)
        self.assertTrue(self.proves())

        self.assert_abandoned(captured)
        self.assertEqual((self.pushes.call_count, self.developer.call_count), (0, 0))

    def test_an_unrecorded_reset_is_not_made(self) -> None:
        # GitHub refuses the blank, or the process is killed before it: nothing
        # is reset or parked, the run and the tip stand as they were, and the
        # next tick records the reset, makes it, and invalidates the run in
        # the write that parks.
        for failing in ("refused", _KILLED):
            with self.subTest(record=failing):
                self.setUp()
                head, settled = self.settles_then_dies()
                with patch.object(branch_transport, _FETCHES, guarded.unfetched):
                    self._fails_to_record(failing)
                    self._assert_standing(head, settled, blank=False)
                    self.recovers()

                self.assert_invalidated(settled)
                self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def test_a_run_settled_meanwhile_holds_the_reset(self) -> None:
        # Another road settles the run while the recovery's fetch fails, over
        # an attempt the tick read with nothing recorded: the blank refuses it
        # and nothing is reset; the next tick resets and invalidates the run in
        # the write that parks, and the checkout put back revives nothing.
        head = self.lands_a_reviewed_rebase()
        git_support.pins_the_attempt(self, head)
        settles = _BEHIND_THE_FETCH.moving(guarded.unfetched, partial(self._settles_elsewhere, head))
        with patch.object(branch_transport, _FETCHES, settles):
            self.recovers()
        settled = readings.pinned_records(self)[1]
        self._assert_standing(head, settled, blank=False)

        with patch.object(branch_transport, _FETCHES, guarded.unfetched):
            self.recovers()
        self._git(*_PUTS_BACK, head, cwd=self._wt)
        self.recovers()

        self.assert_invalidated(settled)
        self.assert_released()

    def _fails_to_record(self, failing: str) -> None:
        """Take one tick whose blank of the base tip GitHub refuses, or whose process is killed before it."""
        if failing == _KILLED:
            handoff.dies_at(self.gh, _BEFORE_THE_BLANK, self.recovers)
            return
        refusing = partial(_refuses_the_blank, self.gh.pinned_failures.refused, self.gh.edit_pinned_state)
        with patch.object(self.gh, _EDITS, refusing):
            self.recovers()

    def _settles_elsewhere(self, head: str) -> None:
        """Settle `head`'s run as another road's finish of the landing would, dying before its announcement."""
        finishing = partial(self.finishes, head, FinishRoad.RECOVERY)
        with patch.object(branch_transport, _FETCHES, _FETCH):
            handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, finishing)

    def _assert_standing(self, checkout: str, settled, *, blank: bool) -> None:
        """The checkout on `checkout`, `settled` current beside the unparked attempt, its tip blank where `blank`."""
        parked, anchor, tip = self.pinned_fields(*guarded.ATTEMPT_FIELDS)
        standing = (self._wt_head(), bool(parked), anchor, tip is None)
        self.assertEqual(standing, (checkout, False, self.anchor, blank))
        self.assertEqual(readings.pinned_records(self)[1], settled)


class UnconfirmedRecordTest(guarded.GuardedRecoveryCase, unittest.TestCase):
    """A reset whose record did not land is not made, nor the clean behind it, and nothing stale undoes it."""

    def test_a_lost_record_resets_and_cleans_nothing(self) -> None:
        # The dirty checkout's park records its reset and the answer is lost:
        # neither the reset nor the clean behind it is made, the run and the
        # attempt stand whole beside the blank that landed, and the tick's own
        # state, which still carries the tip, writes nothing back over it. The
        # next tick finds the reset recorded, makes it and the clean, and
        # releases the attempt with the run invalidated whole.
        head, settled = self.settles_then_dies()
        (self._wt / _LEFTOVER).write_text("left behind by the dead tick\n")
        noticed = len(self.gh.posted_comments)
        with patch.object(self.gh, _EDITS, partial(_loses_the_blank, self.gh.edit_pinned_state)):
            stale = self._parks_the_dirty_checkout(head)
        self.gh.write_pinned_state(self.issue, stale.state)

        self.assertIsNotNone(stale.state.get(readings.KEY_REWRITE_BASE))
        self._assert_untouched(head, settled)
        self.assertEqual(len(self.gh.posted_comments), noticed)
        self._parks_the_dirty_checkout(head)

        self.assertEqual(self._checkout(), (self.anchor, False))
        self.assert_invalidated(settled)
        self.assert_released()

    def test_a_blank_under_a_refused_record_is_read(self) -> None:
        # Another road blanks the base tip as the reset's record reads, refusing
        # it, and puts it back: that movement still invalidates the run whole.
        settled = self.settles_then_dies()[1]
        armed: list = []
        reads = partial(self._reads_a_blank_once, armed, self.gh.read_pinned_state)
        fetches = _BEHIND_THE_FETCH.moving(guarded.unfetched, partial(armed.append, True))
        with patch.object(branch_transport, _FETCHES, fetches), patch.object(self.gh, "read_pinned_state", reads):
            self.recovers()
        self.recovers()
        invalidated = (settled.receipt, readings.INVALIDATED)
        self.assertIsNone(readings.pinned_records(self)[1])
        self.assertIn(invalidated, readings.pinned_records(self)[2])

    def _reads_a_blank_once(self, armed: list, read, issue):
        """`read`, the comment's reading, the first behind `armed` taken with the base tip blanked, put back behind."""
        if armed != [True]:
            return read(issue)
        armed.append(False)
        saved = read(issue)
        blank = read(issue)
        blank.set(readings.KEY_REWRITE_BASE, None)
        self.gh.write_pinned_state(issue, blank)
        answer = read(issue)
        self.gh.write_pinned_state(issue, saved)
        return answer

    def _parks_the_dirty_checkout(self, head: str):
        """Take the git owner's park over a dirty checkout on `head`, which resets and cleans, guarded; its context."""
        context = guarded.recovery_context(self)
        snapshot = _AutoRebaseRecoverySnapshot(branch=git_support.BRANCH, local_head=head)
        outcomes._park_dirty_recovery(context, snapshot, [_LEFTOVER])
        return context

    def _checkout(self) -> tuple:
        """The head the checkout stands on, and whether the dead tick's leftover is still in it."""
        return self._wt_head(), (self._wt / _LEFTOVER).exists()

    def _assert_untouched(self, head: str, settled) -> None:
        """The checkout still on `head` with the leftover in it, and `settled` current beside the unparked attempt.

        The base tip is the blank that landed, which every later proof of
        `settled` reads as movement.
        """
        self.assertEqual(self._checkout(), (head, True))
        self.assertEqual(readings.pinned_records(self)[1], settled)
        parked, anchor, tip = self.pinned_fields(*guarded.ATTEMPT_FIELDS)
        self.assertFalse(parked)
        self.assertEqual((anchor, tip), (self.anchor, None))


if __name__ == "__main__":
    unittest.main()
