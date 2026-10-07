# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real-git PR-route refresh: what the workflow's publication pushes and what it rolls back."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport
from tests.git.base_sync.real_git_test_support import (
    _LocalBranchPusher,
    _RefreshBaseRealGitFixture,
)
from tests.support.fakes import (
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.workflow.fixtures import (
    LABEL_IN_REVIEW,
    LABEL_RESOLVING_CONFLICT,
    LABEL_VALIDATING,
    STATE_OPEN,
)

PR_BRANCH = "orchestrator/acme__widget/issue-7"
KEY_CONFLICT_ROUND = "conflict_round"
KEY_REVIEW_ROUND = "review_round"
KEY_PARK_REASON = "park_reason"
PARK_PUSH_FAILED = "auto_base_rebase_push_failed"
PUSH_COMMAND = "push"
ORIGIN_REMOTE = "origin"
EXTRA_FILENAME = "extra.txt"
PR_NUMBER = 42


class _OpenPullRequestCase(_RefreshBaseRealGitFixture):
    """Issue #7 in review over an open PR #42 on the head its checkout stands on."""

    def _seed_open_pr(self, *, review_round: int | None = None) -> None:
        self._gh = FakeGitHubClient()
        self._gh.add_issue(make_issue(7, label=LABEL_IN_REVIEW))
        state = {
            "pr_number": PR_NUMBER,
            "branch": PR_BRANCH,
        }
        if review_round is not None:
            state["review_round"] = review_round
        self._gh.seed_state(7, **state)
        # Standing on the head this refresh reads out of the checkout and
        # leases its force-push against: the branch is in sync with its
        # remote here, so the two are one fact and the size gate refuses a
        # call whose readings of it disagree.
        self._gh.add_pr(
            FakePR(
                number=PR_NUMBER,
                head_branch=PR_BRANCH,
                merged=False,
                state=STATE_OPEN,
                head=FakePRRef(sha=self._wt_head()),
            )
        )

    def _refresh_with_push(self, push) -> None:
        with patch.object(branch_transport, "_push_branch", side_effect=push):
            self._refresh()

    def _remote_head(self) -> str:
        """Where the bare remote itself has the pull request branch."""
        return self._git("rev-parse", f"refs/heads/{PR_BRANCH}", cwd=self._remote).strip()


class RefreshPrRealGitTest(_OpenPullRequestCase, unittest.TestCase):
    def test_clean_base_advance_routes_to_validating(self) -> None:
        self._seed_open_pr(review_round=4)
        self._git(PUSH_COMMAND, ORIGIN_REMOTE, PR_BRANCH, cwd=self._wt)
        self._advance_base(conflicting=False)
        head_before = self._wt_head()
        pusher = _LocalBranchPusher()

        self._refresh_with_push(pusher)

        self._assert_clean_rebase(pusher, head_before)

    def test_push_failure_resets_local_head(self) -> None:
        self._seed_open_pr()
        self._git(PUSH_COMMAND, ORIGIN_REMOTE, PR_BRANCH, cwd=self._wt)
        self._advance_base(conflicting=False)
        head_before = self._wt_head()
        push = MagicMock(return_value=False)

        self._refresh_with_push(push)

        self._assert_push_failure(push, head_before)

    def test_conflicting_base_routes_to_conflict(self) -> None:
        self._seed_open_pr()
        self._advance_base(conflicting=True)
        head_before = self._wt_head()
        push = MagicMock()

        self._refresh_with_push(push)

        self.assertEqual(head_before, self._wt_head())
        self.assertTrue(self._is_clean())
        push.assert_not_called()
        self.assertIn(
            (7, LABEL_RESOLVING_CONFLICT),
            self._gh.label_history,
        )
        self.assertEqual(
            self._gh.pinned_data(7).get(KEY_CONFLICT_ROUND),
            0,
        )

    def _assert_clean_rebase(
        self,
        pusher: _LocalBranchPusher,
        head_before: str,
    ) -> None:
        self.assertNotEqual(head_before, self._wt_head())
        self.assertTrue((self._wt / EXTRA_FILENAME).exists())
        self.assertTrue(self._is_clean())
        self.assertEqual((pusher.branch, pusher.force_with_lease), (PR_BRANCH, head_before))
        self.assertEqual(self._remote_head(), self._wt_head())
        self.assertIn((7, LABEL_VALIDATING), self._gh.label_history)
        self.assertNotIn(
            (7, LABEL_RESOLVING_CONFLICT),
            self._gh.label_history,
        )
        state = self._gh.pinned_data(7)
        self.assertEqual(state.get(KEY_REVIEW_ROUND), 0)
        self.assertIsNone(state.get(KEY_CONFLICT_ROUND))

    def _assert_push_failure(self, push, head_before: str) -> None:
        push.assert_called_once()
        self.assertEqual(head_before, self._wt_head())
        self.assertFalse((self._wt / EXTRA_FILENAME).exists())
        self.assertTrue(self._is_clean())
        self.assertEqual(self._gh.label_history, [])
        self.assertEqual(self._gh.posted_pr_comments, [])
        self.assertIsNone(
            self._gh.pinned_data(7).get(KEY_REVIEW_ROUND),
        )


class ForeignPushRealGitTest(_OpenPullRequestCase, unittest.TestCase):
    """A push to the branch the remote has seen and GitHub's reading of the pull request has not."""

    def test_the_foreign_push_is_kept(self) -> None:
        # The candidate is read against the remote's own answer, so nothing is
        # pushed over their commit: the checkout goes back onto the anchor and
        # the issue parks for a human.
        self._seed_open_pr()
        self._git(PUSH_COMMAND, ORIGIN_REMOTE, PR_BRANCH, cwd=self._wt)
        self._advance_base(conflicting=False)
        head_before = self._wt_head()
        foreign = self._pushes_a_foreign_commit(head_before)
        push = MagicMock()

        self._refresh_with_push(push)

        push.assert_not_called()
        self.assertEqual((self._remote_head(), self._wt_head()), (foreign, head_before))
        self.assertEqual((self._gh.label_history, self._gh.posted_pr_comments), ([], []))
        self.assertEqual(self._gh.pinned_data(7).get(KEY_PARK_REASON), PARK_PUSH_FAILED)

    def _pushes_a_foreign_commit(self, anchor: str) -> str:
        """Move the remote pull request branch onto a commit no rebase here made."""
        foreign = self._git(
            "commit-tree", f"{anchor}^{{tree}}", "-p", anchor, "-m", "pushed from elsewhere",
            cwd=self._remote, env_extra=self._author_env,
        ).strip()
        self._git("update-ref", f"refs/heads/{PR_BRANCH}", foreign, cwd=self._remote)
        return foreign


if __name__ == "__main__":
    unittest.main()
