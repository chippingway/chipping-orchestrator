# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The replies a parked rebase's resolution road quotes are delivered once a launched run is back."""

from __future__ import annotations

import unittest

from orchestrator.agents.models import AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.conflicts import models as _models
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue

DELIVERED_ID = 100
STAMPED_OVER_ID = 110
NOTICE_ID = 120
REPLY_ID = 130
DELIVERED_THROUGH = "delivered_through_comment_id"


def _comment(comment_id: int, body: str) -> FakeComment:
    return FakeComment(id=comment_id, body=body, user=FakeUser("alice"))


class ResolutionReplyDeliveryTest(unittest.TestCase):
    """The reply boundary goes over the batch before the run; delivery waits for one that was launched.

    The stretch then moves over the quoted reply only where the thread
    between it and that reply holds nothing anybody is owed: a reply the
    park's notice was stamped over keeps it below.
    """

    def test_a_launched_run_delivers_the_quoted_reply(self) -> None:
        for case, invoked, below, through in (
            ("a launched run", True, (), REPLY_ID),
            ("a refused launch", False, (), DELIVERED_ID),
            ("a reply the notice was stamped over", True, (STAMPED_OVER_ID,), DELIVERED_ID),
        ):
            with self.subTest(case=case):
                self.assertEqual(self._delivered(invoked, below).get(DELIVERED_THROUGH), through)

    def _delivered(self, invoked: bool, below: tuple) -> PinnedState:
        """The record a resolution run leaves, launched where `invoked`, `below` written ahead of the notice."""
        issue = make_issue(1, comments=[
            *(_comment(found, "keep the old column") for found in below),
            _comment(NOTICE_ID, _comments._with_orch_marker("rebase conflicted")),
            _comment(REPLY_ID, "take theirs"),
        ])
        state = PinnedState(state_data={
            "last_action_comment_id": REPLY_ID, "delivered_after_comment_id": 0, DELIVERED_THROUGH: DELIVERED_ID,
        })
        reply = _models._ParkedReply("take theirs", REPLY_ID, quoted=frozenset((REPLY_ID,)))
        run_result = AgentResult(None, "", 0, False, "", "", invoked=invoked)
        reply.delivered_by(run_result, FakeGitHubClient([issue]), issue, state)
        return state


if __name__ == "__main__":
    unittest.main()
