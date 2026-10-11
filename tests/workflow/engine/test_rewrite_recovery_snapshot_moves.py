# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run whose landing moved before the recovery's first snapshot, abandoned before any road it takes.

A finish recorded its run for the landed head and died at its relabel, and the
landing moved before the next recovery fetched the branch: the remote rolled
back onto the anchor, the checkout reset onto it, or both moved on together to
another head. Each snapshot sends the recovery down a road that never takes the
run's route -- the park that resets and clears an announced attempt, the
rollback of an undone one, the park of a landing its announcement does not name
-- and the run is abandoned before it. A snapshot nobody could take -- a fetch
that failed, a remote head that would not resolve -- ends in the abort that
resets the checkout onto the anchor and clears the attempt -- as does a
checkout whose lag against its base could not be counted at all -- and once
that reset lands the run is abandoned in the write that releases the attempt; a
reset that failed moved nothing, and keeps it. So once both heads are put back,
the dispatcher's reconciliation has nothing left to settle. Nothing runs,
pushes, or announces again, and no developer is launched.
"""
from __future__ import annotations

import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport, commands
from orchestrator.workflow.engine import base_refresh, verification_transaction
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)

_STRAY_COMMIT = (
    "-c", "user.name=stray", "-c", "user.email=stray@example.invalid",
    "commit", "--quiet", "--allow-empty", "-m", "stray",
)


def _captures(case: support.VerificationRecoveryCase) -> tuple:
    """Land a reviewed rebase whose finish records its run and dies at the relabel; the head, and that run."""
    head = case.lands_a_reviewed_rebase()
    case.dies_routing(partial(case.finishes, head))
    case.assertEqual(case.runs(), 1)
    return head, readings.pinned_records(case)[0]


def _puts_the_remote_on(case: support.VerificationRecoveryCase, head: str) -> None:
    """Point `case`'s remote branch, and the pull request reading it, at `head`."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", head, cwd=case._remote)
    case.pull_request.head.sha = head


def _puts_the_checkout_on(case: support.VerificationRecoveryCase, head: str) -> None:
    """Reset `case`'s checkout onto `head`."""
    case._git("reset", "--quiet", "--hard", head, cwd=case._wt)


def _moves_both_on(case: support.VerificationRecoveryCase) -> None:
    """Commit past the landed head in `case`'s checkout and point the remote branch at that commit too."""
    case._git(*_STRAY_COMMIT, cwd=case._wt)
    case._git("push", "--quiet", "origin", f"HEAD:refs/heads/{git_support.BRANCH}", cwd=case._wt)
    case.pull_request.head.sha = case._wt_head()


# How the landing moves before the recovery's first snapshot.
_MOVES = (
    ("the remote rolled back onto the anchor", lambda case: _puts_the_remote_on(case, case.anchor)),
    ("the checkout reset onto the anchor", lambda case: _puts_the_checkout_on(case, case.anchor)),
    ("both moved on to another head", _moves_both_on),
)


# A snapshot nobody could take: the fetch failing, or the fetched remote head not
# resolving -- each beside the git seam it fails at and the calls it fails, or
# None for a seam whose every reading comes back as nothing.
_UNREAD_SNAPSHOTS = (
    ("the fetch failed", branch_transport, "_authed_fetch", lambda _called: True),
    (
        "the remote head did not resolve",
        commands,
        "_git_hardened",
        lambda called: called[0] == "rev-parse" and "refs/remotes/" in str(called),
    ),
    # The checkout's lag against its base not counted at all, which the
    # refresh answers with the same abort before any snapshot is taken.
    ("the checkout's base lag was not counted", base_refresh, "_worktree_behind_base", None),
)


def _refuses(original, refused, *called, **options):
    """Answer `original`, save a call `refused` names, which fails as git does."""
    if refused(called):
        return subprocess.CompletedProcess(called, 1, "", "refused")
    return original(*called, **options)


def _reconciles(case: support.VerificationRecoveryCase) -> None:
    """Run the dispatcher's reconciliation of `case`'s recorded evidence, over the comment as it stands."""
    verification_transaction._reconciles_pending_evidence(
        case.gh, case._spec, case.issue, git_support.REVIEWING, case.gh.read_pinned_state(case.issue),
    )


class SnapshotMoveRecoveryTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A captured run is abandoned by a recovery whose first snapshot reads its landing moved, whatever road follows."""

    def test_a_snapshot_off_the_landing_abandons(self) -> None:
        # Whatever moved, the recovery abandons the run before the road the
        # snapshot chose. Both heads put back on the landed head, the
        # reconciliation finds nothing pending, so the run is never settled.
        for moved, moves_it in _MOVES:
            with self.subTest(moved=moved):
                self.setUp()
                head, captured = _captures(self)
                moves_it(self)

                self.recovers()

                self._assert_abandoned(captured)
                _puts_the_remote_on(self, head)
                _puts_the_checkout_on(self, head)
                _reconciles(self)
                self._assert_abandoned(captured)
                said = (support.announced(self), self.pushes.call_count, self.developer.call_count)
                self.assertEqual(said, ([head], 0, 0))

    def test_an_unread_snapshot_reset_abandons(self) -> None:
        # The snapshot could not be taken, so the abort resets the checkout
        # onto the anchor and clears the attempt: the recovery's own reset is
        # movement, and the run is abandoned behind it. Put back on the
        # landed head, the reconciliation finds nothing pending.
        for unread, *failing in _UNREAD_SNAPSHOTS:
            with self.subTest(unread=unread):
                head, captured = self._recovers_unread(*failing)

                self._assert_abandoned(captured)
                self.assertEqual(
                    (self._wt_head(), readings.pinned(self)[readings.KEY_PENDING_PUSH]),
                    (self.anchor, None),
                )
                _puts_the_checkout_on(self, head)
                _reconciles(self)
                self._assert_abandoned(captured)
                self.assertEqual((self.pushes.call_count, self.developer.call_count), (0, 0))

    def test_a_failed_reset_keeps_the_run(self) -> None:
        # The fetch failed and the abort's reset failed too: the checkout and
        # the attempt stand where they were, nothing was read moving, and the
        # run is kept for the next proof.
        head, captured = _captures(self)
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

    def _recovers_unread(self, owner, seam: str, refused) -> tuple:
        """A fresh case's captured run, recovered with `owner`'s `seam` failing the calls `refused` names.

        The head and the run.
        """
        self.setUp()
        head, captured = _captures(self)
        failing = patch.object(owner, seam, return_value=None)
        if refused is not None:
            refusing = partial(_refuses, getattr(owner, seam), refused)
            failing = patch.object(owner, seam, side_effect=refusing)
        with failing:
            self.recovers()
        return head, captured

    def _assert_abandoned(self, captured) -> None:
        """Nothing pending or current, the settled evidence invalidated and `captured` abandoned, and no second run."""
        retired = (*git_support.invalidated(self), (captured.receipt, readings.ABANDONED))
        self.assertEqual(
            (readings.pinned_records(self), self.runs()),
            ((None, None, retired), 1),
        )


if __name__ == "__main__":
    unittest.main()
