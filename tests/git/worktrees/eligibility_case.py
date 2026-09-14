# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finished issue and its real local and remote artifacts for eligibility tests."""
from __future__ import annotations

import unittest

from orchestrator.git.worktrees import eligibility
from tests.git.worktrees.artifact_git import BASE_BRANCH
from tests.git.worktrees.artifact_test_support import WIDGET_SLUG, _namespaced_branch, _spec
from tests.git.worktrees.candidate_host_test_support import (
    CLONE_NAME,
    _CandidateWorld,
)
from tests.git.worktrees.eligibility_test_support import (
    ISSUE_NUMBER,
    _candidate,
    _github,
    _reasons,
)


class _CandidateTestCase(unittest.TestCase):
    """One finished issue on a host, and the candidate it left behind."""

    def setUp(self) -> None:
        self.world = _CandidateWorld()
        self.world.prepare(self)
        self.clone = self.world.clone(CLONE_NAME)
        self.spec = _spec(WIDGET_SLUG, self.clone)
        self.world.serve(self.spec)
        self.branch = _namespaced_branch(WIDGET_SLUG, ISSUE_NUMBER)
        self.branches = (self.branch,)
        self.gh = _github()

    def commit(self) -> str:
        """Put one commit on this issue's branch, published nowhere."""
        return self.world.commit_on(self.clone, self.branch)

    def checkout(self):
        """Add this issue's worktree, on the branch its creator leaves it on."""
        return self.world.attached_checkout(
            self.spec, ISSUE_NUMBER, self.branch,
        )

    def shapes(self, worktree) -> tuple[dict, ...]:
        """The three shapes a scan can report this candidate in."""
        return (
            {"worktree": worktree},
            {"branches": self.branches},
            {"worktree": worktree, "branches": self.branches},
        )

    def landed(self) -> str:
        """Commit on the branch and move the remote's base onto it."""
        tip = self.commit()
        self.world.publish(self.clone, BASE_BRANCH, self.branch)
        return tip

    def classify(self, **artifacts):
        """The verdict on this issue's candidate, in the shape given."""
        if not artifacts:
            artifacts = {"branches": self.branches}
        return eligibility._classify_artifacts(
            self.gh, _candidate(self.spec, ISSUE_NUMBER, **artifacts),
        )

    def kept(self, **artifacts) -> tuple[str, ...]:
        """The reasons that verdict keeps the candidate for."""
        return _reasons(self.classify(**artifacts).retentions)
