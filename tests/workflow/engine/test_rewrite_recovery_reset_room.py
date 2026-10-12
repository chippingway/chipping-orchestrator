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
"""
from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.workflow.engine import verification_settlement_state as _settlement
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_moves as finish_moves,
    rewrite_finish_readings as readings,
    rewrite_handoff_test_support as handoff,
    rewrite_verification_recovery_support as support,
)

_AWAITING = "awaiting_human"

_FETCH = branch_transport._authed_fetch


def _unfetched(spec, ref: str, **options) -> subprocess.CompletedProcess:
    """The branch transport's fetch, failing for issue #7's branch alone."""
    if "issue-7" in ref:
        return subprocess.CompletedProcess([], 1, "", "fetch failed")
    return _FETCH(spec, ref, **options)


def _blanking(_issue, state, *, over: dict) -> bool:
    """Whether a pinned-comment edit blanks the base tip the comment still records."""
    blanks = state.get(readings.KEY_REWRITE_BASE) is None
    return blanks and over.get(readings.KEY_REWRITE_BASE) is not None


_BEFORE_THE_BLANK = handoff.Boundary("reset, before the base tip is blanked", "edit_pinned_state", _blanking)


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
                with patch.object(branch_transport, "_authed_fetch", _unfetched):
                    handoff.dies_at(self.gh, boundary, self.recovers)
                    self.recovers()

                self._assert_kept(settled)

    def test_room_made_releases_it_whole(self) -> None:
        # Room is made with the fetch still failing: the abort retires the run
        # whole into history in the write that releases the attempt and parks.
        settled = self._settles_then_fills()
        with patch.object(branch_transport, "_authed_fetch", _unfetched):
            self.recovers()
            finish_moves.makes_room(self)
            self.recovers()

        self._assert_invalidated(settled)
        pinned = readings.pinned(self)
        parked = (pinned[_AWAITING], readings.attempt(pinned))
        self.assertEqual(parked, (True, readings.RETIRED))

    def test_a_landing_put_back_revives_nothing(self) -> None:
        # The checkout is put back on the landed head before room is made: the
        # finish proves the run again, reads the blank tip as movement, and
        # invalidates it whole, routing the head with nothing current.
        head = self.lands_a_reviewed_rebase()
        settled = self._dies_and_fills(head)
        with patch.object(branch_transport, "_authed_fetch", _unfetched):
            self.recovers()
        self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
        finish_moves.makes_room(self)
        self.recovers()

        self._assert_invalidated(settled)
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

    def _assert_invalidated(self, settled) -> None:
        """`settled` invalidated whole behind the anchor's evidence, its revision and binding kept, run once."""
        retired = (*git_support.invalidated(self), (settled.receipt, readings.INVALIDATED))
        self.assertEqual(readings.pinned_records(self), (None, None, retired))
        entry = _settlement.read_evidence_history(self.gh.read_pinned_state(self.issue))[-1]
        self.assertEqual((entry.revision, entry.binding), (settled.revision, settled.binding))
        made = (self.runs(), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(made, (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
