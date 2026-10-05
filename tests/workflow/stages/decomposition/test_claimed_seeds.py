# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The seed an ordinary split owes each child it creates, written under the child's own claim.

A child is dispatchable the moment its create returns, so the seed is written
under the child's writer claim. A seed write that fails parks the parent
naming the child and gives that claim back, so the child is not left held by a
split that has stopped writing it.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.workflow.stages.decomposition import child_creation as _child_creation
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.writer_claims import claimable
from tests.workflow.fixtures import KEY_AWAITING_HUMAN, LABEL_DECOMPOSING
from tests.workflow.stages.decomposition import child_claim_test_support as _support

_PARENT = 96


class ClaimedSeedTest(unittest.TestCase):
    """A `decomposing` parent about to create its one slice."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.parent = make_issue(_PARENT, label=LABEL_DECOMPOSING)
        self.github.add_issue(self.parent)

    def test_a_failed_seed_gives_the_claim_back(self) -> None:
        refused = _support.RefusedWrite(self.github, self.github.write_pinned_state, _PARENT)
        plan = _SplitPlan.start([{"title": "first slice", "body": "do the first part"}], is_umbrella=False)
        state = self.github.read_pinned_state(self.parent)

        with patch.object(self.github, "write_pinned_state", refused), self.assertLogs(_support.WORKFLOW_LOG):
            seeded = _child_creation._create_planned_child(self.github, self.parent, state, plan, 0)

        first = self.github.created_child_issues[0].number
        self.assertFalse(seeded)
        self.assertEqual(refused.claimable_during, [False], "the seed is written under the child's claim")
        self.assertTrue(self.github.pinned_data(_PARENT)[KEY_AWAITING_HUMAN], "the parent is parked naming it")
        self.assertTrue(claimable(self.github.repo_id, first), "and the child's claim is given back")


if __name__ == "__main__":
    unittest.main()
