# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Maintenance deletes only the exact artifact tips its proof names."""
from __future__ import annotations

from orchestrator.git.worktrees import (
    maintenance,
    maintenance_results as _maintenance_results,
)
from orchestrator.git.worktrees.models import ProvenTip
from tests.git.worktrees import (
    maintenance_payloads as _maintenance_payloads,
    maintenance_test_support as _support,
)
from tests.git.worktrees.artifact_test_support import _legacy_branch
from tests.git.worktrees.eligibility_test_support import ISSUE_NUMBER
from tests.support.git import _run_git


class ExactTipTest(_support._MaintenanceTestCase):
    """Nothing is deleted that is not standing exactly where it was proved.

    The proof is handed to the teardown directly here, which is the only way to
    put a case between the classification and the mutation: in production the
    two are one call, and what separates them is a push or a commit landing in
    the microseconds between.
    """

    def reclaimed(self, *proven: ProvenTip):
        """Run the teardown over this host's candidate with a stated proof."""
        candidates = self.discovered()
        self.assertEqual(len(candidates), 1)
        return maintenance._reclaimed(candidates[0], proven)

    def test_a_branch_the_remote_has_moved_is_kept(self) -> None:
        self.landed()

        swept = self.reclaimed(ProvenTip(self.branch, _maintenance_payloads.OTHER_SHA))

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_MOVED)
        self.assertEqual(swept.subject, self.branch)
        self.assertEqual(self.remote_branches(), self.only_branch)
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_moved_local_branch_survives(self) -> None:
        # The remote's copy is proved and goes; the local ref is standing on a
        # commit nobody cleared, so the pinned delete never runs.
        tip = self.landed()
        self.world.unpublish(self.clone, self.branch)
        moved = self.world.commit_on(
            self.clone, self.branch, start=self.branch,
        )

        swept = self.reclaimed(ProvenTip(self.branch, tip))

        self.assertNotEqual(moved, tip)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_MOVED)
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_checkout_that_moved_is_kept(self) -> None:
        # A worktree holds its HEAD and its own reflog, so removing it takes
        # whatever that HEAD names -- and an agent that committed since the
        # proof has moved it to something nobody cleared.
        self.landed()
        worktree = self.settled_checkout()

        swept = self.reclaimed(
            ProvenTip(str(worktree), _maintenance_payloads.OTHER_SHA),
            ProvenTip(self.branch, _maintenance_payloads.OTHER_SHA),
        )

        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_MOVED)
        self.assertEqual(swept.subject, str(worktree))
        self.assertTrue(worktree.exists())
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_checkout_switched_branches_is_kept(self) -> None:
        # Switched onto the flat branch at the very commit that was proved, the
        # checkout still matches its proof -- and is no longer the issue's own.
        # The identity is read again beside the commit, and the tree stays.
        tip = self.landed()
        worktree = self.settled_checkout()
        flat = _legacy_branch(ISSUE_NUMBER)
        _run_git("branch", flat, self.branch, cwd=self.clone)
        _run_git("checkout", "-q", flat, cwd=worktree)

        swept = self.reclaimed(
            ProvenTip(str(worktree), tip),
            ProvenTip(self.branch, tip),
        )

        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_MOVED)
        self.assertEqual(swept.subject, str(worktree))
        self.assertTrue(worktree.exists())
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_a_checkout_with_no_proof_is_kept(self) -> None:
        self.landed()
        worktree = self.settled_checkout()

        swept = self.reclaimed(ProvenTip(self.branch, _maintenance_payloads.OTHER_SHA))

        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_UNREADABLE)
        self.assertTrue(worktree.exists())

    def test_a_branch_no_proof_names_is_kept(self) -> None:
        # A branch the classification cleared nothing for: it found the name on
        # neither host, and a name that is gone at one reading can be back at
        # the next. Nothing about it was established, so nothing about it may
        # be deleted -- however plainly it is standing there now.
        self.landed()

        swept = self.reclaimed()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_UNREADABLE)
        self.assertEqual(swept.subject, self.branch)
        self.assertEqual(self.remote_branches(), self.only_branch)
        self.assertEqual(self.local_branches(), self.only_branch)
