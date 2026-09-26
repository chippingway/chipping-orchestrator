# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    poll_models as _poll_models,
    run_ledger_values as _run_ledger_values,
)
from tests.support.fakes import (
    DEFAULT_PR_HEAD_SHA,
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakePRRef,
    FakeUser,
    make_issue,
)
from tests.workflow import published_reports as _published_reports
from tests.workflow.fixtures import (
    _TEST_SPEC,
    MEASURED_CANDIDATE_SHA,
    REVIEW_APPROVED_MESSAGE,
    _agent,
    _PatchedWorkflowMixin,
)

HUMAN_FEEDBACK_ISSUE = 15
HUMAN_FEEDBACK_PR = 22
HUMAN_FEEDBACK_BRANCH = "orchestrator/chippingway__orchestrator/issue-15"
PRE_PICKUP_ISSUE = 20
PRE_PICKUP_PR = 25
PRE_PICKUP_BRANCH = "orchestrator/chippingway__orchestrator/issue-20"
PICKUP_COMMENT_ID = 900
PR_OPEN_COMMENT_ID = 901
HUMAN_FEEDBACK_ID = 950
PRE_PICKUP_COMMENT_ID = 850
# A comment on the pull request itself, numbered below the pickup: a PR a plan
# handoff reused or a human opened carries conversation the spawn never quoted.
PRE_PICKUP_PR_COMMENT_ID = 860
PRE_PICKUP_PR_BODY = "this reuses the schema we rejected last quarter"
REVIEW_DEBOUNCE_SECONDS = 600
LABEL_VALIDATING = "workflow:validating"
LABEL_IN_REVIEW = "in_review"
LABEL_FIXING = "workflow:fixing"
PICKUP_MESSAGE = ":robot: orchestrator picking this up."
BOT_LOGIN = "orchestrator"
HUMAN_LOGIN = "alice"
BACKEND_CLAUDE = "claude"
DEV_SESSION = "dev-sess"
REVIEWED_SHA = "cafe1234" * 5
CHECKS_SUCCESS = "success"
PR_LAST_COMMENT_ID = "pr_last_comment_id"
DEBOUNCE_SETTING = "IN_REVIEW_DEBOUNCE_SECONDS"
RUN_AGENT = "run_agent"

# An issue that spent its lifetime ledger on a validating park, and the grant
# that bought it more. The grant cannot consume its own command without the
# reply its park interrupted, so the command outlives the grant.
GRANTED_ISSUE = 30
GRANTED_PR = 35
GRANTED_BRANCH = "orchestrator/chippingway__orchestrator/issue-30"
PARK_COMMENT_ID = 910
PARKED_QUESTION = "@hitl agent needs your input to proceed"
HUMAN_REPLY = "answer: use sqlite"
STILL_ASKING = "which of the two did you mean?"
FIXED = "fixed it"
ADD_RUNS = "/orchestrator add-agent-runs 3"
SPENT_RUNS = 3
READY_PING = "ready for review/merge"
PENDING_FIX_ISSUE_IDS = "pending_fix_issue_ids"
EVENT_NAME = "event"
EVENT_AGENT_SPAWN = "agent_spawn"
AGENT_ROLE = "agent_role"


class _HumanFeedbackHandoffFixtureMixin(_PatchedWorkflowMixin):
    def _setup(self):
        gh = FakeGitHubClient()
        issue = make_issue(
            HUMAN_FEEDBACK_ISSUE,
            label=LABEL_VALIDATING,
            comments=[
                FakeComment(
                    id=PICKUP_COMMENT_ID,
                    body=PICKUP_MESSAGE,
                    user=FakeUser(BOT_LOGIN),
                ),
                FakeComment(
                    id=PR_OPEN_COMMENT_ID,
                    body=":sparkles: PR opened: #22",
                    user=FakeUser(BOT_LOGIN),
                ),
            ],
        )
        gh.add_issue(issue)
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        pr = FakePR(
            number=HUMAN_FEEDBACK_PR,
            head_branch=HUMAN_FEEDBACK_BRANCH,
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state=CHECKS_SUCCESS,
            # Human posted a review comment during validating, BEFORE the
            # orchestrator's approval comment lands. Without the watermark
            # fix, the validating handler would seed pr_last_comment_id past
            # this comment and the next in_review tick would never see it.
            issue_comments=[
                FakeComment(
                    id=HUMAN_FEEDBACK_ID,
                    body="please add a docstring",
                    user=FakeUser(HUMAN_LOGIN),
                    created_at=long_ago,
                ),
            ],
        )
        gh.add_pr(pr)
        gh.seed_state(
            HUMAN_FEEDBACK_ISSUE,
            pr_number=HUMAN_FEEDBACK_PR,
            branch=HUMAN_FEEDBACK_BRANCH,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
            orchestrator_comment_ids=[PICKUP_COMMENT_ID, PR_OPEN_COMMENT_ID],
            pickup_comment_id=PICKUP_COMMENT_ID,
        )
        return gh, issue, pr


class ValidatingHandoffPreservesHumanFeedbackTest(
    unittest.TestCase,
    _HumanFeedbackHandoffFixtureMixin,
):
    """Keep concurrent human PR feedback visible after handoff."""

    def test_human_pr_comment_survives_handoff(self) -> None:
        gh, issue, _pr = self._setup()

        # Step 1: validating approves. The orchestrator's approval comment
        # lands AFTER the human's. With the fix, the watermark stops at
        # the first human comment instead of swallowing it.
        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
        )
        # Validating's approval flips through `documenting` first (the
        # final-docs hop); the watermark must already be seeded past the
        # human's pre-handoff PR comment by the time the docs pass runs.
        self.assertIn((HUMAN_FEEDBACK_ISSUE, "workflow:documenting"), gh.label_history)
        watermark = gh.pinned_data(HUMAN_FEEDBACK_ISSUE).get(PR_LAST_COMMENT_ID)
        self.assertIsNotNone(watermark)
        self.assertLess(
            watermark,
            HUMAN_FEEDBACK_ID,
            f"watermark must stop before human comment id=950 (got {watermark})",
        )

        # Step 2: in_review tick. The human comment is visible past the
        # watermark and the handler routes the issue to `fixing` (no dev
        # spawn here; the fixing handler drives the resume). Without the
        # surfacing, the handler would ping HITL for the manual merge
        # over the human's unaddressed feedback.
        from tests.support.fakes import FakeLabel

        if not any(label.name == LABEL_IN_REVIEW for label in issue.labels):
            issue.labels = [FakeLabel(LABEL_IN_REVIEW)]

        with patch.object(
            config,
            DEBOUNCE_SETTING,
            REVIEW_DEBOUNCE_SECONDS,
        ):
            mocks = self._run_in_review(
                gh,
                issue,
                run_agent=_agent(),
            )

        mocks[RUN_AGENT].assert_not_called()
        # No merge happened; issue routed to `fixing` so the human's
        # feedback is owned by the fix loop.
        self.assertEqual(gh.merge_calls, [])
        self.assertIn((HUMAN_FEEDBACK_ISSUE, LABEL_FIXING), gh.label_history)
        self.assertEqual(
            gh.pinned_data(HUMAN_FEEDBACK_ISSUE).get("pending_fix_issue_max_id"),
            HUMAN_FEEDBACK_ID,
        )


class _PrePickupHandoffFixtureMixin(_PatchedWorkflowMixin):
    def _setup(self, *, pr_conversation=()):
        gh = FakeGitHubClient()
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        issue = make_issue(
            PRE_PICKUP_ISSUE,
            label=LABEL_VALIDATING,
            comments=[
                FakeComment(
                    id=PRE_PICKUP_COMMENT_ID,
                    body="original issue clarification posted before pickup",
                    user=FakeUser(HUMAN_LOGIN),
                    created_at=long_ago,
                ),
                FakeComment(
                    id=PICKUP_COMMENT_ID,
                    body=PICKUP_MESSAGE,
                    user=FakeUser(BOT_LOGIN),
                    created_at=long_ago,
                ),
                FakeComment(
                    id=PR_OPEN_COMMENT_ID,
                    body=":sparkles: PR opened: #25",
                    user=FakeUser(BOT_LOGIN),
                    created_at=long_ago,
                ),
            ],
        )
        gh.add_issue(issue)
        pr = FakePR(
            number=PRE_PICKUP_PR,
            head_branch=PRE_PICKUP_BRANCH,
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state=CHECKS_SUCCESS,
            issue_comments=list(pr_conversation),
        )
        gh.add_pr(pr)
        gh.seed_state(
            PRE_PICKUP_ISSUE,
            pr_number=PRE_PICKUP_PR,
            branch=PRE_PICKUP_BRANCH,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
            orchestrator_comment_ids=[PICKUP_COMMENT_ID, PR_OPEN_COMMENT_ID],
            pickup_comment_id=PICKUP_COMMENT_ID,
        )
        return gh, issue, pr

    def _run_after_handoff(self, github, issue, pr):
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        for comment in list(pr.issue_comments):
            if comment.created_at is None:
                comment.created_at = long_ago
        pr.approved = True
        if not any(label.name == LABEL_IN_REVIEW for label in issue.labels):
            issue.labels = [FakeLabel(LABEL_IN_REVIEW)]
        with patch.object(
            config,
            DEBOUNCE_SETTING,
            REVIEW_DEBOUNCE_SECONDS,
        ):
            return self._run_in_review(
                github,
                issue,
                run_agent=_agent(),
            )

    def _assert_ready_path(self, github, mocks) -> None:
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(github.merge_calls, [])
        self.assertNotIn(
            (PRE_PICKUP_ISSUE, "done"),
            github.label_history,
        )
        self.assertNotIn(
            (PRE_PICKUP_ISSUE, LABEL_FIXING),
            github.label_history,
        )
        ping_comments = [
            body
            for _, body in github.posted_comments
            if "ready for review/merge" in body
        ]
        self.assertEqual(len(ping_comments), 1)


class PrePickupChatterHandoffTest(
    unittest.TestCase,
    _PrePickupHandoffFixtureMixin,
):
    """Advance the handoff watermark past pre-pickup discussion."""

    def test_pre_pickup_chatter_not_replayed(self) -> None:
        gh, issue, pr = self._setup()

        # Step 1: validating approves. Watermark must include id 850 so the
        # pre-pickup human comment is treated as consumed.
        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
            head_shas=(REVIEWED_SHA,),
        )
        watermark = gh.pinned_data(PRE_PICKUP_ISSUE).get(PR_LAST_COMMENT_ID)
        self.assertIsNotNone(watermark, "watermark must be seeded past pre-pickup")
        self.assertGreaterEqual(
            watermark,
            PR_OPEN_COMMENT_ID,
            f"watermark must advance past pre-pickup chatter and self-run; got {watermark}",
        )

        # Step 2: in_review tick. With the fix, no comment is past the
        # watermark, so the handler reaches the mergeable / HITL-ping
        # path. Without the fix, the human comment id=850 surfaces as
        # "new" and the issue routes to `fixing`.
        mocks = self._run_after_handoff(gh, issue, pr)

        # Manual-merge-only: no orchestrator merge, but the HITL ping
        # fires because the watermark fix kept the pre-pickup chatter
        # out of `new_comments`.
        self._assert_ready_path(gh, mocks)


class PrePickupPrCommentHandoffTest(
    unittest.TestCase,
    _PrePickupHandoffFixtureMixin,
):
    """Being older than the pickup is no evidence on the pull request.

    The spawn quotes the issue thread, so pre-pickup chatter THERE is chatter
    the developer read. The pull request may be one a plan handoff reused or a
    human opened, and a comment on it numbered below the pickup was in no
    prompt at all -- so the approval handoff's seed has to stop before it
    rather than walk past it as old.
    """

    def test_seed_stops_under_a_pre_pickup_pr_comment(self) -> None:
        gh, issue, pr = self._setup(pr_conversation=[
            FakeComment(
                id=PRE_PICKUP_PR_COMMENT_ID,
                body=PRE_PICKUP_PR_BODY,
                user=FakeUser(HUMAN_LOGIN),
                created_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        ])

        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=REVIEW_APPROVED_MESSAGE),
            head_shas=(REVIEWED_SHA,),
        )

        self.assertLess(
            gh.pinned_data(PRE_PICKUP_ISSUE).get(PR_LAST_COMMENT_ID),
            PRE_PICKUP_PR_COMMENT_ID,
        )

        # And the next stage therefore still finds it: the PR is not pinged
        # as ready for merge over a comment nobody answered.
        mocks = self._run_after_handoff(gh, issue, pr)

        mocks[RUN_AGENT].assert_not_called()
        self.assertIn((PRE_PICKUP_ISSUE, LABEL_FIXING), gh.label_history)
        self.assertEqual(
            gh.pinned_data(PRE_PICKUP_ISSUE).get("pending_fix_issue_max_id"),
            PRE_PICKUP_PR_COMMENT_ID,
        )


class RunLimitToInReviewTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A run-grant command the grant left unread, carried to in_review.

    The developer the grant pays for fixes the branch over the reply the run
    limit interrupted, and the reviewer approves it -- with the command still
    past the issue's mark. The approval seeds in_review's watermark by walking
    the thread, and a walk that stops on the command, or an in_review scan
    that reads it, routes the issue to `fixing` over a control already
    handled.
    """

    def setUp(self) -> None:
        self.github = FakeGitHubClient()
        self.issue = make_issue(
            GRANTED_ISSUE,
            label=LABEL_VALIDATING,
            comments=[
                FakeComment(
                    id=PICKUP_COMMENT_ID, body=PICKUP_MESSAGE, user=FakeUser(BOT_LOGIN),
                ),
                FakeComment(
                    id=PARK_COMMENT_ID, body=PARKED_QUESTION, user=FakeUser(BOT_LOGIN),
                ),
            ],
        )
        self.github.add_issue(self.issue)
        self.pr = FakePR(
            number=GRANTED_PR,
            head_branch=GRANTED_BRANCH,
            head=FakePRRef(sha=DEFAULT_PR_HEAD_SHA),
            mergeable=True,
            check_state=CHECKS_SUCCESS,
        )
        self.github.add_pr(self.pr)
        self.github.seed_state(
            GRANTED_ISSUE,
            pr_number=GRANTED_PR,
            branch=GRANTED_BRANCH,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
            orchestrator_comment_ids=[PICKUP_COMMENT_ID, PARK_COMMENT_ID],
            pickup_comment_id=PICKUP_COMMENT_ID,
            awaiting_human=True,
            park_reason=None,
            last_action_comment_id=PARK_COMMENT_ID,
            **{
                _run_ledger_values.AGENT_RUN_ALLOWANCE: SPENT_RUNS,
                _run_ledger_values.AGENT_RUNS_USED: SPENT_RUNS,
            },
        )

    def test_the_grant_command_is_no_review(self) -> None:
        commanded = self._approved_over_a_grant()
        seeded = self.github.pinned_data(GRANTED_ISSUE)[PR_LAST_COMMENT_ID]

        reviewed = self._reviews()

        self.assertEqual(
            [
                recorded[AGENT_ROLE] for recorded in self.github.recorded_events
                if recorded[EVENT_NAME] == EVENT_AGENT_SPAWN
            ],
            ["developer", "reviewer"],
        )
        self.assertGreater(seeded, commanded)
        reviewed[RUN_AGENT].assert_not_called()
        self.assertNotIn((GRANTED_ISSUE, LABEL_FIXING), self.github.label_history)
        self.assertNotIn(PENDING_FIX_ISSUE_IDS, self.github.pinned_data(GRANTED_ISSUE))
        self.assertEqual(
            sum(READY_PING in body for _, body in self.github.posted_comments), 1,
        )

    def _approved_over_a_grant(self) -> int:
        """The whole validating arc, from the refused resume to the approval.

        The reply a spent ledger refuses the developer on, the command that
        buys more runs and the poll repairing the park's notice, the grant's
        own poll -- the developer resumed on the reply, committing the fix
        the size gate measures -- and the reviewer approving it. Answers the
        command's id, which is still past the issue's mark at the end.
        """
        self._they_say(HUMAN_REPLY)
        self._polls()
        commanded = self._they_say(ADD_RUNS)
        self._polls()
        self._polls(
            _agent(session_id=DEV_SESSION, last_message=FIXED),
            (DEFAULT_PR_HEAD_SHA, MEASURED_CANDIDATE_SHA),
            has_new_commits=True,
        )
        self.pr.head = FakePRRef(sha=MEASURED_CANDIDATE_SHA)
        _published_reports.publishes_the_report(self.github, self.issue)
        self._polls(
            _agent(last_message=REVIEW_APPROVED_MESSAGE), (MEASURED_CANDIDATE_SHA,),
        )
        return commanded

    def _reviews(self):
        """One in_review tick over the approved pull request.

        The final-docs hop between the approval and in_review seeds through
        the same walk, so the issue is carried straight to in_review here.
        """
        self.pr.approved = True
        self.issue.labels = [FakeLabel(LABEL_IN_REVIEW)]
        with patch.object(config, DEBOUNCE_SETTING, REVIEW_DEBOUNCE_SECONDS):
            return self._run_in_review(self.github, self.issue, run_agent=_agent())

    def _they_say(self, body: str) -> int:
        identified = self.github.next_reply_id(self.issue)
        self.issue.comments.append(
            FakeComment(identified, body, user=FakeUser(HUMAN_LOGIN)),
        )
        return identified

    def _polls(self, answers=None, heads=(DEFAULT_PR_HEAD_SHA,), **run_options):
        """One whole validating poll, through the dispatcher's run-limit hold."""
        return self._run(
            lambda: _issue_processing._route_issue_to_handler(
                self.github, _TEST_SPEC, self.issue, LABEL_VALIDATING,
                reading=_poll_models._POLLED_OPEN,
            ),
            run_agent=MagicMock(
                return_value=answers or _agent(session_id=DEV_SESSION, last_message=STILL_ASKING),
            ),
            head_shas=heads,
            **run_options,
        )
