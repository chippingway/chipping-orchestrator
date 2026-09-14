# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claims and recent activity retain a candidate before mutation."""
from __future__ import annotations

import os
import time
from unittest.mock import patch

from orchestrator.git.worktrees import (
    activity_evidence as _activity_evidence,
    maintenance,
    maintenance_results as _maintenance_results,
)
from orchestrator.git.worktrees.models import ProbeAnswer
from tests.git.worktrees import (
    artifact_git as _artifact_git,
    maintenance_guard_support as _guard_support,
    maintenance_host as _maintenance_host,
    maintenance_payloads as _maintenance_payloads,
    maintenance_test_support as _support,
)
from tests.git.worktrees.eligibility_test_support import (
    ISSUE_NUMBER,
)
from tests.support.git import (
    _run_git,
)


class GuardedCandidateTest(_support._MaintenanceTestCase):
    """Everything in front of the mutation keeps the artifacts where they are."""

    def setUp(self) -> None:
        super().setUp()
        self.landed()
        self.worktree = self.settled_checkout()
        self.long_ago = time.time() - _maintenance_host.SETTLED_SECONDS

    def assert_untouched(self, swept) -> None:
        """The candidate is kept, and every artifact is still where it was."""
        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertTrue(self.worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_an_issue_being_run_is_left_alone(self) -> None:
        swept = self.only_result(claimed=_guard_support._always_claimed)

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.ACTIVE_CLAIM)
        self.assertEqual(swept.subject, f"#{ISSUE_NUMBER}")

    def test_a_guard_that_raises_is_read_as_a_claim(self) -> None:
        with self.assertLogs(maintenance.log.name, level=_maintenance_payloads.WARNING):
            swept = self.only_result(claimed=_guard_support._unanswerable_claim)

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.CLAIM_UNREADABLE)

    def test_a_checkout_touched_lately_is_left_alone(self) -> None:
        # The tree is clean and the classification clears it; what keeps it is
        # that somebody was in it moments ago.
        (self.worktree / _maintenance_payloads.LOOSE_FILE).write_text(_maintenance_payloads.LOOSE_CONTENT)
        (self.worktree / _maintenance_payloads.LOOSE_FILE).unlink()

        swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.RECENT_ACTIVITY)

    def test_a_just_committed_checkout_is_left_alone(self) -> None:
        # The tree is clean, the commit is in the base, and the directory's own
        # timestamp is old -- a commit does not move it. What keeps the
        # checkout is the index and reflog that commit rewrote.
        _run_git(
            "commit", "-q", "--allow-empty", "-m", "an agent's own round",
            cwd=self.worktree,
        )
        self.world.publish(self.clone, self.branch, self.branch)
        self.world.publish(self.clone, _artifact_git.BASE_BRANCH, self.branch)
        os.utime(self.worktree, (self.long_ago, self.long_ago))

        swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.RECENT_ACTIVITY)
        self.assertEqual(swept.subject, str(self.worktree))

    def test_an_untimeable_checkout_is_left_alone(self) -> None:
        # The last gate fails closed like every one before it: a tree nobody
        # could time is not one to delete on the strength of the reads that
        # did answer.
        with patch.object(
            _activity_evidence,
            "_quiet_checkout",
            return_value=ProbeAnswer.UNREADABLE,
        ):
            swept = self.only_result()

        self.assert_untouched(swept)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.ACTIVITY_UNREADABLE)
