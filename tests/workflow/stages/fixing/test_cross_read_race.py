# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A fix round's settlement steps over no issue reply landing between its two reads."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.fixing import feedback as _feedback
from tests.support.fakes import FakeComment, FakeGitHubClient, FakePR, FakeUser, make_issue

PR_LAST = "pr_last_comment_id"
SETTLED_ID = 100
# The issue reply landing after the thread's read and before the pull request's.
RACED_REPLY_ID = 110
PR_COMMENT_ID = 120


def _comment(comment_id: int, body: str) -> FakeComment:
    return FakeComment(id=comment_id, body=body, user=FakeUser("alice"))


class CrossReadRaceTest(unittest.TestCase):
    """The thread is read first, the pull request second, and `pr_last_comment_id` spans both.

    A reply that lands on the thread between the two reads is in neither, while
    a PR comment numbered above it is in the batch. Settled to that PR comment,
    the shared cursor would carry the reply for good; held below the reply, it
    leaves it to the next scan, which delivers both and lifts the cursor.
    """

    def setUp(self) -> None:
        self.issue = make_issue(1, label="workflow:fixing")
        self.pr = FakePR(number=2)
        self.github = FakeGitHubClient([self.issue])
        self.github.add_pr(self.pr)
        self.read_pull_request = self.github.pr_conversation_comments_after
        self.state = PinnedState(state_data={
            PR_LAST: SETTLED_ID, "pr_last_review_comment_id": 0, "pr_last_review_summary_id": 0,
            "last_action_comment_id": SETTLED_ID,
            "delivered_after_comment_id": 0, "delivered_through_comment_id": SETTLED_ID,
        })

    def test_settling_leaves_the_reply_unread(self) -> None:
        batch = self._raced_scan()
        _feedback._settle_consumed_feedback(self.state, batch)

        self.assertEqual([seen.id for seen in batch.all_items], [PR_COMMENT_ID])
        self.assertLess(self.state.get(PR_LAST), RACED_REPLY_ID)
        following = _feedback._rescan_fixing_feedback(self.github, self.issue, self.pr, self.state)
        self.assertEqual([seen.id for seen in following.all_items], [RACED_REPLY_ID, PR_COMMENT_ID])
        _feedback._settle_consumed_feedback(self.state, following)
        self.assertEqual(self.state.get(PR_LAST), PR_COMMENT_ID)

    def test_a_report_freezes_no_pair_over_the_reply(self) -> None:
        # A round finishing on a report freezes its pairs for the write that
        # settles it, and those carry the same bound as the direct settlement.
        frozen = _feedback._consumed_delivery(self.state, self._raced_scan()).consumed_pairs(self.state)

        self.assertLess(dict(frozen).get(PR_LAST, SETTLED_ID), RACED_REPLY_ID)

    def _raced_scan(self):
        """The fixing scan, its pull-request read run after a reply lands on the thread and a PR comment above it."""
        with patch.object(self.github, "pr_conversation_comments_after", side_effect=self._race):
            return _feedback._rescan_fixing_feedback(self.github, self.issue, self.pr, self.state)

    def _race(self, asked_pr, after_id):
        self.issue.comments.append(_comment(RACED_REPLY_ID, "Do not drop the audit rows"))
        self.pr.issue_comments.append(_comment(PR_COMMENT_ID, "Also fix the typo"))
        return self.read_pull_request(asked_pr, after_id)


if __name__ == "__main__":
    unittest.main()
