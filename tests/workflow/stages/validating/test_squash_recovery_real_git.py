# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One validating tick over a checkout a squash was interrupted inside.

A collapse stopped between the reset and the commit leaves a checkout with
nothing over its base and every change it was about in the index -- and a
stage that prepares such a checkout the ordinary way force-removes it, since
the reuse probe asks for unpushed COMMITS and there are none. What that takes
with it is the staged collapse, the tree a human was asked to reconcile, and
whatever repair they had staged.

So the checkout is real and the tick is the real handler over it
(`squash_recovery_git_support`).

The park that recovery takes is a guarded commit over the comment read
afresh: another road's own write right ahead of it is kept beside the park,
and one GitHub takes and never confirms reports no human wait, while the next
tick finds the park standing and mentions nobody again.
"""
from __future__ import annotations

import unittest

from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.late_split import collapses as _collapses
from tests.workflow.stages.validating import (
    approval_commit_test_support as _one,
    review_write_test_support as _roads,
)
from tests.workflow.stages.validating.squash_recovery_git_support import HalfMadeCollapseWorld
from tests.workflow.stages.validating.squash_tick_git_support import APPROVED_COMMITS, ISSUE_NUMBER, run_git

LABEL_DOCUMENTING = "workflow:documenting"

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"

PARK_SQUASH_FAILED = "squash_failed"

# What the park says about a branch standing mid-rewrite, which is what sends
# an operator to the reflog rather than to HEAD for the approved commits.
LEFT_COLLAPSED = "the branch is NOT standing on the commits the reviewer"

# A note another road leaves on the pinned comment, which no write here owns.
THEIR_NOTE = "another_road_note"

# The park's own write: the guarded commit staging the reason this recovery parks under.
_THE_PARK = _one.staging(PARK_REASON, PARK_SQUASH_FAILED)


class HalfMadeCollapseRealGitTest(HalfMadeCollapseWorld, unittest.TestCase):
    """A tick that comes back to a branch rewound and not yet recommitted."""

    def test_a_rewound_checkout_is_not_rebuilt(self) -> None:
        # The reset landed and the commit did not, so the reuse probe an
        # ordinary preparation gates on answers "no unpushed commits" over the
        # one checkout that must survive.
        agent, push = self._runs_the_tick()

        agent.assert_not_called()
        push.assert_not_called()
        self.assertTrue(self.repo.path.exists())
        self.assertEqual(self.repo.head(), self.repo.base)
        self.assertEqual(len(self.repo.staged()), len(APPROVED_COMMITS))

    def test_the_claim_and_the_park_both_stand(self) -> None:
        # And the tick answers the only way it can: the record is left for
        # whichever tick finds the checkout reconciled, and the human is told
        # where the branch is -- not on the commits the reviewer approved.
        self._runs_the_tick()

        pinned = self.github.pinned_data(ISSUE_NUMBER)
        self.assertIn(_collapses.LATE_COLLAPSE_HEAD, pinned)
        self.assertTrue(pinned[AWAITING_HUMAN])
        self.assertEqual(pinned[PARK_REASON], PARK_SQUASH_FAILED)
        self.assertNotIn(
            (ISSUE_NUMBER, LABEL_DOCUMENTING), self.github.label_history,
        )
        self.assertTrue(any(
            LEFT_COLLAPSED in body
            for _, body in self.github.posted_comments
        ))



class ParkCommitRealGitTest(HalfMadeCollapseWorld, unittest.TestCase):
    """The park that recovery takes, landed as a guarded commit over the comment read afresh."""

    def test_a_write_ahead_of_the_park_is_kept(self) -> None:
        # Another road leaves a note of its own after the park's last reading
        # and before its commit: the park lands beside it and is reported.
        ahead = _roads.AnotherRoadAhead(self, _THE_PARK, _roads.Writes({THEIR_NOTE: "kept"}))

        with ahead.patched():
            self._runs_the_tick()

        pinned = self.github.pinned_data(ISSUE_NUMBER)
        self.assertEqual(
            (pinned[PARK_REASON], pinned[THEIR_NOTE], self._parks_reported()),
            (PARK_SQUASH_FAILED, "kept", 1),
        )

    def test_a_lost_park_write_mentions_nobody_again(self) -> None:
        # The park's commit lands and its response is lost: the park and the
        # record are on the comment, and no human wait is reported behind a
        # write nobody confirmed. The next tick retries the recovery over the
        # same checkout, finds its own park standing, and posts nothing: one
        # notice in all, no agent, no push, and the staged collapse intact.
        with _one.LosesOneResponse(self, _THE_PARK).patched():
            self._runs_the_tick()
        noticed = len(self.github.posted_comments)
        agent, push = self._runs_the_tick()

        pinned = self.github.pinned_data(ISSUE_NUMBER)
        mentioned = len(self.github.posted_comments)
        self.assertEqual(
            (
                (pinned[PARK_REASON], _collapses.LATE_COLLAPSE_HEAD in pinned),
                (noticed, mentioned, self._parks_reported()),
                (agent.call_count, push.call_count),
                self._staged_over_the_base(),
            ),
            (
                (PARK_SQUASH_FAILED, True),
                (1, 1, 0),
                (0, 0),
                (True, len(APPROVED_COMMITS)),
            ),
        )


def _standing(repo) -> tuple:
    """The checkout's head and staged paths, and the tip of the issue's own branch."""
    tip = run_git("rev-parse", repo.branch, cwd=repo.path)
    return repo.head(), repo.staged(), tip.strip()


class ForeignCheckoutCollapseTest(HalfMadeCollapseWorld, unittest.TestCase):
    """The same interrupted collapse, with the tree at the issue's path switched onto the flat branch since."""

    def test_a_flat_checkout_is_not_rewritten(self) -> None:
        # The recovery resets and recommits what it finds, so the tree is held
        # to the issue's own branch first: one on the flat branch refuses the
        # tick with its head, its staged changes, and the issue's branch as
        # they were, and nothing launched or pushed.
        run_git("checkout", "-q", "-b", f"orchestrator/issue-{ISSUE_NUMBER}", cwd=self.repo.path)
        before = _standing(self.repo)

        with self.assertRaises(_naming.BranchRefused):
            self._runs_the_tick()

        self.assertEqual(_standing(self.repo), before)


if __name__ == "__main__":
    unittest.main()
