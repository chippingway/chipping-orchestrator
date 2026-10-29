# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The worktree window the durable record of a collapse opens.

Every reading the squash takes before it rewrites anything -- the planning
probes, and the entry's own proof of the tree and the head -- happens before
the terms of the collapse go onto the pinned comment. That write is a request,
so the worktree is writable for the whole of it, and what the rewrite behind
it commits is the INDEX rather than the plan: a `--soft` reset keeps whatever
is staged, and the commit that follows carries it.

Left unchecked, a change staged in that window is collapsed into the squash
and force-pushed onto the pull request as work a reviewer approved. So the
checkout is proved again once the write comes back, and both halves are
proved: a tree that is no longer provably clean, and a head something moved.
A tree switched onto the flat branch at the planned head, clean, passes both,
so the checkout is proven the issue's own last of all, before the reset -- and
again between the reset and the commit, since a tree switched while the reset
runs would have the staged collapse committed onto its branch.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git import commands
from orchestrator.git.worktrees import evidence as _evidence, naming
from orchestrator.git.worktrees.models import ProbeAnswer
from tests.git.publication import squash_git_support as squash_support
from tests.git.publication.squash_race_doubles import RACED_FILE, _RacesTheRecord
from tests.git.publication.squash_recovery_support import (
    APPROVED_COMMITS,
    BRANCH_INTACT,
    BRANCH_UNKNOWN,
    KEY_COLLAPSE_HEAD,
    SquashRecoveryMixin,
)

_FLAT_BRANCH = f"orchestrator/issue-{squash_support.SQUASH_ISSUE_NUMBER}"

# The rewrite's own first step, behind which the collapse is staged in the index.
_SOFT_RESET = ("reset", "--soft")


class RecordRaceRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """What arrives between the record of a collapse and the collapse."""

    def test_a_staged_change_is_never_collapsed_in(self) -> None:
        gate = self._gate_subject()
        accepted = self._head_sha()
        racing = _RacesTheRecord(self, gate)

        with racing.held():
            squash_run = self._squashes(gate)

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        # The approved commits are exactly where the plan left them, and the
        # edit survives as the uncommitted change it was.
        self.assertEqual(self._head_sha(), accepted)
        self._assert_branch_carries(APPROVED_COMMITS)
        self.assertTrue((self.work / RACED_FILE).exists())

    def test_an_untouched_branch_says_so(self) -> None:
        # Nothing was rewritten, so the notice may say the approved commits
        # are where a human squashing by hand will find them -- and the record
        # of a collapse that did not happen goes with the refusal.
        gate = self._gate_subject()
        racing = _RacesTheRecord(self, gate)

        with racing.held():
            squash_run = self._squashes(gate)

        self.assertEqual(squash_run.standing, BRANCH_INTACT)
        self.assertNotIn(KEY_COLLAPSE_HEAD, gate.state.data)

    def test_a_moved_head_is_never_published(self) -> None:
        # The sharper half of the same window: something committed over the
        # checkout, so the plan was taken over a head the branch has left and
        # the squash would publish a commit nobody here can account for.
        gate = self._gate_subject()
        racing = _RacesTheRecord(self, gate, commits=True)

        with racing.held():
            squash_run = self._squashes(gate)

        self.assertIsNotNone(squash_run.error)
        squash_run.push_mock.assert_not_called()
        self._assert_branch_carries(APPROVED_COMMITS + 1)
        # Nothing was rewritten and the record saying otherwise has just been
        # dropped, so neither place may be named: an operator sent to HEAD
        # would find a commit this tick never accounted for, and one sent to
        # the reflog would find no collapse at all.
        self.assertEqual(squash_run.standing, BRANCH_UNKNOWN)

    def test_a_flat_switch_collapses_nothing(self) -> None:
        # The tree is switched onto the flat branch at the planned head, clean,
        # so the tree and head proofs both pass -- and the soft reset would
        # collapse that branch's history. Proven the issue's own last, it is
        # refused with nothing rewritten, and the record stands exactly as a
        # process that died before the reset leaves it.
        gate = self._gate_subject()
        accepted = self._head_sha()
        self._writes = gate.gh.write_pinned_state

        with patch.object(gate.gh, "write_pinned_state", side_effect=self._switched_write):
            self.assertRaises(naming.BranchRefused, self._squashes, gate)

        self.assertEqual(self._head_sha(), accepted)
        self._assert_branch_carries(APPROVED_COMMITS)
        self.assertIn(KEY_COLLAPSE_HEAD, self._pinned(gate))

    def test_a_switch_mid_soft_reset_commits_nothing(self) -> None:
        # The soft reset lands on the issue's branch, and the tree is switched
        # onto the flat branch while it runs, the collapse staged in its index.
        # The commit behind it would land on that branch, so the checkout is
        # proven again first: nothing is committed, the switched tree keeps its
        # staged collapse, and the record stands for the recovery.
        gate = self._gate_subject()
        self._hardened = commands._git_hardened

        with patch.object(commands, "_git_hardened", side_effect=self._switched_reset):
            self.assertRaises(naming.BranchRefused, self._squashes, gate)

        staged = squash_support.run_git("diff", "--cached", "--name-only", cwd=self.work)
        self.assertEqual(self._head_sha(), self._switched_at)
        self.assertTrue(staged.strip())
        self.assertIn(KEY_COLLAPSE_HEAD, self._pinned(gate))

    def _switched_reset(self, *args, **kwargs):
        """Run the hardened command, switching the checkout onto the flat branch behind the soft reset."""
        answer = self._hardened(*args, **kwargs)
        called = args[:len(_SOFT_RESET)]
        if called == _SOFT_RESET:
            squash_support.run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=self.work)
            self._switched_at = self._head_sha()
            _evidence._checkout_identity.return_value = ProbeAnswer.REFUTED
        return answer

    def _switched_write(self, issue, state):
        """Land the write, then switch the checkout onto the flat branch at its head."""
        written = self._writes(issue, state)
        squash_support.run_git("checkout", "-q", "-B", _FLAT_BRANCH, cwd=self.work)
        _evidence._checkout_identity.return_value = ProbeAnswer.REFUTED
        return written


if __name__ == "__main__":
    unittest.main()
