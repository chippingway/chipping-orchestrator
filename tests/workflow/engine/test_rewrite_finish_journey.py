# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A base rewrite of a pull request in review, walked on through its report refresh to a fresh reviewer.

The squash-rebase journey (`squash_rebase_journey_support`): an approved report
squashed and carried onto `SQUASHED`, documented, and put in review, when the
base moves and a whole base refresh rebases the squash onto `REBASED`. The
evidence carried onto the squash answers for a review of the approved commit,
which the rebased head's report refresh replaces. So the finish records nothing
for the rebased head: where the rebase moved the tree, it invalidates that
evidence before the relabel, and where the tree is the one tested, it leaves it
where it stands. Either way the developer is asked for the rebased head's
report, the reviewer handed that report is handed no evidence and told to run
the verification itself, and the evidence that then becomes current is that
reviewer's own, bound to the refreshed report about the rebased head.
"""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    review_subjects as _review_subjects,
    verification_settlement_state as _settlement,
)
from tests.workflow.engine import rewrite_finish_readings as readings
from tests.workflow.git_owners import seam_patch
from tests.workflow.stages.validating import (
    review_verdict_test_support as _world,
    squash_rebase_journey_support as _journey,
)

# The tree the rebase of the squash reads as where the base it moved onto
# changed what the branch carries.
_REBASED_TREE = "d670460b4b4aece5915caf5c68d12f560a9fe3e4"

# What the reviewer of the rebased head is told where no evidence covers it.
_RUN_IT_YOURSELF = (
    "No current workflow verification evidence covers this subject, so run the verification yourself."
)

_HANDED_EVIDENCE = "Workflow verification evidence (revision"


class _MovedTree:
    """The tree each commit reads as once the base moved: the rebased head's own, every other the tested one."""

    def __call__(self, _worktree, revision: str) -> str:
        return _REBASED_TREE if revision == _journey.REBASED else _world.TREE


class RewriteToFreshReviewTest(_journey._SquashRebaseJourney, unittest.TestCase):
    """The rebased head's evidence is invalidated or deferred at its finish, and its reviewer verifies afresh."""

    def test_a_moved_tree_invalidates_the_carry(self) -> None:
        # The carry is history before the issue is back on `validating`, so
        # nothing about the approved commit stands current beside the rebase.
        self.walks_into_review()
        carried = self._current()
        with seam_patch("_tree_sha", _MovedTree()):
            self.base_refresh(_journey.REBASED, checkout_tree=None)

        pending, current, retired = self._finished()
        self.assertEqual(
            (pending, current, retired[-1]),
            (None, None, (carried.receipt, "invalidated")),
        )
        self._reviewed_afresh()

    def test_an_exact_tree_defers_the_carry(self) -> None:
        # The carry stands where it was, still about the approved commit's
        # review, which is no subject the rebased head's reviewer is handed.
        self.walks_into_review()
        carried = self._current()
        self.base_refresh(_journey.REBASED)

        self.assertEqual(self._finished()[:2], (None, carried))
        self._reviewed_afresh()

    def _current(self):
        """The current evidence the pinned comment carries now."""
        return _settlement.read_current_evidence(self.github.read_pinned_state(self.issue))

    def _finished(self) -> tuple:
        """What the base refresh's finish left: `validating`, and the evidence records (`readings.records`)."""
        self.assertEqual(self.github.workflow_label(self.issue), "workflow:validating")
        return readings.records(self.github.pinned_data(self.issue.number))

    def _reviewed_afresh(self) -> None:
        """Refresh the report, then review: the reviewer is told to verify, and its own run becomes current.

        The current evidence is the reviewer's run of the rebased head, bound
        to the approved review of the refreshed report about that head.
        """
        self.dispatched(_journey.refresh())
        self.approved_into_review(_journey.REBASED)
        reviewed = self.spawned(_journey.REVIEWER)
        self.assertEqual(len(reviewed), 1)
        self.assertIn(_RUN_IT_YOURSELF, reviewed[0])
        self.assertNotIn(_HANDED_EVIDENCE, reviewed[0])
        binding = self._current().binding
        approved = self.github.pinned_data(self.issue.number)[_review_subjects.APPROVED_SUBJECT]
        self.assertEqual(
            (binding.tested_sha, binding.target.target_head, binding.target.subject),
            (_journey.REBASED, _journey.REBASED, approved),
        )
        self.assertEqual(_review_subjects.ReviewSubject.commit_recorded_in(approved), _journey.REBASED)


if __name__ == "__main__":
    unittest.main()
