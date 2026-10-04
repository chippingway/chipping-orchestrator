# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The seed an ordinary split owes each child it creates, written under the child's own claim.

A child is dispatchable the moment its create returns, so another poller on
this host may reach it first. Inside `child_claims.claiming()` the seed is
written under the child's writer claim onto whatever record the child carries
by then, lifting the hold its missing seed earned. A child that poller still
holds is recorded and handed back unseeded, and the split's recovery repairs
it under the claim -- stopping short of it, with no park, until that poller
lets go.

No production split or recovery enters `claiming()` yet -- the last case holds
an ordinary split to the seeds it always wrote.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PINNED_STATE_MARKER
from orchestrator.workflow.stages.decomposition import (
    blocked as _blocked,
    child_claims as _child_claims,
    child_creation as _child_creation,
    recovery as _recovery,
)
from orchestrator.workflow.stages.decomposition.models import _SplitPlan
from tests.support.fakes import FakeGitHubClient, FakeIssue, make_issue
from tests.support.writer_claims import claimable, claimed_on_creation, held_elsewhere
from tests.workflow.fixtures import (
    _TEST_SPEC,
    KEY_AWAITING_HUMAN,
    KEY_PARENT_NUMBER,
    LABEL_BLOCKED,
    LABEL_DECOMPOSING,
    _agent,
)
from tests.workflow.stages.decomposition import child_claim_test_support as _support
from tests.workflow.stages.decomposition.decomposing_test_support import (
    KEY_CHILDREN,
    SPLIT_MANIFEST,
    _DecomposingWorkflowMixin,
)

_PARENT = 96

_SLICES = (
    {"title": "first slice", "body": "do the first part"},
    {"title": "second slice", "body": "do the second part"},
)


class _ParkedFirst:
    """A child create whose child another poller reaches and parks before the split seeds it.

    That poller's `blocked` handler finds no parent link on the child and
    parks it under the child's claim, which it lets go before the split asks.
    `records` keeps the pinned comment each park was written to.
    """

    def __init__(self, gh: FakeGitHubClient) -> None:
        self._gh = gh
        self._create = gh.create_child_issue
        self.records: list[int | None] = []

    def __call__(self, **fields):
        """Create the child, then park it as the other poller's handler does."""
        child = self._create(**fields)
        with held_elsewhere(self._gh.repo_id, child.number):
            _blocked._handle_empty_blocked_parent(self._gh, child, self._gh.read_pinned_state(child))
        self.records.append(self._gh.read_pinned_state(child).comment_id)
        return child


def _created(gh: FakeGitHubClient, parent: FakeIssue, plan: _SplitPlan) -> list[bool]:
    """Create and seed every planned slice inside `claiming()`, as the split's loop does."""
    state = gh.read_pinned_state(parent)
    with _child_claims.claiming():
        return [
            _child_creation._create_planned_child(gh, parent, state, plan, idx)
            for idx in range(len(plan.children_manifest))
        ]


def _recovered(gh: FakeGitHubClient, parent: FakeIssue) -> bool:
    """One claimed recovery of the parent's split, and whether it took the tick."""
    with _child_claims.claiming():
        return _recovery._recover_stale_manifest(gh, _TEST_SPEC, parent, gh.read_pinned_state(parent))


class ClaimedSeedTest(unittest.TestCase):
    """A `decomposing` parent about to create its two slices."""

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.parent = make_issue(_PARENT, label=LABEL_DECOMPOSING)
        self.github.add_issue(self.parent)
        self.plan = _SplitPlan.start(list(_SLICES), is_umbrella=False)

    def test_a_held_child_is_handed_back_unseeded(self) -> None:
        with claimed_on_creation(self.github), self.assertLogs(_support.WORKFLOW_LOG):
            created = _created(self.github, self.parent, self.plan)

        numbers = [child.number for child in self.github.created_child_issues]
        self.assertEqual(created, [True, True], "a held child is no failure")
        self.assertEqual(self.plan.unseeded, numbers, "and is handed back unseeded")
        self.assertEqual(self.github.pinned_data(_PARENT)[KEY_CHILDREN], numbers, "both are recorded")
        self.assertEqual(self._records(), [{}, {}], "neither is written")

    def test_the_recovery_seeds_it_once_let_go(self) -> None:
        with claimed_on_creation(self.github):
            with self.assertLogs(_support.WORKFLOW_LOG):
                _created(self.github, self.parent, self.plan)
            with self.assertLogs(_support.WORKFLOW_LOG):
                self.assertTrue(_recovered(self.github, self.parent))

            self.assertEqual(self._records(), [{}, {}], "the recovery waits on them")
            self.assertEqual(self.github.label_history, [], "and does not finalize past them")
            self.assertIsNone(self.github.pinned_data(_PARENT).get(KEY_AWAITING_HUMAN), "nothing parks")

        self.assertTrue(_recovered(self.github, self.parent))

        self.assertEqual(self._parent_links(), [_PARENT, _PARENT])
        self.assertEqual(self.github.label_history, [(_PARENT, LABEL_BLOCKED)])

    def test_the_seed_lands_on_the_held_record(self) -> None:
        # One pinned comment, the one every reader takes, carrying the seed
        # and none of the park the missing seed earned.
        parked_first = _ParkedFirst(self.github)
        with patch.object(self.github, "create_child_issue", parked_first):
            _created(self.github, self.parent, self.plan)

        self.assertEqual(self.plan.unseeded, [])
        for child, parked in zip(self.github.created_child_issues, parked_first.records, strict=True):
            records = [comment.id for comment in child.comments if PINNED_STATE_MARKER in comment.body]
            seed = self.github.read_pinned_state(child)
            self.assertEqual(records, [parked], f"#{child.number} carries the one record it was parked on")
            self.assertEqual(seed.comment_id, parked)
            self.assertEqual(seed.get(KEY_PARENT_NUMBER), _PARENT)
            self.assertFalse(seed.get(KEY_AWAITING_HUMAN), "the park its missing seed earned is lifted")

    def test_a_failed_seed_gives_the_claim_back(self) -> None:
        refused = _support.RefusedWrite(self.github, self.github.write_pinned_state, _PARENT)
        one_slice = _SplitPlan.start([_SLICES[0]], is_umbrella=False)

        with patch.object(self.github, "write_pinned_state", refused), self.assertLogs(_support.WORKFLOW_LOG):
            seeded = _created(self.github, self.parent, one_slice)

        first = self.github.created_child_issues[0].number
        self.assertEqual(seeded, [False])
        self.assertEqual(refused.claimable_during, [False], "the seed is written under the child's claim")
        self.assertTrue(self.github.pinned_data(_PARENT)[KEY_AWAITING_HUMAN], "the parent is parked naming it")
        self.assertTrue(claimable(self.github.repo_id, first), "and the child's claim is given back")

    def _records(self) -> list[dict]:
        """What each created child's pinned record carries, in creation order."""
        return [self.github.pinned_data(child.number) for child in self.github.created_child_issues]

    def _parent_links(self) -> list:
        """The parent each created child's record names."""
        return [record.get(KEY_PARENT_NUMBER) for record in self._records()]


class OrdinarySplitTest(unittest.TestCase, _DecomposingWorkflowMixin):
    """What a split does today, outside `claiming()`."""

    def test_a_split_seeds_past_a_held_child(self) -> None:
        # No production split enters `claiming()`: each child is seeded fresh
        # and the parent finalized, whoever else holds the children.
        github = FakeGitHubClient()
        parent = make_issue(_PARENT, label=LABEL_DECOMPOSING)
        github.add_issue(parent)

        with claimed_on_creation(github):
            self._run_decomposing(github, parent, run_agent=_agent(last_message=SPLIT_MANIFEST))

        seeds = [github.pinned_data(child.number) for child in github.created_child_issues]
        self.assertEqual({seed.get(KEY_PARENT_NUMBER) for seed in seeds}, {_PARENT})
        self.assertIn((_PARENT, LABEL_BLOCKED), github.label_history)


if __name__ == "__main__":
    unittest.main()
