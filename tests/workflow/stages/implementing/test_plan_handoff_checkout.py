# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout an accepted plan handoff moves onto its plan pull request's head, over a real clone.

The move hard-resets the tree standing at the issue's path, so the tree is
held to the issue's own branch first: one switched onto the flat branch,
carrying an operator's uncommitted edit, refuses the handoff with its head,
its files, and the issue's branch exactly as they were, and nothing launched
or pushed.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.agents import runner
from orchestrator.git import branch_transport
from orchestrator.git.worktrees import naming
from orchestrator.workflow.stages.implementing import handler
from tests.git.worktrees.real_git_test_support import _AmendedPlanRepo, _run_git
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue

ISSUE = 300
PR_NUMBER = 42
OPERATOR_EDIT = "operator's uncommitted work\n"
_README = "README.md"


class PlanHandoffCheckoutTest(unittest.TestCase):
    """An accepted handoff whose plan pull request humans amended, over a tree on the flat branch."""

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        self.branch = naming._branch_name(self.repo.spec, ISSUE)
        self.repo.plant(self, ISSUE, self.branch)
        _run_git("checkout", "-b", f"orchestrator/issue-{ISSUE}", cwd=self.repo.worktree)
        (self.repo.worktree / _README).write_text(OPERATOR_EDIT)
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label="workflow:implementing")
        self.gh.add_issue(self.issue)
        amended = FakePRRef(sha=self.repo.amended)
        self.gh.add_pr(FakePR(number=PR_NUMBER, head_branch=self.branch, head=amended))
        self.gh.seed_state(
            ISSUE, branch=self.branch, pr_number=PR_NUMBER,
            read_only_baseline_sha=self.repo.published, discussion_plan_sha=self.repo.published,
        )

    def test_a_flat_checkout_keeps_its_edits(self) -> None:
        before = self.repo.head_of(self.repo.worktree)
        launch = MagicMock()
        push = MagicMock(return_value=True)

        with patch.object(runner, "run_agent", launch), patch.object(branch_transport, "_push_branch", push):
            self.assertRaises(
                naming.BranchRefused, handler._handle_implementing, self.gh, self.repo.spec, self.issue,
            )

        self.assertEqual(self.repo.head_of(self.repo.worktree), before)
        self.assertEqual((self.repo.worktree / _README).read_text(), OPERATOR_EDIT)
        self.assertEqual(self.repo.branch_tip(self.branch), self.repo.published)
        self.assertEqual((launch.call_count, push.call_count), (0, 0))


if __name__ == "__main__":
    unittest.main()
