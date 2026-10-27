# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout the conflict stage's rebase replays, proven the issue's own again just before it.

The stage proves its checkout before it works in it, but a report settlement
and the replay record's durable write run between that proof and the rebase,
and a tree switched onto the flat branch at the same head passes every other
reading here. So the rebase asks again itself: a checkout the identity read
refutes is never replayed onto the base, whatever proved it before.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git.base_sync import pre_pr
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import evidence, naming
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.stages.conflicts import rebase
from orchestrator.workflow.stages.conflicts.models import _ConflictContext
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.repo_values import _FAKE_WT, _TEST_SPEC, FORK_POINT_SHA, HEAD_BEFORE_RUN

ISSUE = 7
PR_NUMBER = 42


class RebaseCheckoutTest(unittest.TestCase):
    """One conflict round's rebase, over a checkout the identity read refutes at the rebase."""

    def test_a_refuted_checkout_is_never_replayed(self) -> None:
        github = FakeGitHubClient()
        issue = make_issue(ISSUE, label="workflow:resolving_conflict")
        github.add_issue(issue)
        github.seed_state(ISSUE, branch=naming._branch_name(_TEST_SPEC, ISSUE), pr_number=PR_NUMBER)
        context = _ConflictContext(github, _TEST_SPEC, issue, github.read_pinned_state(issue))
        merge = MagicMock(return_value=(True, []))
        self.enterContext(patch.object(evidence, "_checkout_identity", return_value=ProbeAnswer.REFUTED))
        self.enterContext(patch.object(pre_pr, "_rebase_base_into_worktree", merge))
        self.enterContext(patch.object(_verification_probes, "_head_sha", return_value=HEAD_BEFORE_RUN))
        self.enterContext(patch.object(_publication_probes, "_fork_point", return_value=FORK_POINT_SHA))

        self.assertRaises(
            naming.BranchRefused, rebase._rebase_and_dispose, context, PR_NUMBER, 0, _FAKE_WT,
        )

        merge.assert_not_called()
        self.assertEqual((github.posted_comments, github.label_history), ([], []))


if __name__ == "__main__":
    unittest.main()
