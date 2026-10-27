# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for the approval's seed walk over what no record names: a thread no
delivered stretch covers, and posts of ours the id ledger no longer holds."""
from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import comments as _comments
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakePRRef,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    _agent,
    _PatchedWorkflowMixin,
    approved_on,
)

WATERMARK_ISSUE = 300
WATERMARK_BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-300"
UNDELIVERED_ISSUE = 500
UNDELIVERED_PR = 1000
UNDELIVERED_BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-500"
MARKER_WALK_PR = 700
PICKUP_COMMENT_ID = 900
PR_OPEN_COMMENT_ID = 901
HUMAN_FEEDBACK_ID = 950
PRE_PICKUP_COMMENT_ID = 800
LATER_PR_OPEN_COMMENT_ID = 960
MARKER_ONLY_COMMENT_ID = 902
APPROVAL_COMMENT_ID = 903
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
LONG_AGO = datetime.now(UTC) - timedelta(hours=1)
ORCHESTRATOR_MARKER = _comments._ORCH_COMMENT_MARKER


class HandoffWithoutDeliveryRecordTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A record carrying a pickup anchor and no delivered stretch.

    The delivered stretch is the only record that a developer was handed the
    issue thread, and a prompt that quoted the thread writes it -- never the
    pickup, whatever reply boundary it stood; a record missing it says nobody
    was handed anything. So the approval's seed walk
    crosses no human comment for being older than the pickup: it stops at
    the first one, the human comments past it -- the pre-pickup clarification
    and the "do not merge yet" posted while the developer ran alike -- reach
    in_review as unread feedback, and the orchestrator's own posts are still
    dropped there by the marker and the id ledger.
    """

    def test_no_human_comment_is_crossed_for_its_age(self) -> None:
        gh = FakeGitHubClient()
        issue = make_issue(
            UNDELIVERED_ISSUE,
            label=LABEL_VALIDATING,
            comments=[
                FakeComment(
                    id=PRE_PICKUP_COMMENT_ID,
                    body="original issue clarification",
                    user=FakeUser(HUMAN_LOGIN),
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=PICKUP_COMMENT_ID,
                    body=f"{PICKUP_MESSAGE}\n\n{ORCHESTRATOR_MARKER}",
                    user=FakeUser(BOT_LOGIN),
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=HUMAN_FEEDBACK_ID,
                    body="please do not merge yet",
                    user=FakeUser(HUMAN_LOGIN),
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=LATER_PR_OPEN_COMMENT_ID,
                    body=":sparkles: PR opened: #1000",
                    user=FakeUser(BOT_LOGIN),
                    created_at=LONG_AGO,
                ),
            ],
        )
        gh.add_issue(issue)
        pr = FakePR(
            number=UNDELIVERED_PR,
            head_branch=UNDELIVERED_BRANCH,
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state=CHECKS_SUCCESS,
        )
        gh.add_pr(pr)
        gh.seed_state(
            UNDELIVERED_ISSUE,
            pr_number=UNDELIVERED_PR,
            branch=UNDELIVERED_BRANCH,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
            orchestrator_comment_ids=[LATER_PR_OPEN_COMMENT_ID],
            pickup_comment_id=PICKUP_COMMENT_ID,
        )

        # Step 1: validating approves. The oldest comment on the thread is a
        # human's nothing records delivering, so the seed crosses nothing.
        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=approved_on(REVIEWED_SHA)),
            head_shas=(REVIEWED_SHA,),
        )
        self.assertEqual(gh.pinned_data(UNDELIVERED_ISSUE).get(PR_LAST_COMMENT_ID), 0)

        # Step 2: in_review tick. Every gate passes -- the only thing
        # standing between the PR and a ready-ping is the unread human
        # comments. The handler surfaces both as fresh feedback and routes
        # to `fixing`, dropping our own posts.
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

        self.assertEqual(gh.merge_calls, [])
        mocks[RUN_AGENT].assert_not_called()
        self.assertIn((UNDELIVERED_ISSUE, LABEL_FIXING), gh.label_history)
        self.assertEqual(
            gh.pinned_data(UNDELIVERED_ISSUE).get("pending_fix_issue_ids"),
            [PRE_PICKUP_COMMENT_ID, HUMAN_FEEDBACK_ID],
        )


class HandoffWalkerHonorsOrchestratorMarkerTest(unittest.TestCase, _PatchedWorkflowMixin):
    """`_seed_watermark_past_self` must recognise orchestrator-authored
    content by hidden body marker AS WELL AS by recorded id. Without the
    marker check, a bot comment whose id was evicted from the bounded
    `orchestrator_comment_ids` cap (or never persisted due to a state-write
    race) stops the walker early and leaves the in_review watermark
    stranded at the previous orchestrator id. The in_review filter still
    drops the marker-bearing bot content at scan time, so no human comment
    is mis-routed, but the validating->documenting->in_review->fixing
    cycle described in #437 made the cost of that stranded watermark
    visible: every in_review tick re-scanned the same orchestrator backlog,
    and the fixing-bounce path silently relabelled to `validating`,
    looping the issue indefinitely.
    """

    def test_marker_only_comment_does_not_stop_walk(
        self,
    ) -> None:
        gh = FakeGitHubClient()
        # Lifecycle: pickup (900) -> PR-opened (901) -> orchestrator
        # reviewer-requested-changes comment whose id was never tracked
        # (902, marker present, MISSING from orchestrator_comment_ids) ->
        # orchestrator approval (903, tracked). The id=902 case models the
        # PR #433 incident where 3 review-request comments were posted
        # but their ids never made it into `orchestrator_comment_ids` -- a
        # state-write race window.
        issue = make_issue(
            WATERMARK_ISSUE,
            label=LABEL_VALIDATING,
            comments=[
                FakeComment(
                    id=PICKUP_COMMENT_ID,
                    body=PICKUP_MESSAGE,
                    user=FakeUser(BOT_LOGIN),
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=PR_OPEN_COMMENT_ID,
                    body=(
                        ":sparkles: PR opened: #700\n\n"
                        f"{ORCHESTRATOR_MARKER}"
                    ),
                    user=FakeUser(BOT_LOGIN),
                    created_at=LONG_AGO,
                ),
            ],
        )
        gh.add_issue(issue)
        pr = FakePR(
            number=MARKER_WALK_PR,
            head_branch=WATERMARK_BRANCH,
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state=CHECKS_SUCCESS,
            issue_comments=[
                FakeComment(
                    id=MARKER_ONLY_COMMENT_ID,
                    body=(
                        ":eyes: codex review requested changes\n\n"
                        f"{ORCHESTRATOR_MARKER}"
                    ),
                    user=FakeUser(BOT_LOGIN),
                    created_at=LONG_AGO,
                ),
                FakeComment(
                    id=APPROVAL_COMMENT_ID,
                    body=(
                        ":white_check_mark: codex review approved.\n\n"
                        f"{ORCHESTRATOR_MARKER}"
                    ),
                    user=FakeUser(BOT_LOGIN),
                    created_at=LONG_AGO,
                ),
            ],
        )
        gh.add_pr(pr)
        # Crucially: id 902 is NOT in orchestrator_comment_ids. Without
        # the marker check the walker would stop at 902 and leave the
        # watermark at 901.
        gh.seed_state(
            WATERMARK_ISSUE,
            pr_number=MARKER_WALK_PR,
            branch=WATERMARK_BRANCH,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            review_round=0,
            orchestrator_comment_ids=[
                PICKUP_COMMENT_ID,
                PR_OPEN_COMMENT_ID,
                APPROVAL_COMMENT_ID,
            ],
            pickup_comment_id=PICKUP_COMMENT_ID,
        )

        self._run_validating(
            gh,
            issue,
            run_agent=_agent(last_message=approved_on(REVIEWED_SHA)),
            head_shas=(REVIEWED_SHA,),
        )

        # Watermark must advance past the marker-only id 902 -- ideally
        # to id 903 (the latest tracked orchestrator comment on either
        # surface). The exact value is not part of the contract, but it
        # must NOT be stuck at <=901.
        watermark = gh.pinned_data(WATERMARK_ISSUE).get(PR_LAST_COMMENT_ID)
        self.assertIsNotNone(watermark)
        self.assertGreaterEqual(
            watermark,
            MARKER_ONLY_COMMENT_ID,
            f"walker must advance past marker-only bot comment id=902; got {watermark}",
        )
