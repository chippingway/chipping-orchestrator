# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout a docs commit's subject is amended in, proven the issue's own just before it.

The amendment moves whatever branch HEAD names onto the replacement, and the
docs agent's run came between the pass's own proof and here: a tree switched
onto the flat branch at the docs commit passes every reading of that commit.
So the amendment asks again itself, and a checkout the identity read refutes
has nothing amended, nothing parked, and nothing said.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git.publication import commits as _publication_commits
from orchestrator.git.worktrees import evidence, naming
from orchestrator.git.worktrees.models import ProbeAnswer
from orchestrator.workflow.stages.documenting import subject
from orchestrator.workflow.stages.documenting.models import _DocumentingContext
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.repo_values import _FAKE_WT, _TEST_SPEC, HEAD_AFTER_RUN

ISSUE = 7
PR_NUMBER = 42


class SubjectCheckoutTest(unittest.TestCase):
    """One docs commit's amendment, over a checkout the identity read refutes at the amendment."""

    def test_a_refuted_checkout_is_never_amended(self) -> None:
        github = FakeGitHubClient()
        issue = make_issue(ISSUE, label="workflow:documenting")
        github.add_issue(issue)
        branch = naming._branch_name(_TEST_SPEC, ISSUE)
        github.seed_state(ISSUE, branch=branch, pr_number=PR_NUMBER)
        context = _DocumentingContext(
            github, _TEST_SPEC, issue, github.read_pinned_state(issue), branch, PR_NUMBER,
        )
        amend = MagicMock()
        self.enterContext(patch.object(evidence, "_checkout_identity", return_value=ProbeAnswer.REFUTED))
        self.enterContext(patch.object(_publication_commits, "_amend_commit_message", amend))

        self.assertRaises(
            naming.BranchRefused,
            subject._amended_docs_commit, context, _FAKE_WT, HEAD_AFTER_RUN, f"docs: note (#{PR_NUMBER})\n",
        )

        amend.assert_not_called()
        self.assertEqual(github.posted_comments, [])
        self.assertIsNone(github.pinned_data(ISSUE).get("park_reason"))


if __name__ == "__main__":
    unittest.main()
