# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real artifact evidence fixtures and timing windows for checkout activity."""
from __future__ import annotations

import time
import unittest

from orchestrator.git.worktrees import activity_evidence as _activity_evidence
from orchestrator.git.worktrees.models import BranchTip, ProbeAnswer
from tests.git.worktrees.artifact_git import BASE_BRANCH
from tests.git.worktrees.artifact_test_support import WIDGET_SLUG, _namespaced_branch, _spec
from tests.git.worktrees.candidate_host_test_support import (
    CLONE_NAME,
    _CandidateWorld,
    _settle_checkout,
)
from tests.git.worktrees.candidate_refs import _branch_at
from tests.git.worktrees.eligibility_test_support import ISSUE_NUMBER

MINUTE = 60
HOUR = 60 * MINUTE


def _named(sha: str) -> BranchTip:
    """One commit as the remote naming it, which is how a base arrives."""
    return BranchTip(answer=ProbeAnswer.CONFIRMED, sha=sha)


class _HostTestCase(unittest.TestCase):
    """A clone, its issue branch name, and the spec naming both."""

    def setUp(self) -> None:
        self.world = _CandidateWorld()
        self.world.prepare(self)
        self.clone = self.world.clone(CLONE_NAME)
        self.spec = _spec(WIDGET_SLUG, self.clone)
        self.branch = _namespaced_branch(WIDGET_SLUG, ISSUE_NUMBER)

    def commit(self) -> str:
        """Put one commit on this issue's branch."""
        return self.world.commit_on(self.clone, self.branch)


class _QuietCheckoutCase(_HostTestCase):
    """A real issue checkout with activity measured against a quiet-period window."""

    def setUp(self) -> None:
        super().setUp()
        _branch_at(self.clone, self.branch, BASE_BRANCH)
        self.worktree = self.world.attached_checkout(
            self.spec, ISSUE_NUMBER, self.branch,
        )

    def quiet(self) -> ProbeAnswer:
        """What the probe says about this checkout a minute-wide window back."""
        return _activity_evidence._quiet_checkout(self.worktree, time.time() - MINUTE)

    def settle(self) -> None:
        """Leave every trace of this checkout an hour in the past."""
        _settle_checkout(self.worktree, time.time() - HOUR)
