# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout the conflict stage's rebase replays, proven the issue's own again just before it.

The stage proves its checkout before it works in it, but a report settlement
and the replay record's durable write run between that proof and the rebase,
and a tree switched onto the flat branch at the same head passes every other
reading here. So the rebase asks again itself: a checkout switched while the
replay record is written is never replayed onto the base, and the record the
write left stands for the tick that finds the checkout restored.
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

# What the replay record names: the head the rebase replaces, and the pull
# request it is made against.
_REPLAY_FROM = "conflict_replay_from_sha"
_REPLAY_PR = "conflict_replay_pr_number"


class RebaseCheckoutTest(unittest.TestCase):
    """One conflict round's rebase of the head this issue exempts, which writes its replay record first."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label="workflow:resolving_conflict")
        self.github.add_issue(self.issue)
        self.github.seed_state(
            ISSUE, branch=naming._branch_name(_TEST_SPEC, ISSUE), pr_number=PR_NUMBER,
            late_exempt_sha=HEAD_BEFORE_RUN,
        )
        self.identity = MagicMock(return_value=ProbeAnswer.CONFIRMED)
        self.merge = MagicMock(return_value=(True, []))
        self._write = self.github.write_pinned_state
        self.enterContext(patch.object(evidence, "_checkout_identity", self.identity))
        self.enterContext(patch.object(pre_pr, "_rebase_base_into_worktree", self.merge))
        self.enterContext(patch.object(_verification_probes, "_head_sha", return_value=HEAD_BEFORE_RUN))
        self.enterContext(patch.object(_publication_probes, "_fork_point", return_value=FORK_POINT_SHA))

    def test_a_switch_at_the_replay_record_is_refused(self) -> None:
        state = self.github.read_pinned_state(self.issue)
        context = _ConflictContext(self.github, _TEST_SPEC, self.issue, state)

        with patch.object(self.github, "write_pinned_state", side_effect=self._switched_write):
            self.assertRaises(
                naming.BranchRefused, rebase._rebase_and_dispose, context, PR_NUMBER, 0, _FAKE_WT,
            )

        recorded = self.github.pinned_data(ISSUE)
        self.merge.assert_not_called()
        self.assertEqual(recorded.get(_REPLAY_FROM), HEAD_BEFORE_RUN)
        self.assertEqual(recorded.get(_REPLAY_PR), PR_NUMBER)
        self.assertEqual((self.github.posted_comments, self.github.label_history), ([], []))

    def _switched_write(self, issue, state):
        """Land the write, the checkout switched off the issue's branch behind the one recording the replay."""
        written = self._write(issue, state)
        if state.get(_REPLAY_FROM):
            self.identity.return_value = ProbeAnswer.REFUTED
        return written


if __name__ == "__main__":
    unittest.main()
