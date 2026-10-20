# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run whose landing moved before the recovery's first snapshot, abandoned before any road it takes.

A finish recorded its run for the landed head and died posting its artifact, and the
landing moved before the next recovery fetched the branch: the remote rolled
back onto the anchor, the checkout reset onto it, or both moved on together to
another head. Each snapshot sends the recovery down a road that never takes the
run's route -- the park of a replay the run says landed and the remote was
rolled back off, the rollback of an undone one, the park of a landing nothing
on the comment names -- and the run is abandoned before it. No announcement
mark is down yet, since the finish resolves the evidence first, but the run
itself says the push landed, so the rolled-back remote is parked rather than
pushed over. A snapshot nobody could take -- a fetch
that failed, a remote head that would not resolve -- ends in the abort that
resets the checkout onto the anchor and clears the attempt -- as does a
checkout whose lag against its base could not be counted at all -- and once
that reset lands the run is abandoned in the write that releases the attempt; a
reset that failed moved nothing, and keeps it -- unless the fetch had already
read the checkout off the landed head, which abandons the run before the
remote head is resolved, so not even a resolution and a reset that both fail
leave it for a human's continue to revive. So once both heads are put back,
the dispatcher's reconciliation has nothing left to settle. Nothing runs,
pushes, or announces again, and no developer is launched.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.workflow.engine import base_refresh
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)


def _puts_the_remote_on(case: support.VerificationRecoveryCase, head: str) -> None:
    """Point `case`'s remote branch, and the pull request reading it, at `head`."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", head, cwd=case._remote)
    case.pull_request.head.sha = head


def _puts_the_checkout_on(case: support.VerificationRecoveryCase, head: str) -> None:
    """Reset `case`'s checkout onto `head`."""
    case._git("reset", "--quiet", "--hard", head, cwd=case._wt)


def _moves_both_on(case: support.VerificationRecoveryCase) -> None:
    """Commit past the landed head in `case`'s checkout and point the remote branch at that commit too."""
    case._git(*support.STRAY_COMMIT, cwd=case._wt)
    case._git("push", "--quiet", "origin", f"HEAD:refs/heads/{git_support.BRANCH}", cwd=case._wt)
    case.pull_request.head.sha = case._wt_head()


# How the landing moves before the recovery's first snapshot.
_MOVES = (
    ("the remote rolled back onto the anchor", lambda case: _puts_the_remote_on(case, case.anchor)),
    ("the checkout reset onto the anchor", lambda case: _puts_the_checkout_on(case, case.anchor)),
    ("both moved on to another head", _moves_both_on),
)


def _resets(called: tuple) -> bool:
    """Whether a git call resets the checkout."""
    return called[0] == "reset"


def _resolves_the_remote(called: tuple) -> bool:
    """Whether a git call resolves the pull request's fetched remote head, rather than any base ref."""
    return called[:2] == ("rev-parse", f"refs/remotes/origin/{git_support.BRANCH}")


# A snapshot nobody could take -- the fetched remote head not resolving; a fetch
# that failed is the abort's own case (`test_rewrite_recovery_unlanded_abandonment`)
# -- each beside the git seam it fails at and the calls it fails, or None for a
# seam whose every reading comes back as nothing.
_UNREAD_SNAPSHOTS = (
    ("the remote head did not resolve", commands, "_git_hardened", _resolves_the_remote),
    # The checkout's lag against its base not counted at all, which the
    # refresh answers with the same abort before any snapshot is taken.
    ("the checkout's base lag was not counted", base_refresh, "_worktree_behind_base", None),
)


# A checkout the fetch reads off the landed head, beside the git calls that fail
# behind it: reset onto the anchor, which the rollback resets again; and
# committed past the head with the remote head not resolving, which the abort
# resets. Either reset fails.
_MOVED_BEHIND_A_FAILED_RESET = (
    ("the checkout reset onto the anchor", lambda case: _puts_the_checkout_on(case, case.anchor), _resets),
    (
        "the checkout committed past the head, the remote head unresolved",
        lambda case: case._git(*support.STRAY_COMMIT, cwd=case._wt),
        lambda called: _resets(called) or _resolves_the_remote(called),
    ),
)


def _refuses(original, refused, *called, **options):
    """Answer `original`, save a call `refused` names, which fails as git does."""
    if refused(called):
        return subprocess.CompletedProcess(called, 1, "", "refused")
    return original(*called, **options)


class SnapshotMoveRecoveryTest(support.CapturedRunCase, unittest.TestCase):
    """A captured run is abandoned by a recovery whose first snapshot reads its landing moved, whatever road follows."""

    def test_a_snapshot_off_the_landing_abandons(self) -> None:
        # Whatever moved, the recovery abandons the run before the road the
        # snapshot chose, and that road's park lands behind the abandonment's
        # own write -- the recovery's earlier checkpoint, not a move under it.
        # Both heads put back on the landed head, the reconciliation finds
        # nothing pending, so the run is never settled.
        for move in _MOVES:
            with self.subTest(moved=move[0]):
                self.setUp()
                head, captured = self.captures()
                move[1](self)

                self.recovers()

                parked = bool(readings.pinned(self).get("awaiting_human"))
                self.assert_abandoned(captured)
                _puts_the_remote_on(self, head)
                _puts_the_checkout_on(self, head)
                self.reconciles()
                self.assert_abandoned(captured)
                said = (support.announced(self), self.pushes.call_count, self.developer.call_count, parked)
                self.assertEqual(said, ([], 0, 0, True))

    def test_an_unread_snapshot_reset_abandons(self) -> None:
        # The snapshot could not be taken, so the abort resets the checkout
        # onto the anchor and clears the attempt: the recovery's own reset is
        # movement, and the run is abandoned behind it. Put back on the
        # landed head, the reconciliation finds nothing pending.
        for unread, *failing in _UNREAD_SNAPSHOTS:
            with self.subTest(unread=unread):
                head, captured = self._recovers_unread(*failing)

                self.assert_abandoned(captured)
                self._assert_parked(reset=True)
                self.assertEqual(
                    (self._wt_head(), readings.pinned(self)[readings.KEY_PENDING_PUSH]),
                    (self.anchor, None),
                )
                _puts_the_checkout_on(self, head)
                self.reconciles()
                self.assert_abandoned(captured)
                self.assertEqual((self.pushes.call_count, self.developer.call_count), (0, 0))

    def test_a_failed_reset_keeps_the_run(self) -> None:
        # The fetch failed and the abort's reset failed too: the checkout and
        # the attempt stand where they were, nothing was read moving, and the
        # run is kept for the next proof.
        head, captured = self.captures()
        unread = partial(_refuses, branch_transport._authed_fetch, lambda _called: True)
        unreset = partial(_refuses, commands._git_hardened, lambda called: called[0] == "reset")
        with (
            patch.object(branch_transport, "_authed_fetch", side_effect=unread),
            patch.object(commands, "_git_hardened", side_effect=unreset),
        ):
            self.recovers()

        self.assertEqual(self._wt_head(), head)
        self.assert_held(captured)
        self.assertEqual(self.runs(), 1)
        self._assert_parked(reset=False)

    def test_a_failed_reset_behind_a_move_abandons(self) -> None:
        # The fetch read the checkout off the landed head, and the road's own
        # reset of it fails -- behind a remote head that did not resolve, too:
        # that reset moved nothing, but the checkout had already moved, so the
        # run is abandoned before the road is taken, the attempt kept as the
        # failed reset leaves it. Put back on the head and continued by a
        # human, the recovery routes it with the run still abandoned and
        # nothing made current.
        for moved, moves_it, refused in _MOVED_BEHIND_A_FAILED_RESET:
            with self.subTest(moved=moved):
                head, captured = self._recovers_failing(moves_it, refused)

                self.assert_abandoned(captured)
                self.assertEqual(readings.pinned(self)[readings.KEY_PENDING_PUSH], self.anchor)
                self._assert_parked(reset=False)
                _puts_the_checkout_on(self, head)
                self.continues()
                self.recovers()
                self.reconciles()
                self.assert_abandoned(captured)
                self.assert_recovered(head)

    def _recovers_failing(self, moves_it, refused) -> tuple:
        """A fresh case's captured run, `moves_it` done to it and recovered with the git calls `refused` names failing.

        The head and the run.
        """
        self.setUp()
        captured = self.captures()
        moves_it(self)
        failing = partial(_refuses, commands._git_hardened, refused)
        with patch.object(commands, "_git_hardened", side_effect=failing):
            self.recovers()
        return captured

    def _assert_parked(self, *, reset: bool) -> None:
        """The notice the recovery parked with says whether its reset to the anchor landed, and what the park kept."""
        notice = self.gh.posted_comments[-1][1]
        short = self.anchor[:8]
        landed = (f"Local HEAD has been reset to `{short}`" in notice, "is dropped by the pinned-state write" in notice)
        failed = (f"`git reset --hard {short}` failed" in notice, "keeps the attempt" in notice)
        expected = ((reset, reset), (not reset, not reset))
        self.assertEqual((landed, failed), expected, notice)

    def _recovers_unread(self, owner, seam: str, refused) -> tuple:
        """A fresh case's captured run, recovered with `owner`'s `seam` failing the calls `refused` names.

        The head and the run.
        """
        self.setUp()
        head, captured = self.captures()
        failing = patch.object(owner, seam, return_value=None)
        if refused is not None:
            refusing = partial(_refuses, getattr(owner, seam), refused)
            failing = patch.object(owner, seam, side_effect=refusing)
        with failing:
            self.recovers()
        return head, captured


if __name__ == "__main__":
    unittest.main()
