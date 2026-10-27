# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout the shared publication seam pushes from and hands on, over a real clone.

The seam proves the checkout the issue's own on entry, but the gate's reading
of the pull request comes after that proof, and a tree switched onto the flat
branch at the measured commit passes every reading of the commit and the
tree. So the push takes the proof again and refuses with nothing pushed; and
a tree switched while the push itself runs gets no handoff -- the push
stands, nothing is parked, and the claim it owes is recorded for the tick
that finds the checkout restored.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.git.worktrees import naming
from orchestrator.workflow.stages.implementing import late_push
from orchestrator.workflow.stages.implementing.late_gate_models import _Entered, _Gate
from tests.git.worktrees.real_git_test_support import _AmendedPlanRepo, _run_git
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue

ISSUE = 300
PR_NUMBER = 42
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"


def _switch(worktree) -> None:
    """Switch `worktree` onto the flat branch at the commit it stands on, the first time only."""
    if not _run_git("branch", "--list", _FLAT_BRANCH, cwd=worktree).strip():
        _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=worktree)


class PublicationCheckoutTest(unittest.TestCase):
    """One gated push of the planted commit onto the pull request the remote already carries."""

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        self.branch = naming._branch_name(self.repo.spec, ISSUE)
        self.repo.plant(self, ISSUE, self.branch)
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label="workflow:fixing")
        self.gh.add_issue(self.issue)
        amended = FakePRRef(sha=self.repo.amended)
        self.gh.add_pr(FakePR(number=PR_NUMBER, head_branch=self.branch, head=amended))
        self.gh.seed_state(ISSUE, branch=self.branch, pr_number=PR_NUMBER)
        self._read = self.gh.get_pr
        self.push = MagicMock(return_value=True)
        self.enterContext(patch.object(config, "DECOMPOSE", False))
        self.enterContext(patch.object(branch_transport, "_push_branch", self.push))

    def test_the_issue_s_own_checkout_is_published(self) -> None:
        published = self._published()

        self.assertEqual((self.push.call_count, published.landed), (1, True))

    def test_a_switch_mid_read_pushes_nothing(self) -> None:
        with patch.object(self.gh, "get_pr", side_effect=self._switched_read):
            self.assertRaises(naming.BranchRefused, self._published)

        self.assertEqual(self.push.call_count, 0)

    def test_a_switch_mid_push_hands_nothing_on(self) -> None:
        self.push.side_effect = self._switched_push

        published = self._published()

        pinned = self.gh.pinned_data(ISSUE)
        answered = (published.landed, published.held)
        self.assertEqual((self.push.call_count, answered), (1, (False, True)))
        self.assertEqual(pinned.get("late_approved_sha"), self.repo.published)
        self.assertIsNone(pinned.get("park_reason"))
        self.assertEqual(self.gh.posted_comments, [])

    def _published(self) -> late_push._PushedCandidate:
        """The seam's answer for the planted commit, entered over the head the pull request stands on."""
        repo = self.repo
        state = self.gh.read_pinned_state(self.issue)
        gate = _Gate(self.gh, repo.spec, self.issue, state, repo.worktree)
        entered = _Entered(candidate=repo.published, head=repo.amended)
        return late_push._publishes(gate, self.branch, entered)

    def _switched_read(self, number: int):
        """Read pull request `number`, switching the checkout first."""
        _switch(self.repo.worktree)
        return self._read(number)

    def _switched_push(self, *_args, **_kwargs) -> bool:
        """A push that lands while the checkout is switched under it."""
        _switch(self.repo.worktree)
        return True


if __name__ == "__main__":
    unittest.main()
