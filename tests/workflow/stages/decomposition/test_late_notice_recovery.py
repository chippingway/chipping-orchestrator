# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A park notice whose recording write was lost is recovered as said, and as nothing delivered."""

from __future__ import annotations

import unittest

from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.late_park_delivery import _reconcile_notice_delivery
from orchestrator.workflow.stages.in_review.surfaces import _unread_issue_thread
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import _TEST_SPEC

BOT_LOGIN = "orchestrator"
MESSAGE = "Candidate needs your guidance."
REASON = "late_owner_unreadable"
# How far the thread had been delivered, and where the reply boundary stood, before the park.
DELIVERED_ID = 100
HUMAN_REPLY_ID = 110
NOTICE_ID = 120
DELIVERED_THROUGH = "delivered_through_comment_id"
LAST_ACTION = "last_action_comment_id"


class LostNoticeWriteTest(unittest.TestCase):
    """The notice's own comment is the receipt its lost write leaves.

    Recovering it moves the reply boundary to that comment, the mark a park's
    own mention is supposed to leave. It hands nobody anything, so the
    delivered stretch follows only where nothing but our own posts stands
    between it and the notice: a human comment written ahead of the notice
    stays unread feedback.
    """

    def test_the_boundary_moves_and_delivery_stays(self) -> None:
        for case, thread, delivered in (
            ("a human comment below the notice", (HUMAN_REPLY_ID,), DELIVERED_ID),
            ("the notice alone", (), NOTICE_ID),
        ):
            with self.subTest(case=case):
                recovered, unread = self._recovered_over(thread)
                self.assertEqual(recovered.get(LAST_ACTION), NOTICE_ID)
                self.assertEqual(recovered.get(DELIVERED_THROUGH), delivered)
                self.assertEqual([found for found in unread if found != NOTICE_ID], list(thread))

    def _recovered_over(self, thread: tuple) -> tuple:
        """The record the recovery leaves over `thread`, human comments below the notice, and the unread ids."""
        issue = make_issue(1, label="workflow:decomposing", comments=[
            *(FakeComment(id=found, body="Preserve the audit rows", user=FakeUser("alice")) for found in thread),
            # Posted carrying our hidden marker, as every notice is; the ledger
            # entry recording its id went down with the lost write.
            FakeComment(id=NOTICE_ID, body=_comments._with_orch_marker(MESSAGE), user=FakeUser(BOT_LOGIN)),
        ])
        github = FakeGitHubClient([issue], bot_login=BOT_LOGIN)
        github.seed_state(
            1, awaiting_human=True, park_reason=REASON, pr_last_comment_id=DELIVERED_ID,
            late_park_notice={"message": MESSAGE, "reason": REASON}, **{
                LAST_ACTION: DELIVERED_ID, "delivered_after_comment_id": 0, DELIVERED_THROUGH: DELIVERED_ID,
            },
        )
        generation = LateGeneration(cycle_id=1, generation=1, root_issue=1, current_issue=1)
        _reconcile_notice_delivery(_LateContext(github, _TEST_SPEC, issue, github.read_pinned_state(issue), generation))
        recovered = github.read_pinned_state(issue)
        return recovered, [seen.id for seen in _unread_issue_thread(github, issue, recovered)]


if __name__ == "__main__":
    unittest.main()
