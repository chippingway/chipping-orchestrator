# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A captured run whose abandonment is read moving keeps that abandonment, however its first write fails.

A finish recorded its run for the landed head and died at its relabel, and the
remote was rolled back onto the anchor before the next recovery. That snapshot
is movement under the run, and the road it chooses resets and clears the
attempt -- so the run is abandoned first. Where the abandonment's own write
over the comment read again does not land -- that comment would not read, or
another road moved a record under the write -- it is staged on the tick's own
reading instead and lands there, so the movement is kept: with both heads put
back, a later recovery and the dispatcher's reconciliation settle nothing.
Only a comment that takes no write at all leaves the run unabandoned, and then
the recovery takes no road: nothing is reset, cleared, or parked, and the
attempt's anchor keeps the reconciliation off the run.

A fetch that fails ends in the git owner's abort, whose reset takes the
checkout off the landed head itself: the run is abandoned on the state that
abort's park writes, so it goes in the very write that releases the attempt --
whatever a comment read of the abandonment's own would have answered -- or,
where that write does not land, neither goes and the attempt still guards the
run. Nothing runs, pushes, or announces again, and no developer is launched.
"""
from __future__ import annotations

import hashlib
import subprocess
import unittest
from functools import partial
from unittest.mock import patch

from orchestrator.git import branch_transport
from orchestrator.github.pinned_state import PinnedEdit
from orchestrator.workflow.engine import verification_durable, verification_transaction
from orchestrator.workflow.engine.review_subjects import REVIEW_SUBJECT
from tests.workflow.engine import (
    rewrite_finish_git_support as git_support,
    rewrite_finish_readings as readings,
    rewrite_verification_recovery_support as support,
)
from tests.workflow.interleaving import _RacesPastTheStep

_DURABLE_READ = "durable_comment"

# A fetch of the pull request's branch that failed.
_UNFETCHED = subprocess.CompletedProcess([], 1, "", "unread remote")

# The comment read again for the abandonment answering as one nobody could read.
_UNREAD = (None, verification_durable._UNREAD)

# A requirements revision no reviewer was handed, for a review subject another road moves.
_ELSEWHERE = hashlib.sha256(b"requirements another road recorded").hexdigest()


def _moves_the_subject(case: support.VerificationRecoveryCase) -> None:
    """Move the review subject on `case`'s pinned comment, as another road's write would."""
    moved = case.gh.read_pinned_state(case.issue)
    moved.set(REVIEW_SUBJECT, {**moved.get(REVIEW_SUBJECT), "requirements": _ELSEWHERE})
    case.gh.write_pinned_state(case.issue, moved)


def _unreadable(*_called, **_options):
    """The comment read again for an abandonment, answering as one nobody could read."""
    return _UNREAD


def _puts_the_remote_on(case: support.VerificationRecoveryCase, head: str) -> None:
    """Point `case`'s remote branch at `head`."""
    case._git("update-ref", f"refs/heads/{git_support.BRANCH}", head, cwd=case._remote)


def _captures(case: support.VerificationRecoveryCase) -> tuple:
    """Land a reviewed rebase whose finish records its run and dies at the relabel; the head, and that run."""
    head = case.lands_a_reviewed_rebase()
    case.dies_routing(partial(case.finishes, head))
    return head, readings.pinned_records(case)[0]


def _reconciles(case: support.VerificationRecoveryCase) -> None:
    """Run the dispatcher's reconciliation of `case`'s recorded evidence, over the comment as it stands."""
    verification_transaction._reconciles_pending_evidence(
        case.gh, case._spec, case.issue, git_support.REVIEWING, case.gh.read_pinned_state(case.issue),
    )


# How the abandonment's write fails: the comment nobody could read again, or a
# record another road moved between that reading and the write.
_UNLANDED = (
    ("the comment would not read again", lambda _case, _original: _unreadable),
    (
        "another road moved a record under the write",
        lambda case, original: _RacesPastTheStep(original, partial(_moves_the_subject, case)),
    ),
)


class UnlandedAbandonmentTest(support.VerificationRecoveryCase, unittest.TestCase):
    """A recovery holds, with its attempt standing, until the abandonment it owes lands."""

    def test_a_failed_write_falls_back(self) -> None:
        # The abandonment's write over the comment read again fails, so it is
        # landed over the tick's own reading: the run is abandoned and the
        # rollback's road taken. With both heads put back on the landed head,
        # a later recovery and the reconciliation settle nothing.
        for failure, failing in _UNLANDED:
            with self.subTest(failure=failure):
                head, captured = self._recovers_a_rollback(failing)
                self._assert_abandoned(head, captured)
                _puts_the_remote_on(self, head)
                self._git("reset", "--quiet", "--hard", head, cwd=self._wt)

                self.recovers()
                _reconciles(self)

                self._assert_abandoned(head, captured)

    def test_an_unwritable_comment_holds(self) -> None:
        # No write to the comment lands at all, so the run cannot be
        # abandoned: nothing is reset, cleared, or parked, and the
        # reconciliation leaves the run to the attempt still standing, even
        # with the remote put back on the landed head.
        head, captured = self._recovers_a_rollback(
            lambda _case, original: original, edit=PinnedEdit.MOVED,
        )

        self.assertEqual(self._wt_head(), head)
        self.assert_held(captured)
        _puts_the_remote_on(self, head)
        _reconciles(self)
        self.assertEqual(readings.pinned_records(self)[:2], (captured, None))

    def test_a_reset_carries_its_abandonment(self) -> None:
        # The fetch fails, so the abort resets the checkout onto the anchor:
        # the run is abandoned in the write that releases the attempt, even
        # where the comment would not read again for an abandonment of its
        # own. Put back on the landed head, the checkout settles nothing.
        head, captured = _captures(self)
        with (
            patch.object(branch_transport, "_authed_fetch", return_value=_UNFETCHED),
            patch.object(verification_durable, _DURABLE_READ, side_effect=_unreadable),
        ):
            self.recovers()

        self.assertEqual(self._wt_head(), self.anchor)
        self._assert_abandoned(head, captured)
        self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
        _reconciles(self)
        self._assert_abandoned(head, captured)

    def test_an_unwritten_park_keeps_the_attempt(self) -> None:
        # The fetch fails and the write of the abort's park does not land:
        # neither the abandonment nor the attempt's release is written, so
        # the attempt still guards the run, and the reconciliation leaves it
        # be even with the checkout put back on the landed head.
        head, captured = _captures(self)
        with (
            patch.object(branch_transport, "_authed_fetch", return_value=_UNFETCHED),
            patch.object(self.gh, "write_pinned_state", side_effect=support.dies),
        ):
            self.recovers()

        self.assert_held(captured)
        self._git("reset", "--quiet", "--hard", head, cwd=self._wt)
        _reconciles(self)
        self.assertEqual(readings.pinned_records(self)[:2], (captured, None))

    def _recovers_a_rollback(self, failing, edit: PinnedEdit | None = None) -> tuple:
        """A fresh case's captured run, its remote rolled back, recovered with the comment read again as `failing` says.

        `edit` is what every strict edit of the comment answers meanwhile,
        where one is given. The head, and the run.
        """
        self.setUp()
        head, captured = _captures(self)
        _puts_the_remote_on(self, self.anchor)
        reread = failing(self, verification_durable.durable_comment)
        edits = self.gh.edit_pinned_state if edit is None else (lambda *_called, **_options: edit)
        with (
            patch.object(verification_durable, _DURABLE_READ, side_effect=reread),
            patch.object(self.gh, "edit_pinned_state", side_effect=edits),
        ):
            self.recovers()
        return head, captured

    def _assert_abandoned(self, head: str, captured) -> None:
        """`captured` abandoned and the attempt cleared, `head` announced once, and nothing pushed, launched, or run."""
        recorded = readings.pinned_records(self)
        attempt = readings.pinned(self)[readings.KEY_PENDING_PUSH]
        self.assertEqual(
            (recorded[0], recorded[2][-1], attempt),
            (None, (captured.receipt, readings.ABANDONED), None),
        )
        said = (support.announced(self), self.pushes.call_count, self.developer.call_count)
        self.assertEqual(said, ([head], 0, 0))
        self.assertEqual(self.runs(), 1)


if __name__ == "__main__":
    unittest.main()
