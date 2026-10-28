# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A waiting change request over a record or checkout no live work may use is finished by no tick.

Both recoveries admit the branch and the checkout the developer would be
handed before their first write (`review_handoffs.HandedLaunch.of`): a
validating tick relabelling a request whose relabel was refused, and a fixing
tick writing a cleared feedback anchor back ahead of the launch it owes. A
record pinning the flat branch, and a checkout at the issue's path that is not
proven the issue's own -- refuted or unreadable -- each refuse
(`naming.BranchRefused`) with the label, the pinned comment, and the pull
request's thread exactly as they read.
"""
from __future__ import annotations

import unittest

from orchestrator.git.worktrees import models as _worktree_models, naming as _naming
from tests.workflow.stages.validating import (
    resumed_verdict_test_support as _resumed,
    review_verdict_test_support as _world,
)

_PROVEN = _worktree_models.ProbeAnswer.CONFIRMED

# How the issue refuses: the branch its record pins, None leaving the current
# one, and what the ownership read answers for the checkout at its path.
_REFUSALS = (
    ("a flat pin", f"orchestrator/issue-{_world.ISSUE}", _PROVEN),
    ("a refuted checkout", None, _worktree_models.ProbeAnswer.REFUTED),
    ("an unreadable checkout", None, _worktree_models.ProbeAnswer.UNREADABLE),
)


def _pins(case, branch: str | None) -> None:
    """Pin `branch` on the issue's record, where the case names one."""
    if branch is not None:
        state = case.github.read_pinned_state(case.issue)
        state.set("branch", branch)
        case.github.write_pinned_state(case.issue, state)


def _as_it_reads(case) -> tuple:
    """The pinned comment, the label history, and the feedback posts, as one reading."""
    labels = tuple(case.github.label_history)
    return case.pinned(), labels, len(case.feedback_posts())


class RefusedRecoveryTest(_resumed.ResumedVerdictWorld, unittest.TestCase):
    """A handed request's recovery, over a record or checkout the developer may not be handed."""

    def test_a_refused_relabel_is_never_retried(self) -> None:
        # The tick handing the request over died on its relabel, so its
        # feedback is posted and the request handed. The validating tick
        # finishing it refuses ahead of the relabel and the launch.
        for name, branch, identity in _REFUSALS:
            with self.subTest(name):
                self.setUp()
                _resumed.refuses_the_relabel(self)
                _pins(self, branch)
                before = _as_it_reads(self)

                with self.assertRaises(_naming.BranchRefused):
                    self.validates(checkout_identity=identity)

                self.assertEqual(_as_it_reads(self), before)

    def test_a_cleared_anchor_is_never_written_back(self) -> None:
        # The launch a handed request owes is still owed, and its pinned
        # feedback anchor was cleared. The fixing tick refuses ahead of the
        # commit that would write the anchor back, so the comment keeps it
        # cleared.
        for name, branch, identity in _REFUSALS:
            with self.subTest(name):
                self.setUp()
                self.hands_over_unstarted()
                _resumed.clears_the_anchor(self)
                _pins(self, branch)
                before = _as_it_reads(self)

                with self.assertRaises(_naming.BranchRefused):
                    self.fixes(checkout_identity=identity)

                self.assertEqual(_as_it_reads(self), before)


if __name__ == "__main__":
    unittest.main()
