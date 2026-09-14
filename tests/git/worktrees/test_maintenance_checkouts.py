# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Checked-out branches survive maintenance, including incomplete listings."""
from __future__ import annotations

from unittest.mock import patch

from orchestrator.git.worktrees import (
    checkout_listing as _checkout_listing,
    maintenance_results as _maintenance_results,
)
from tests.git.worktrees import (
    maintenance_payloads as _maintenance_payloads,
    maintenance_test_support as _support,
)
from tests.git.worktrees.candidate_host_test_support import _unlink_backlink
from tests.support.git import (
    _run_git,
)


class CheckedOutBranchTest(_support._MaintenanceTestCase):
    """A branch some tree of the clone is standing on is never deleted.

    The safety `update-ref -d` gives up for its commit pin. The trees that can
    be on a branch are not only the ones a scan names: an operator adding a
    worktree to look at a finished branch is standing on it just as squarely,
    and nothing about the per-issue paths would ever report that.
    """

    def test_a_worktree_elsewhere_keeps_the_branch(self) -> None:
        self.landed()
        inspected = self.world.checkout_at(
            self.spec, self.world.path(_maintenance_payloads.INSPECTED_DIR), self.branch,
        )

        swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.BRANCH_CHECKED_OUT)
        self.assertEqual(swept.subject, self.branch)
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(
            _run_git("rev-parse", "--verify", "HEAD", cwd=inspected).returncode,
            0,
        )

    def test_a_worktree_git_dropped_keeps_the_branch(self) -> None:
        # `worktree list` passes over a linked worktree whose backlink is
        # missing -- exit zero, nothing on stderr, one fewer worktree -- while
        # that tree goes on working and goes on holding its branch. The listing
        # is counted against the clone's own entries for exactly this.
        self.landed()
        dropped = self.world.checkout_at(
            self.spec, self.world.path(_maintenance_payloads.INSPECTED_DIR), self.branch,
        )
        _unlink_backlink(dropped)

        with self.assertLogs(_support.LIFECYCLE_LOGGER, level=_maintenance_payloads.WARNING):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_UNREADABLE)
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(
            _run_git("rev-parse", "--verify", "HEAD", cwd=dropped).returncode,
            0,
        )

    def test_a_listing_that_failed_keeps_the_branch(self) -> None:
        # Without it nothing establishes that no tree is standing on the ref,
        # which is the one thing this read is spent on.
        self.landed()

        with patch.object(
            _checkout_listing, "_checked_out_branches", return_value=None,
        ):
            swept = self.only_result()

        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.TIP_UNREADABLE)
        self.assertEqual(self.local_branches(), self.only_branch)
