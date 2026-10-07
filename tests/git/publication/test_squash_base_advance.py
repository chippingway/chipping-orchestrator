# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pre-tick base refresh, over a branch a squash is mid-way through.

The refresh runs ahead of every handler, so it is the one thing that can move
a branch between the tick that collapsed it and the tick that would finish the
publication. A collapse is proved by the tree the commit on the branch carries
-- a squash rewinds with the index intact and commits again, so the object it
makes has the tree of the head it replaced, exactly -- and a rebase replaces
that with a commit carrying the base advance too. Rebased inside the window,
the recovery refuses and the pull request is left standing on the history the
record says was collapsed, with the rebase already force-pushed over it.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.workflow.engine import base_refresh as _base_refresh, base_rewrite as _base_rewrite
from tests.git.publication import squash_git_support as squash_support
from tests.git.publication.squash_recovery_support import (
    APPROVED_COMMITS,
    SquashRecoveryMixin,
)

# The PR-aware coordinator every rebase and force-push of a published branch
# goes through, which is what the freeze has to keep out of reach.
SYNC_PR_WORKTREE = "_sync_pr_worktree_to_base"


class BaseAdvanceRealGitTest(
    SquashRecoveryMixin,
    squash_support.SquashGitFixtureMixin,
    unittest.TestCase,
):
    """The refresh that runs ahead of every handler, over a branch mid-squash.

    A collapse is proved by the tree the commit on the branch carries: a
    squash rewinds with the index intact and commits again, so the object it
    makes has the tree of the head it replaced, exactly. A rebase destroys
    exactly that -- the collapse becomes a commit carrying the base advance
    too -- so the recovery refuses, and the pull request is left standing on
    the history the record says was collapsed with the rebase already
    force-pushed over it.
    """

    def test_a_recorded_collapse_is_not_rebased(self) -> None:
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        squashed = self._head_sha()
        self._advances_the_base()
        rebased = MagicMock()

        with patch.object(_base_rewrite, SYNC_PR_WORKTREE, rebased):
            _base_refresh._sync_worktree_with_base(
                gate.gh, gate.spec, self.work, gate.issue.number,
            )

        rebased.assert_not_called()
        self.assertEqual(self._head_sha(), squashed)

    def test_the_collapse_is_still_publishable(self) -> None:
        # What the freeze buys: the tree the record was written about is still
        # the tree on the branch, so the recovery finishes rather than refuses.
        gate = self._gate_subject()
        self._crashes_after_the_commit(gate)
        self._advances_the_base()

        with patch.object(_base_rewrite, SYNC_PR_WORKTREE, MagicMock()):
            _base_refresh._sync_worktree_with_base(
                gate.gh, gate.spec, self.work, gate.issue.number,
            )
        squash_run = self._squashes(self._next_tick(gate))

        self.assertTrue(squash_run.success)
        self.assertEqual(squash_run.count, APPROVED_COMMITS)


if __name__ == "__main__":
    unittest.main()
