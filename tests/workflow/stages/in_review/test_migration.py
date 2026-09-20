# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for the legacy in_review watermark migration: an issue that reached
the stage before the handoff seeded watermarks, and how far the first tick may
say it has read each of its surfaces."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from orchestrator import config
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    FakePRReview,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)

LEGACY_ISSUE = 150
LEGACY_PR = 300
EMPTY_WATERMARK_ISSUE = 400
EMPTY_WATERMARK_PR = 900
EARLIER_COMMENT_ID = 910
PR_OPEN_COMMENT_ID = 911
LATER_COMMENT_ID = 920
INLINE_REVIEW_ID = 30
REVIEW_SUMMARY_ID = 4000
FIRST_INLINE_REVIEW_ID = 42
FIRST_REVIEW_SUMMARY_ID = 5050
REVIEW_DEBOUNCE_SECONDS = 600
BOT_LOGIN = "orchestrator"
ORCH_MARKER = "<!--orchestrator-comment-->"
FIXING = "workflow:fixing"
# A comment on the pull request numbered BELOW the pickup: a PR a plan handoff
# reused or a human opened carries conversation the spawn never quoted, so
# being old is no evidence there that anybody read it.
PRE_PICKUP_PR_COMMENT_ID = 890
PRE_PICKUP_PR_BODY = "this reuses the schema we rejected last quarter"
REVIEWED_SHA = "cafe1234"
HUMAN_LOGIN = "alice"
BACKEND_CLAUDE = "claude"
DEV_SESSION = "dev-sess"
DEBOUNCE_SETTING = "IN_REVIEW_DEBOUNCE_SECONDS"
RUN_AGENT = "run_agent"


class _LegacyWatermarkFixtureMixin(_PatchedWorkflowMixin):
    def _legacy_setup(self, *, pr_conversation=()):
        gh = FakeGitHubClient()
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        # Two historical orchestrator comments on the issue thread plus one
        # on the PR conversation (the validating handoff approval), each
        # carrying the hidden marker that is the only thing proving a post is
        # ours once the id ledger is gone -- exactly the shape of an in-flight
        # in_review issue whose state was written before pr_last_comment_id
        # existed. The two review surfaces carry human feedback nothing here
        # records having delivered.
        issue = make_issue(
            LEGACY_ISSUE,
            label="in_review",
            comments=[
                FakeComment(
                    id=EARLIER_COMMENT_ID,
                    body=f":robot: orchestrator picking this up.\n\n{ORCH_MARKER}",
                    user=FakeUser(BOT_LOGIN),
                    created_at=long_ago,
                ),
                FakeComment(
                    id=PR_OPEN_COMMENT_ID,
                    body=f":sparkles: PR opened: #300\n\n{ORCH_MARKER}",
                    user=FakeUser(BOT_LOGIN),
                    created_at=long_ago,
                ),
            ],
        )
        gh.add_issue(issue)
        pr = FakePR(
            number=LEGACY_PR,
            head_branch=_issue_branch(LEGACY_ISSUE),
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state="success",
            issue_comments=[
                *pr_conversation,
                FakeComment(
                    id=LATER_COMMENT_ID,
                    body=f":white_check_mark: codex review approved.\n\n{ORCH_MARKER}",
                    user=FakeUser(BOT_LOGIN),
                    created_at=long_ago,
                ),
            ],
            review_comments=[
                FakeComment(
                    id=INLINE_REVIEW_ID,
                    body="line 5: drop the trailing newline",
                    user=FakeUser(HUMAN_LOGIN),
                    created_at=long_ago,
                ),
            ],
            reviews=[
                FakePRReview(
                    id=REVIEW_SUMMARY_ID,
                    body="please rename foo to bar",
                    state="CHANGES_REQUESTED",
                    user=FakeUser(HUMAN_LOGIN),
                    submitted_at=long_ago,
                    commit_id=REVIEWED_SHA,
                ),
            ],
        )
        gh.add_pr(pr)
        # Legacy state: pr_number and the pickup anchor the walk starts from
        # are set, but no watermarks AND no recorded orchestrator_comment_ids.
        # This is the state shape the migration has to handle without
        # replaying its own history or crossing anybody else's.
        gh.seed_state(
            LEGACY_ISSUE,
            pr_number=LEGACY_PR,
            branch=_issue_branch(LEGACY_ISSUE),
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            pickup_comment_id=EARLIER_COMMENT_ID,
        )
        return gh, issue, pr


class LegacyInReviewWatermarkSeedTest(
    unittest.TestCase,
    _LegacyWatermarkFixtureMixin,
):
    """Seed each legacy surface as far as it can go, and no further."""

    def test_our_own_history_is_walked_past(self) -> None:
        # The issue-side seed advances through the leading run of posts the
        # hidden marker proves are ours -- on both IssueComment surfaces --
        # so the pickup greeting, the PR-opened notice, and the approval are
        # never re-read as somebody's review.
        gh, issue, _pr = self._legacy_setup()

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
        self.assertNotIn((LEGACY_ISSUE, "workflow:validating"), gh.label_history)
        self.assertEqual(
            gh.pinned_data(LEGACY_ISSUE).get("pr_last_comment_id"),
            LATER_COMMENT_ID,
        )

    def test_unread_review_feedback_is_not_crossed(self) -> None:
        # The orchestrator posts on neither review surface, so there is no
        # leading run of ours to walk there and nothing a seed could advance
        # past that is not a human's review. Both are seeded at 0 and the
        # review a developer was never shown routes to `fixing`.
        gh, issue, _pr = self._legacy_setup()

        with patch.object(
            config,
            DEBOUNCE_SETTING,
            REVIEW_DEBOUNCE_SECONDS,
        ):
            self._run_in_review(
                gh,
                issue,
                run_agent=_agent(),
            )

        state = gh.pinned_data(LEGACY_ISSUE)
        self.assertEqual(state.get("pr_last_review_comment_id"), 0)
        self.assertEqual(state.get("pr_last_review_summary_id"), 0)
        self.assertIn((LEGACY_ISSUE, FIXING), gh.label_history)
        self.assertEqual(
            state.get("pending_fix_review_max_id"), INLINE_REVIEW_ID,
        )
        self.assertEqual(
            state.get("pending_fix_review_summary_max_id"), REVIEW_SUMMARY_ID,
        )

    def test_a_pre_pickup_pr_comment_is_not_crossed(self) -> None:
        # The migration walks the same seed the approval handoff does, so the
        # pickup boundary is the issue thread's alone here too: a PR comment
        # older than the pickup was in no prompt, and the walk stops under it.
        gh, issue, _pr = self._legacy_setup(pr_conversation=[
            FakeComment(
                id=PRE_PICKUP_PR_COMMENT_ID,
                body=PRE_PICKUP_PR_BODY,
                user=FakeUser(HUMAN_LOGIN),
                created_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        ])

        with patch.object(
            config,
            DEBOUNCE_SETTING,
            REVIEW_DEBOUNCE_SECONDS,
        ):
            self._run_in_review(
                gh,
                issue,
                run_agent=_agent(),
            )

        state = gh.pinned_data(LEGACY_ISSUE)
        self.assertLess(state.get("pr_last_comment_id"), PRE_PICKUP_PR_COMMENT_ID)
        self.assertIn((LEGACY_ISSUE, FIXING), gh.label_history)
        self.assertEqual(
            state.get("pending_fix_issue_max_id"), PRE_PICKUP_PR_COMMENT_ID,
        )

    def test_first_tick_pings_for_mergeable_pr(self) -> None:
        # All gates passing and nothing unread anywhere: the migration must
        # not park or otherwise block the handler from posting the HITL ping.
        gh, issue, pr = self._legacy_setup()
        # Drop the human review feedback (a PR nobody is owed an answer on)
        # and mark the PR as approved on the current head so the gate passes.
        pr.reviews = []
        pr.review_comments = []
        pr.approved = True

        with patch.object(
            config,
            DEBOUNCE_SETTING,
            REVIEW_DEBOUNCE_SECONDS,
        ):
            self._run_in_review(
                gh,
                issue,
                run_agent=_agent(),
            )

        # No merge (humans drive the merge); HITL ping fires for the
        # mergeable PR.
        self.assertEqual(gh.merge_calls, [])
        self.assertNotIn((LEGACY_ISSUE, "done"), gh.label_history)
        ping_comments = [body for _, body in gh.posted_comments if "ready for review/merge" in body]
        self.assertEqual(len(ping_comments), 1)
        self.assertEqual(
            gh.pinned_data(LEGACY_ISSUE).get("ready_ping_sha"),
            REVIEWED_SHA,
        )


class _EmptyWatermarkMigrationFixtureMixin(_PatchedWorkflowMixin):
    def _legacy_setup(self):
        gh = FakeGitHubClient()
        # Make 'truly legacy': no watermarks at all on any surface, no
        # comments anywhere. This is the shape the reviewer flagged --
        # snapshot-failed handoff or pre-feature in_review state with an
        # empty PR.
        issue = make_issue(EMPTY_WATERMARK_ISSUE, label="in_review")
        gh.add_issue(issue)
        pr = FakePR(
            number=EMPTY_WATERMARK_PR,
            head_branch=_issue_branch(EMPTY_WATERMARK_ISSUE),
            head=FakePRRef(sha=REVIEWED_SHA),
            mergeable=True,
            check_state="success",
        )
        gh.add_pr(pr)
        gh.seed_state(
            EMPTY_WATERMARK_ISSUE,
            pr_number=EMPTY_WATERMARK_PR,
            branch=_issue_branch(EMPTY_WATERMARK_ISSUE),
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
        )
        return gh, issue, pr


class LegacyMigrationPersistsEmptyWatermarksTest(
    unittest.TestCase,
    _EmptyWatermarkMigrationFixtureMixin,
):
    """Persist zero watermarks so first feedback remains visible."""

    def test_first_inline_review_surfaces(self) -> None:
        gh, issue, pr = self._legacy_setup()

        # Tick 1: legacy migration runs on an issue with nothing on any
        # surface. It must persist 0 on every namespace anyway, so the read
        # that follows is a scan rather than a migration decision.
        self._run_in_review(
            gh,
            issue,
            run_agent=_agent(),
        )
        state = gh.pinned_data(EMPTY_WATERMARK_ISSUE)
        self.assertEqual(state.get("pr_last_review_comment_id"), 0)
        self.assertEqual(state.get("pr_last_review_summary_id"), 0)
        self.assertEqual(state.get("pr_last_comment_id"), 0)

        # Now a human posts the first inline review comment. With the fix,
        # the next tick sees pr_last_review_comment_id=0 (already set) and
        # surfaces id=42 rather than re-running the migration over it.
        pr.review_comments.append(
            FakeComment(
                id=FIRST_INLINE_REVIEW_ID,
                body="line 7: rename foo to bar",
                user=FakeUser(HUMAN_LOGIN),
                created_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        )

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

        # The first inline review comment after migration is treated as
        # fresh feedback and routes the issue to `fixing` (no dev spawn
        # here; the fixing handler owns that step).
        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(gh.merge_calls, [])
        self.assertIn((EMPTY_WATERMARK_ISSUE, FIXING), gh.label_history)
        self.assertEqual(
            gh.pinned_data(EMPTY_WATERMARK_ISSUE).get("pending_fix_review_max_id"),
            FIRST_INLINE_REVIEW_ID,
        )

    def test_first_review_summary_surfaces(self) -> None:
        # Same shape on the review-summary surface. A COMMENTED summary
        # body must still surface through the fresh-feedback scan, and the
        # 0 the migration persists is what says the surface is seeded
        # without claiming anything on it has been read.
        gh, issue, pr = self._legacy_setup()
        gh.seed_state(
            EMPTY_WATERMARK_ISSUE,
            pr_number=EMPTY_WATERMARK_PR,
            branch=_issue_branch(EMPTY_WATERMARK_ISSUE),
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
        )

        self._run_in_review(
            gh,
            issue,
            run_agent=_agent(),
        )
        state = gh.pinned_data(EMPTY_WATERMARK_ISSUE)
        self.assertEqual(state.get("pr_last_review_summary_id"), 0)

        pr.reviews.append(
            FakePRReview(
                id=FIRST_REVIEW_SUMMARY_ID,
                body="please tighten the spec",
                state="COMMENTED",
                user=FakeUser(HUMAN_LOGIN),
                submitted_at=datetime.now(UTC) - timedelta(hours=1),
                commit_id=REVIEWED_SHA,
            ),
        )

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
        self.assertEqual(gh.merge_calls, [])
        self.assertIn((EMPTY_WATERMARK_ISSUE, FIXING), gh.label_history)
        self.assertEqual(
            gh.pinned_data(EMPTY_WATERMARK_ISSUE).get("pending_fix_review_summary_max_id"),
            FIRST_REVIEW_SUMMARY_ID,
        )
