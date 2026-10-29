# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout a docs commit's subject is amended in, proven the issue's own around the move, over a real clone.

The amendment moves whatever branch HEAD names onto the replacement, and the
docs agent's run came between the pass's own proof and here: a tree switched
onto the flat branch at the docs commit passes every reading of that commit.
So the amendment asks once the replacement exists, immediately before HEAD is
moved, since reading the commit and building its replacement are a window of
their own. A refusal moves no branch, parks nothing, and says nothing; the
issue's own checkout is still amended.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import commands
from orchestrator.git.worktrees import creation, naming
from orchestrator.workflow.stages.documenting import subject
from orchestrator.workflow.stages.documenting.models import _DocumentingContext
from tests.git.worktrees.real_git_test_support import _RealGitWorktreeRepo, _run_git
from tests.support.fakes import FakeGitHubClient, make_issue

ISSUE = 7
PR_NUMBER = 42
_FLAT_REF = f"refs/heads/orchestrator/issue-{ISSUE}"

# The read that names a commit's headers: once for its message, once more for
# the replacement built from it.
_COMMIT_READ = ("cat-file", "commit")


class SubjectCheckoutTest(unittest.TestCase):
    """One docs commit's amendment to end in its pull request's reference."""

    def setUp(self) -> None:
        repo = _RealGitWorktreeRepo()
        repo.prepare(self)
        self.spec = repo.spec
        self.branch = naming._branch_name(repo.spec, ISSUE)
        self.worktree = creation._ensure_worktree(repo.spec, ISSUE, branch=self.branch)
        self.docs_commit = repo._commit_plan(self.worktree, "# docs\n")
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label="workflow:documenting")
        self.gh.add_issue(self.issue)
        self.gh.seed_state(ISSUE, branch=self.branch, pr_number=PR_NUMBER)
        self._reads = 0
        self._read = commands._git_hardened_bytes
        self.enterContext(patch.object(config, "PR_REF_IN_SUBJECT", True))

    def test_the_issue_s_own_checkout_is_amended(self) -> None:
        replacement = self._amends()

        self.assertNotIn(replacement, (None, self.docs_commit))
        self.assertEqual(self._tip(f"refs/heads/{self.branch}"), replacement)

    def test_a_switch_moves_no_branch(self) -> None:
        # Switched before the amendment, or while the commit is read again to
        # build the replacement: the flat branch keeps the docs commit, and
        # nothing is parked or said.
        for switched_at in (0, 2):
            with self.subTest(switched_at=switched_at):
                self.setUp()
                if not switched_at:
                    self._switch()
                read = self._read_switching_at(switched_at)
                with patch.object(commands, "_git_hardened_bytes", side_effect=read):
                    self.assertRaises(naming.BranchRefused, self._amends)

                self.assertEqual(self._tip(_FLAT_REF), self.docs_commit)
                self.assertEqual(self._tip(f"refs/heads/{self.branch}"), self.docs_commit)
                self.assertEqual(self.gh.posted_comments, [])
                self.assertIsNone(self.gh.pinned_data(ISSUE).get("park_reason"))

    def _amends(self) -> str | None:
        """The pass's amendment of its docs commit, entered over the record as it stands."""
        state = self.gh.read_pinned_state(self.issue)
        context = _DocumentingContext(self.gh, self.spec, self.issue, state, self.branch, PR_NUMBER)
        return subject._referenced_docs_commit(context, self.worktree, self.docs_commit)

    def _read_switching_at(self, switched_at: int):
        """The hardened byte read, the checkout switched onto the flat branch behind commit read `switched_at`."""

        def wrapper(*args, **kwargs):
            answer = self._read(*args, **kwargs)
            called = args[:len(_COMMIT_READ)]
            if called == _COMMIT_READ:
                self._reads += 1
                if self._reads == switched_at:
                    self._switch()
            return answer
        return wrapper

    def _switch(self) -> None:
        """Switch the checkout onto the flat branch at the docs commit."""
        _run_git("checkout", "-q", "-b", _FLAT_REF.removeprefix("refs/heads/"), cwd=self.worktree)

    def _tip(self, ref: str) -> str:
        """The commit `ref` names."""
        return _run_git("rev-parse", ref, cwd=self.worktree).strip()


if __name__ == "__main__":
    unittest.main()
