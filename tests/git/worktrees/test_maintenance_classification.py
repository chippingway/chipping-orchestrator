# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Maintenance preserves candidates refused by artifact classification."""
from __future__ import annotations

from orchestrator.git.worktrees import (
    maintenance,
    maintenance_results as _maintenance_results,
)
from orchestrator.git.worktrees.models import RetentionReason
from tests.git.worktrees import (
    maintenance_payloads as _maintenance_payloads,
    maintenance_test_support as _support,
)
from tests.git.worktrees.candidate_refs import _track_file
from tests.git.worktrees.eligibility_test_support import (
    OPEN_PR_STATE,
    _github,
    _pull_request,
    _terminal_issue,
)


class RetainedByClassificationTest(_support._MaintenanceTestCase):
    """A candidate the classification keeps is reported with its own reasons."""

    def assert_kept_for(self, swept, reason: RetentionReason) -> None:
        """The pass reports the classification's answer, in its vocabulary."""
        self.assertEqual(swept.outcome, _maintenance_results.MaintenanceOutcome.RETAINED)
        self.assertEqual(swept.reason, _maintenance_results.MaintenanceReason.UNPROVEN)
        self.assertEqual(
            tuple(kept.reason for kept in swept.retentions), (reason,),
        )
        self.assertEqual(swept.subject, swept.retentions[0].subject)

    def test_a_dirty_tree_keeps_the_whole_candidate(self) -> None:
        self.landed()
        worktree = self.settled_checkout()
        (worktree / _maintenance_payloads.LOOSE_FILE).write_text(_maintenance_payloads.LOOSE_CONTENT)

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.WORKTREE_DIRTY)
        self.assertTrue(worktree.exists())
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_a_tree_hiding_files_keeps_it(self) -> None:
        # `worktree remove` would take these down without a word, which is why
        # the classification asks about them and the pass never gets a proof.
        _track_file(self.clone, _maintenance_payloads.IGNORE_FILE, f"{_maintenance_payloads.HIDDEN_FILE}\n")
        self.landed()
        worktree = self.settled_checkout()
        (worktree / _maintenance_payloads.HIDDEN_FILE).write_text(_maintenance_payloads.HIDDEN_CONTENT)

        with self.assertLogs(maintenance.log.name, level=_maintenance_payloads.INFO_LEVEL):
            swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.WORKTREE_IGNORED)
        self.assertTrue((worktree / _maintenance_payloads.HIDDEN_FILE).exists())

    def test_an_open_pull_request_keeps_the_branches(self) -> None:
        tip = self.landed()
        self.gh.existing_open_pr[self.branch] = _pull_request(
            _maintenance_payloads.PR_NUMBER, self.branch, tip, state=OPEN_PR_STATE,
        )

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.OPEN_PULL_REQUEST)
        self.assertEqual(self.remote_branches(), self.only_branch)

    def test_an_issue_that_has_not_ended_keeps_it(self) -> None:
        self.landed()
        self.gh = _github(_terminal_issue(
            closed=False, label_names=(_maintenance_payloads.IMPLEMENTING_LABEL,),
        ))

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.ISSUE_OPEN)
        self.assertEqual(self.local_branches(), self.only_branch)

    def test_an_unaccounted_commit_keeps_it(self) -> None:
        # Published, never merged, and no pull request carries it: the one copy
        # of that work is the branch this pass was asked about.
        self.published()

        swept = self.only_result()

        self.assert_kept_for(swept, RetentionReason.UNACCOUNTED_COMMITS)
        self.assertEqual(self.remote_branches(), self.only_branch)
