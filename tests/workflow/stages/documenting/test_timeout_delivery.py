# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A reply posted while a docs pass ran is not delivered by the park that ends it."""

from __future__ import annotations

import unittest
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.github.comments import ORCHESTRATOR_COMMENT_MARKER
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.documenting import models as _models, outcomes as _outcomes, run as _documenting_run
from orchestrator.workflow.stages.in_review.surfaces import _unread_issue_thread
from tests.support.fakes import FakeComment, FakeGitHubClient, FakeUser, make_issue
from tests.workflow.fixtures import _TEST_SPEC, _agent, _open_pr_for
from tests.workflow.stages.documenting.documenting_test_support import SHA_BEFORE, _branch, _DocumentingWorkflowMixin
from tests.workflow.verified_approvals import verifies_the_approval

DOCUMENTING = "workflow:documenting"
ISSUE_NUMBER = 411
PR_NUMBER = 48
# The thread the docs pass was handed ends here, and the boundary stands on it.
DELIVERED_ID = 100
# A human reply landing while the agent ran, never in its prompt.
DURING_RUN_ID = 110
NOTICE_ID = 1001
RESUME_REPLY_ID = 1100
AUDIT_REPLY = "Preserve the audit rows"
# A reply long enough to fill the documentation prompt's excerpt on its own.
LONG_REPLY_CHARS = 5000
LONG_REPLY = "x" * LONG_REPLY_CHARS
SHA_PR_HEAD = "pr-head-sha"
DEV_SESSION = "dev-sess"
DELIVERED_THROUGH = "delivered_through_comment_id"
LAST_ACTION = "last_action_comment_id"


def _comment(comment_id: int, body: str) -> FakeComment:
    return FakeComment(id=comment_id, body=body, user=FakeUser("alice"))


class TimeoutParkDeliveryTest(unittest.TestCase, _DocumentingWorkflowMixin):
    """A docs pass counts as delivered only what its prompt quoted.

    A timed-out pass parks over its own notice: the park stamps the reply
    boundary there, so its wait is for a reply above that, and nothing it does
    is delivery -- the human reply that landed while the agent ran is still
    owed to whoever reads feedback next. The resume a reply buys records what
    its bounded prompt quoted, and nothing the excerpt cut.
    """

    def test_a_reply_during_the_run_stays_unread(self) -> None:
        issue = make_issue(ISSUE_NUMBER, label=DOCUMENTING)
        github = FakeGitHubClient([issue])
        state = PinnedState(state_data={
            "pr_last_comment_id": DELIVERED_ID, LAST_ACTION: DELIVERED_ID,
            "delivered_after_comment_id": 0, DELIVERED_THROUGH: DELIVERED_ID,
        })
        issue.comments.append(_comment(DURING_RUN_ID, AUDIT_REPLY))

        _outcomes._dispose_documenting_outcome(
            _models._DocumentingContext(github, _TEST_SPEC, issue, state, "topic", 2),
            _models._DocumentingRun(
                worktree=Path("/tmp/timeout-delivery"), agent_result=AgentResult(None, "", -1, True, "", ""),
                before_sha=SHA_BEFORE, recovered=False, paused=False, ahead=0,
            ),
        )

        self.assertEqual(state.get("park_reason"), "agent_timeout")
        self.assertGreater(state.get(LAST_ACTION), DURING_RUN_ID)
        self.assertEqual(state.get(DELIVERED_THROUGH), DELIVERED_ID)
        self.assertIn(DURING_RUN_ID, [seen.id for seen in _unread_issue_thread(github, issue, state)])

    def test_the_resume_delivers_what_it_quoted(self) -> None:
        # The reply that resumes the pass moves the boundary over the thread
        # either way, and the pass that commits nothing parks again above it.
        # What counts as delivered is what the resume's bounded prompt quoted:
        # beside a short reply, the reply the timed-out run never saw is in
        # it and answered; behind a reply long enough to fill the excerpt, it
        # was cut, and stays unread feedback.
        for case, reply, quoted in (
            ("a short reply", "try again", True),
            ("a reply filling the excerpt", LONG_REPLY, False),
        ):
            with self.subTest(case=case):
                prompt, unread = self._resumed_with(reply)
                self.assertEqual(AUDIT_REPLY in prompt, quoted)
                self.assertEqual(DURING_RUN_ID in unread, not quoted)

    def test_a_reply_the_excerpt_cut_stays_unread(self) -> None:
        # Two replies answer the park, the second long enough to fill the
        # excerpt alone. The boundary goes over both; the first, which the
        # prompt never carried, is still unread feedback.
        issue = make_issue(ISSUE_NUMBER, label=DOCUMENTING, comments=[
            _comment(DURING_RUN_ID, AUDIT_REPLY), _comment(RESUME_REPLY_ID, LONG_REPLY),
        ])
        github = FakeGitHubClient([issue])
        state = PinnedState(state_data={
            "dev_agent": "codex", "dev_session_id": DEV_SESSION, LAST_ACTION: DELIVERED_ID,
            "delivered_after_comment_id": 0, DELIVERED_THROUGH: DELIVERED_ID,
        })
        context = _models._DocumentingContext(github, _TEST_SPEC, issue, state, "topic", PR_NUMBER)

        self._run(
            lambda: _documenting_run._resume_documenting_dev(context, Path("/tmp/timeout-delivery"), 0, SHA_PR_HEAD),
            run_agent=_agent(session_id=DEV_SESSION, last_message="noted"),
        )

        self.assertEqual(state.get(LAST_ACTION), RESUME_REPLY_ID)
        self.assertIn(DURING_RUN_ID, [seen.id for seen in _unread_issue_thread(github, issue, state)])

    def _resumed_with(self, reply: str) -> tuple:
        """The prompt a resume answering a timeout park with `reply` was given, and the unread ids it leaves."""
        github, issue = self._parked_with(reply)
        mocks = self._run_documenting(
            github, issue, run_agent=_agent(session_id=DEV_SESSION, last_message="noted"),
            push_branch=True, head_shas=[SHA_PR_HEAD, SHA_PR_HEAD], branch_ahead_behind=(0, 0),
        )
        state = github.read_pinned_state(issue)
        self.assertGreaterEqual(state.get(LAST_ACTION), RESUME_REPLY_ID)
        prompt = mocks["run_agent"].call_args.args[1]
        return prompt, [seen.id for seen in _unread_issue_thread(github, issue, state)]

    def _parked_with(self, reply: str) -> tuple:
        """An issue the timeout parked at `NOTICE_ID` over a reply the run never saw, answered by `reply`.

        Over the approval a docs pass is entered under, recorded as
        production leaves it (`verified_approvals.verifies_the_approval`).
        """
        issue = make_issue(ISSUE_NUMBER, label=DOCUMENTING, comments=[
            _comment(DURING_RUN_ID, AUDIT_REPLY),
            _comment(NOTICE_ID, f"agent timed out\n\n{ORCHESTRATOR_COMMENT_MARKER}"),
            _comment(RESUME_REPLY_ID, reply),
        ])
        github = FakeGitHubClient()
        github.add_issue(issue)
        _open_pr_for(github, issue_number=ISSUE_NUMBER, pr_number=PR_NUMBER)
        github.seed_state(
            ISSUE_NUMBER, pr_number=PR_NUMBER, branch=_branch(ISSUE_NUMBER), dev_agent="codex",
            dev_session_id=DEV_SESSION, awaiting_human=True, park_reason="agent_timeout",
            orchestrator_comment_ids=[NOTICE_ID], **{
                LAST_ACTION: NOTICE_ID, "delivered_after_comment_id": 0, DELIVERED_THROUGH: DELIVERED_ID,
            },
        )
        verifies_the_approval(github, issue)
        return github, issue


if __name__ == "__main__":
    unittest.main()
