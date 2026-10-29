# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout an accepted late verdict publishes from and hands on, over a real clone.

Admission proves the checkout the issue's own before the adjudication is
settled, but the pull request reads and the exemption come after it, and a
tree switched onto the flat branch at the accepted commit stands on that
commit cleanly. So the push takes the proof again and refuses with nothing
pushed or relabelled, and the retry finding a push a dead process made
already landed refuses the handoff by the same proof: it records the
receipt that push is owed, and leaves the label, the generation, and every
park where they were.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport, push_questions
from orchestrator.git.measurement import fingerprint
from orchestrator.git.worktrees import naming
from orchestrator.workflow.late_split import overrides
from orchestrator.workflow.stages.decomposition import late_coordinator
from tests.git.worktrees.real_git_test_support import _AmendedPlanRepo, _run_git
from tests.support.fakes import FakeGitHubClient
from tests.workflow.stages.decomposition.late_published_support import published_generation, seed_published_pr
from tests.workflow.stages.decomposition.late_test_support import LATE_ISSUE_NUMBER, SPLIT_BLOCKER, seed_late_issue

_FLAT_BRANCH = f"orchestrator/issue-{LATE_ISSUE_NUMBER}"
LABEL_DECOMPOSING = "workflow:decomposing"

# Who commits on the switched checkout: an operator, named explicitly so no
# ambient git identity is needed.
_OPERATOR = ("-c", "user.name=Operator", "-c", "user.email=operator@example.invalid")


def _preparing(worktree, sent: list):
    """A push transport preparing in `worktree`, switched to the flat branch meanwhile, asking last; its sends."""

    def wrapper(*_args, **_kwargs):
        _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=worktree)
        push_questions._asks()
        sent.append(True)
        return True
    return wrapper


class AcceptedCheckoutTest(unittest.TestCase):
    """An authorized single verdict over a candidate past publication, from the tree at the issue's path."""

    def setUp(self) -> None:
        self.repo = _AmendedPlanRepo()
        self.branch = naming._branch_name(self.repo.spec, LATE_ISSUE_NUMBER)
        self.repo.plant(self, LATE_ISSUE_NUMBER, self.branch)
        self.gh = FakeGitHubClient()
        self._read = self.gh.get_pr
        self._commits_on_switch = False
        self.push = MagicMock(return_value=True)
        self.enterContext(patch.object(branch_transport, "_push_branch", self.push))

    def test_the_issue_s_own_checkout_is_published(self) -> None:
        issue = self._accepted()

        self._adjudicated(issue)

        self.assertEqual(self.push.call_count, 1)
        self.assertNotEqual(self.gh.workflow_label(issue), LABEL_DECOMPOSING)

    def test_a_switch_mid_read_pushes_nothing(self) -> None:
        # Switched while the pull request is read, or while the push transport
        # prepares in the worktree behind the last proof -- the push's own
        # question refusing it there before anything is sent: the label and
        # the generation stay on the adjudication.
        for transported in (False, True):
            with self.subTest(transported=transported):
                self.setUp()
                issue = self._accepted()
                read = self._read if transported else self._switched_read
                sent = []
                if transported:
                    self.push.side_effect = _preparing(self.repo.worktree, sent)
                with patch.object(self.gh, "get_pr", side_effect=read):
                    self.assertRaises(naming.BranchRefused, self._adjudicated, issue)

                self.assertEqual((self.push.call_count, sent), (int(transported), []))
                self.assertEqual(self.gh.workflow_label(issue), LABEL_DECOMPOSING)

    def test_a_landed_push_hands_nothing_on(self) -> None:
        # The retry finds the push a dead process made already landed, and the
        # tree is switched onto the flat branch while the pull request is read
        # -- at the accepted commit, or carrying a commit of its own, which the
        # standing proof behind would otherwise park as a moved checkout. Either
        # is refused as no checkout of the issue's own, with nothing parked.
        for commits in (False, True):
            with self.subTest(commits_on_switch=commits):
                self.setUp()
                issue = self._accepted()
                self.push.side_effect = RuntimeError("the process died inside the push")
                self.assertRaises(RuntimeError, self._adjudicated, issue)
                self.push.reset_mock(side_effect=True)
                self.pull_request.head.sha = self.repo.published
                self._commits_on_switch = commits

                with patch.object(self.gh, "get_pr", side_effect=self._switched_read):
                    self.assertRaises(naming.BranchRefused, self._adjudicated, issue)

                recorded = self.gh.pinned_data(LATE_ISSUE_NUMBER)
                self.assertEqual(self.push.call_count, 0)
                self.assertEqual(self.gh.workflow_label(issue), LABEL_DECOMPOSING)
                self.assertEqual(recorded.get("implementing_published_sha"), self.repo.published)
                self.assertEqual(recorded.get("late_cycle_id"), self.generation.cycle_id)
                self.assertIsNone(recorded.get("park_reason"))

    def _accepted(self):
        """Seed the verdict a human authorized over the planted candidate, and its pull request; the issue."""
        base = _run_git("rev-parse", "main", cwd=self.repo.spec.target_root).strip()
        generation = published_generation(candidate_sha=self.repo.published, base_sha=base)
        self.generation = generation
        self.pull_request = seed_published_pr(self.gh, head_branch=self.branch)
        issue = seed_late_issue(
            self.gh, generation, branch=self.branch, late_result_verdict="single",
            late_result_split_blocker=SPLIT_BLOCKER,
            late_run_cycle_id=generation.cycle_id, late_run_generation=generation.generation,
            late_source_sha=self.repo.published,
        )
        state = self.gh.read_pinned_state(issue)
        overrides.record_publication_override(state, overrides.LateOversizedPublication(
            candidate_sha=self.repo.published, base_sha=base,
            fingerprint=fingerprint._fingerprint_contribution(self.repo.worktree, base, self.repo.published).digest,
            additions=generation.additions, threshold=generation.threshold, comment_id=100,
        ))
        self.gh.write_pinned_state(issue, state)
        return issue

    def _adjudicated(self, issue):
        """Settle `issue`'s generation over its record as it stands; the outcome."""
        state = self.gh.read_pinned_state(issue)
        return late_coordinator._adjudicate_late_generation(self.gh, self.repo.spec, issue, state)

    def _switched_read(self, number: int):
        """Read pull request `number`, switching the checkout onto the flat branch at its head the first time."""
        worktree = self.repo.worktree
        if not _run_git("branch", "--list", _FLAT_BRANCH, cwd=worktree).strip():
            _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=worktree)
            if self._commits_on_switch:
                _run_git(*_OPERATOR, "commit", "-q", "--allow-empty", "-m", "operator work", cwd=worktree)
        return self._read(number)


if __name__ == "__main__":
    unittest.main()
