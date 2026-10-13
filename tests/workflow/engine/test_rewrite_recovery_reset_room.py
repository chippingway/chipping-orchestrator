# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settled evidence a landed reset moves under, kept whole where the pinned comment has no room to retire it.

The real-git finish case (`rewrite_verification_recovery_support`): issue #7's
reviewed rebase, its run settled under the anchor, and the finish killed
before its announcement. Another road then fills the pinned comment to its
limit, and the next tick's recovery cannot fetch the branch, so it takes the
fail-closed abort: the checkout goes back onto the anchor. The settled run has
no room for its history entry, so it is neither dropped nor left behind a
released attempt: it stays current, its binding whole, beside the attempt that
keeps every reader off it, and the reset is recorded by blanking the base tip
the attempt recorded its replay as made onto, so every later proof of the run
reads movement. Nothing is released or parked, and a process killed before
that blank lands is answered the same way by the next tick.

Once room is made, the run is invalidated whole into history, its revision and
binding kept -- by the abort that then releases the attempt and parks, or,
with the checkout put back on the landed head, by the finish that proves the
run again and routes the head with nothing current. The run is never made
again, and nothing is pushed or launched.

The blank lands ahead of the reset, with room on the comment or none, and
over a run the finish captured and never settled as well as a settled one: a
process killed behind the reset, before anything else is written, leaves the
reset recorded, so the checkout put back on the landed head before the next
poll revives nothing -- the settled run is invalidated, and the captured one
abandoned rather than settled. A blank GitHub refuses holds the tick with
nothing reset, and the next tick records it and resets. So does a run another
road settles while the recovery's fetch fails, which the tick never read: the
blank is decided on the evidence records as the tick read them, so it is
refused and nothing is reset, and the next tick records the reset against
that run, resets, and invalidates it, so putting the checkout back revives
nothing.
"""
from __future__ import annotations

import contextlib
import subprocess
import sys
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.workflow.engine import verification_settlement_state as _settlement
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

_AWAITING = "awaiting_human"

_FETCH = branch_transport._authed_fetch

_FETCHES = "_authed_fetch"

_RESET = "reset"

# A hard reset of the checkout, as somebody putting it back on a head would make it.
_PUTS_BACK = (_RESET, "--quiet", "--hard")


def _unfetched(spec, ref: str, **options) -> subprocess.CompletedProcess:
    """The branch transport's fetch, failing for issue #7's branch alone."""
    if "issue-7" in ref:
        return subprocess.CompletedProcess([], 1, "", "fetch failed")
    return _FETCH(spec, ref, **options)


def _blanking(_issue, state, *, over: dict) -> bool:
    """Whether a pinned-comment edit blanks the base tip the comment still records."""
    blanks = state.get(readings.KEY_REWRITE_BASE) is None
    return blanks and over.get(readings.KEY_REWRITE_BASE) is not None


_BEFORE_THE_BLANK = handoff.Boundary("before the base tip is blanked", "edit_pinned_state", _blanking)

# The recovery's fetch of issue #7's branch, behind which another road settles the run.
_BEHIND_THE_FETCH = handoff.Boundary(
    "behind the branch's fetch", _FETCHES, lambda _spec, ref, **_options: "issue-7" in ref,
)

# The reset git made, behind which the process is killed before anything else is written.
_RESETTING = handoff.Boundary("behind the reset", "_git_hardened", lambda verb, *_args, **_kwargs: verb == _RESET)


def _dies_behind_the_reset():
    """The git owner's hardened git, killing the process behind the first reset it makes."""
    return _RESETTING.moving(commands._git_hardened, partial(sys.exit, "the process was killed behind the reset"))


def _refuses_the_blank(refused: set, live, issue, state, *, over: dict):
    """`live`, the client's pinned-comment edit, refused by GitHub where it is the base tip's blank."""
    if _blanking(issue, state, over=over):
        refused.add(issue.number)
    answered = live(issue, state, over=over)
    refused.discard(issue.number)
    return answered


def _assert_invalidated(case: support.CapturedRunCase, settled) -> None:
    """`settled` invalidated whole behind the anchor's evidence, its revision and binding kept, run once."""
    retired = (*git_support.invalidated(case), (settled.receipt, readings.INVALIDATED))
    case.assertEqual(readings.pinned_records(case), (None, None, retired))
    entry = _settlement.read_evidence_history(case.gh.read_pinned_state(case.issue))[-1]
    case.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
    made = (case.runs(), case.pushes.call_count, case.developer.call_count)
    case.assertEqual(made, (1, 0, 0))


class ResetRoomTest(support.CapturedRunCase, unittest.TestCase):
    """A run a landed reset moved under, on a comment with no room for its history, is kept whole until room is made."""

    def test_a_full_comment_keeps_the_run(self) -> None:
        # Whether or not the first tick lived to blank the tip, the next one
        # leaves the run current and whole beside the standing attempt, the
        # tip blank, and nothing released or parked.
        for boundary in (None, _BEFORE_THE_BLANK):
            with self.subTest(boundary=getattr(boundary, "name", "uninterrupted")):
                self.setUp()
                settled = self._settles_then_fills()
                with patch.object(branch_transport, _FETCHES, _unfetched):
                    handoff.dies_at(self.gh, boundary, self.recovers)
                    self.recovers()

                self._assert_kept(settled)

    def test_room_made_releases_it_whole(self) -> None:
        # Room is made with the fetch still failing: the abort retires the run
        # whole into history in the write that releases the attempt and parks.
        settled = self._settles_then_fills()
        with patch.object(branch_transport, _FETCHES, _unfetched):
            self.recovers()
            finish_moves.makes_room(self)
            self.recovers()

        _assert_invalidated(self, settled)
        pinned = readings.pinned(self)
        parked = (pinned[_AWAITING], readings.attempt(pinned))
        self.assertEqual(parked, (True, readings.RETIRED))

    def test_a_landing_put_back_revives_nothing(self) -> None:
        # The checkout is put back on the landed head before room is made: the
        # finish proves the run again, reads the blank tip as movement, and
        # invalidates it whole, routing the head with nothing current.
        head = self.lands_a_reviewed_rebase()
        settled = self._dies_and_fills(head)
        with patch.object(branch_transport, _FETCHES, _unfetched):
            self.recovers()
        self._git(*_PUTS_BACK, head, cwd=self._wt)
        finish_moves.makes_room(self)
        self.recovers()

        _assert_invalidated(self, settled)
        routed = (support.announced(self), readings.relabels(self))
        self.assertEqual(routed, ([head], readings.ROUTED))

    def _settles_then_fills(self):
        """Land and review a rebase, settle its run, kill the finish before its announcement, and fill the comment."""
        return self._dies_and_fills(self.lands_a_reviewed_rebase())

    def _dies_and_fills(self, head: str):
        """Kill `head`'s finish before its announcement, its run settled, and fill the comment; the settled run."""
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, lambda: self.finishes(head))
        settled = readings.pinned_records(self)[1]
        self.assertEqual(settled.binding.target.target_head, head)
        finish_moves.fills_the_comment(self)
        return settled

    def _assert_kept(self, settled) -> None:
        """`settled` current and whole beside the standing attempt, the tip blank, nothing released or parked."""
        kept = (None, settled, git_support.invalidated(self))
        self.assertEqual(readings.pinned_records(self), kept)
        pinned = readings.pinned(self)
        attempt = (pinned[readings.KEY_PENDING_PUSH], pinned.get(readings.KEY_REWRITE_BASE))
        self.assertEqual(attempt, (self.anchor, None))
        self.assertFalse(pinned.get(_AWAITING))
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


class ResetRecordTest(support.CapturedRunCase, unittest.TestCase):
    """A reset is recorded against a settled run before it moves the checkout, so nothing behind it revives the run."""

    def test_a_reset_lost_behind_revives_nothing(self) -> None:
        # The process dies behind the reset, over a full comment or one with
        # room: the reset is already recorded, so the checkout put back on the
        # landed head and room made leave the next finish reading the run
        # moved, invalidating it whole and routing the head with nothing current.
        for full in (True, False):
            with self.subTest(full=full):
                self.setUp()
                head = self.lands_a_reviewed_rebase()
                settled = self._settles_and_resets(head, full=full)

                self._git(*_PUTS_BACK, head, cwd=self._wt)
                if full:
                    finish_moves.makes_room(self)
                self.recovers()

                _assert_invalidated(self, settled)
                routed = (support.announced(self), readings.relabels(self))
                self.assertEqual(routed, ([head], readings.ROUTED))

    def test_a_captured_run_is_recorded_too(self) -> None:
        # The run was captured and never settled when the process died behind
        # the reset: the reset is recorded against it all the same, so the
        # checkout put back on the landed head and the branch fetched again
        # abandon the run rather than settle it, nothing run again.
        head, captured = self.captures()
        with (
            patch.object(branch_transport, _FETCHES, _unfetched),
            patch.object(commands, "_git_hardened", _dies_behind_the_reset()),
            contextlib.suppress(SystemExit),
        ):
            self.recovers()
        self.assertEqual(self._wt_head(), self.anchor)
        self.assertEqual(readings.pinned_records(self)[0], captured)
        self.assertIsNone(readings.pinned(self)[readings.KEY_REWRITE_BASE])

        self._git(*_PUTS_BACK, head, cwd=self._wt)
        self.recovers()

        self.assert_abandoned(captured)
        self.assertEqual((self.pushes.call_count, self.developer.call_count), (0, 0))

    def test_a_refused_record_resets_nothing(self) -> None:
        # GitHub refuses the blank: nothing is reset or parked, the run and
        # the tip stand as they were, and the next tick records the reset,
        # makes it, and invalidates the run in the write that parks.
        head = self.lands_a_reviewed_rebase()
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        settled = readings.pinned_records(self)[1]
        refusing = partial(_refuses_the_blank, self.gh.pinned_failures.refused, self.gh.edit_pinned_state)
        with patch.object(branch_transport, _FETCHES, _unfetched):
            with patch.object(self.gh, "edit_pinned_state", refusing):
                self.recovers()
            self._assert_standing(head, settled, blank=False)
            self.recovers()

        _assert_invalidated(self, settled)
        self.assertEqual(readings.attempt(readings.pinned(self)), readings.RETIRED)

    def test_a_run_settled_meanwhile_holds_the_reset(self) -> None:
        # Another road settles the run while the recovery's fetch fails, over
        # an attempt the tick read with nothing recorded: the blank refuses it
        # and nothing is reset; the next tick resets and invalidates the run in
        # the write that parks, and the checkout put back revives nothing.
        head = self.lands_a_reviewed_rebase()
        git_support.pins_the_attempt(self, head)
        settles = _BEHIND_THE_FETCH.moving(_unfetched, partial(self._settles_elsewhere, head))
        with patch.object(branch_transport, _FETCHES, settles):
            self.recovers()
        settled = readings.pinned_records(self)[1]
        self._assert_standing(head, settled, blank=False)

        with patch.object(branch_transport, _FETCHES, _unfetched):
            self.recovers()
        self._git(*_PUTS_BACK, head, cwd=self._wt)
        self.recovers()

        _assert_invalidated(self, settled)
        pinned = readings.pinned(self)
        parked = (pinned[_AWAITING], readings.attempt(pinned))
        self.assertEqual(parked, (True, readings.RETIRED))

    def _settles_elsewhere(self, head: str) -> None:
        """Settle `head`'s run as another road's finish of the landing would, dying before its announcement."""
        finishing = partial(self.finishes, head, FinishRoad.RECOVERY)
        with patch.object(branch_transport, _FETCHES, _FETCH):
            handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, finishing)

    def _settles_and_resets(self, head: str, *, full: bool):
        """Settle `head`'s run, kill its finish, fill the comment where `full`, and die behind an abort's reset.

        The run, standing current beside the attempt with the tip blank and the
        checkout reset onto the anchor.
        """
        handoff.dies_at(self.gh, handoff.BEFORE_THE_ANNOUNCEMENT, partial(self.finishes, head))
        settled = readings.pinned_records(self)[1]
        if full:
            finish_moves.fills_the_comment(self)
        with (
            patch.object(branch_transport, _FETCHES, _unfetched),
            patch.object(commands, "_git_hardened", _dies_behind_the_reset()),
            contextlib.suppress(SystemExit),
        ):
            self.recovers()
        self._assert_standing(self.anchor, settled, blank=True)
        return settled

    def _assert_standing(self, checkout: str, settled, *, blank: bool) -> None:
        """The checkout on `checkout`, `settled` current beside the unparked attempt, its tip blank where `blank`."""
        pinned = readings.pinned(self)
        self.assertEqual(self._wt_head(), checkout)
        self.assertEqual(readings.pinned_records(self)[1], settled)
        self.assertEqual(pinned[readings.KEY_PENDING_PUSH], self.anchor)
        self.assertFalse(pinned.get(_AWAITING))
        self.assertEqual(pinned.get(readings.KEY_REWRITE_BASE) is None, blank)


if __name__ == "__main__":
    unittest.main()
