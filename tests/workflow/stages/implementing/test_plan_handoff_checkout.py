# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout an accepted plan handoff moves onto its plan pull request's head, over a real clone.

The move hard-resets the tree standing at the issue's path, so the tree is
held to the issue's own branch first, and again at the reset behind the
move's fetch: one switched onto the flat branch, carrying an operator's
uncommitted edit -- before the tick or while that fetch runs -- refuses the
handoff with its head, its files, and the issue's branch exactly as they
were, and nothing launched or pushed. A discussion's park relabelled here is held to it before the
handoff is recorded, even where nobody amended the plan and no move is made:
one on the flat branch at the plan's own head refuses with the park, the plan
records, and the round anchor as they were.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.agents import runner
from orchestrator.git import branch_transport
from orchestrator.git.worktrees import naming
from orchestrator.workflow.engine import content_hash
from orchestrator.workflow.stages.implementing import handler
from tests.git.worktrees.real_git_test_support import _AmendedPlanRepo, _run_git
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue

ISSUE = 300
PR_NUMBER = 42
OPERATOR_EDIT = "operator's uncommitted work\n"
_README = "README.md"


class PlanHandoffCheckoutTest(unittest.TestCase):
    """An accepted handoff whose plan pull request humans amended, over a tree switched onto the flat branch."""

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        self.branch = naming._branch_name(self.repo.spec, ISSUE)
        self.repo.plant(self, ISSUE, self.branch)
        self.switched = False
        self._fetch = branch_transport._authed_target_fetch
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label="workflow:implementing")
        self.gh.add_issue(self.issue)
        amended = FakePRRef(sha=self.repo.amended)
        self.gh.add_pr(FakePR(number=PR_NUMBER, head_branch=self.branch, head=amended))
        self.gh.seed_state(
            ISSUE, branch=self.branch, pr_number=PR_NUMBER,
            read_only_baseline_sha=self.repo.published, discussion_plan_sha=self.repo.published,
        )

    def test_an_unmoved_plan_keeps_its_marker(self) -> None:
        # The plan pull request is back on the head the records name, so all
        # that is left is to spend the move's marker -- over a tree on the
        # flat branch, which refuses first with the marker kept.
        self._switch()
        self.gh.get_pr(PR_NUMBER).head.sha = self.repo.published
        marked = {
            "read_only_anchor_sha": self.repo.published,
            "user_content_hash": content_hash._compute_user_content_hash(self.issue, set()),
        }
        self.gh.seed_state(ISSUE, **{**self.gh.pinned_data(ISSUE), **marked})
        recorded = self.gh.pinned_data(ISSUE)

        with self.assertRaises(naming.BranchRefused):
            handler._handle_implementing(self.gh, self.repo.spec, self.issue)

        self.assertEqual(self.gh.pinned_data(ISSUE), recorded)

    def test_a_flat_checkout_keeps_its_edits(self) -> None:
        self._switch()

        self._assert_refused_and_kept()

    def test_a_switch_mid_fetch_keeps_its_edits(self) -> None:
        with patch.object(branch_transport, "_authed_target_fetch", side_effect=self._fetched):
            self._assert_refused_and_kept()

        self.assertTrue(self.switched)

    def _fetched(self, spec, branch: str):
        """The real fetch, switching the checkout onto the flat branch the first time one runs."""
        if not self.switched:
            self._switch()
        return self._fetch(spec, branch)

    def _switch(self) -> None:
        """Switch the checkout onto the flat branch at its head, with an operator's edit beside it."""
        _run_git("checkout", "-b", f"orchestrator/issue-{ISSUE}", cwd=self.repo.worktree)
        (self.repo.worktree / _README).write_text(OPERATOR_EDIT)
        self.switched = True

    def _assert_refused_and_kept(self) -> None:
        """One tick refuses the handoff: head, edit, and branch as they were, nothing launched or pushed."""
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


class ReadOnlyRelabelCheckoutTest(unittest.TestCase):
    """A discussion's published plan relabelled to implementing, over a tree on the flat branch at the plan's head."""

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        branch = naming._branch_name(self.repo.spec, ISSUE)
        self.repo.plant(self, ISSUE, branch)
        # Nobody amended the plan: the remote head is the one the round published.
        _run_git("push", "-q", "--force", "origin", branch, cwd=self.repo.spec.target_root)
        _run_git("checkout", "-q", "-b", f"orchestrator/issue-{ISSUE}", cwd=self.repo.worktree)
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label="workflow:implementing")
        self.gh.add_issue(self.issue)
        published = FakePRRef(sha=self.repo.published)
        self.gh.add_pr(FakePR(number=PR_NUMBER, head_branch=branch, head=published))
        self.gh.seed_state(
            ISSUE, branch=branch, pr_number=PR_NUMBER, awaiting_human=True,
            user_content_hash=content_hash._compute_user_content_hash(self.issue, set()),
            park_reason="discussion_plan_published", discussion_plan_path=f"plans/issue-{ISSUE}.md",
            discussion_plan_sha=self.repo.published,
            discussion_round_branch=branch, discussion_round_sha=self.repo.published,
        )

    def test_an_unchanged_plan_head_records_nothing(self) -> None:
        recorded = self.gh.pinned_data(ISSUE)
        launch = MagicMock()
        push = MagicMock(return_value=True)

        with patch.object(runner, "run_agent", launch), patch.object(branch_transport, "_push_branch", push):
            self.assertRaises(
                naming.BranchRefused, handler._handle_implementing, self.gh, self.repo.spec, self.issue,
            )

        self.assertEqual(self.gh.pinned_data(ISSUE), recorded)
        self.assertEqual((launch.call_count, push.call_count), (0, 0))


if __name__ == "__main__":
    unittest.main()
