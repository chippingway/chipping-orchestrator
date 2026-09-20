# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for in_review feedback watermark handling: how far a park's own
message may carry the mark, and the split issue / inline-review id
namespaces."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    _agent,
    _PatchedWorkflowMixin,
)

PARK_ISSUE = 60
PARK_PR = 70
PARK_BRANCH = "orchestrator/chippingway__orchestrator/issue-60"
HANDOFF_WATERMARK = 900
SPLIT_WATERMARK_ISSUE = 65
SPLIT_WATERMARK_PR = 95
SPLIT_WATERMARK_BRANCH = "orchestrator/chippingway__orchestrator/issue-65"
INLINE_COMMENT_ID = 42
INLINE_COMMENT_WATERMARK = 41
# Above the handoff watermark and below every id the double mints, which is
# where a comment written while the tick was deciding lands.
CONCURRENT_PR_COMMENT_ID = 950
CONCURRENT_ISSUE_COMMENT_ID = 960
CONCURRENT_BODY = "hold off, the migration needs a rollback path"
HUMAN = "alice"
RUN_AGENT = "run_agent"
FIXING = "workflow:fixing"
PR_CONVERSATION = "pr conversation"
ISSUE_THREAD = "issue thread"


class _WriteMeanwhile:
    """A human writing while the tick is deciding, on either surface.

    Their comment is numbered in the space both surfaces share, so it lands
    BELOW the notice the park posts right after it -- which is the ordering a
    mark carried to the newest comment would skip for good, on the pull
    request by the issue-side watermark and on the thread by the delivery
    cursor an unbounded park would stamp at that notice.
    """

    def __init__(self, posted, thread, comment):
        self.posted = posted
        self.thread = thread
        self.comment = comment

    def __call__(self, parked_issue, body):
        self.thread.append(self.comment)
        return self.posted(parked_issue, body)


class InReviewParkWatermarkTest(unittest.TestCase, _PatchedWorkflowMixin):
    """A park inside `_handle_in_review` posts an issue comment. The watermark
    must be bumped past that comment so the next tick does not see the
    orchestrator's own HITL park message as fresh PR feedback and route
    the issue to `fixing` against it.
    """

    def assert_initial_park(self, github, issue) -> int:
        state = github.pinned_data(PARK_ISSUE)
        self.assertTrue(state.get("awaiting_human"))
        self.assertEqual(state.get("park_reason"), "unmergeable")
        comments_after_park = len(github.posted_comments)
        self.assertGreater(comments_after_park, 0)
        # Nothing else stood on either surface, so the walk reached the
        # notice the park just posted -- which is also the newest comment.
        self.assertEqual(
            state.get("pr_last_comment_id"),
            github.latest_comment_id(issue),
        )
        return comments_after_park

    def test_park_does_not_replay_next_tick(self) -> None:
        # An unmergeable PR parks awaiting human on the first tick. The
        # park message is recorded as orchestrator-authored and the
        # watermark is carried over it; subsequent ticks must not surface
        # the park message as fresh PR feedback.
        gh, issue, _pr = self._park_setup()

        # Tick 1: unmergeable park.
        self._run_in_review(
            gh,
            issue,
            run_agent=_agent(),
        )
        comments_after_park = self.assert_initial_park(gh, issue)

        # Tick 2: nothing new; must NOT route the orchestrator's park
        # message back through the fixing route.
        mocks = self._run_in_review(
            gh,
            issue,
            run_agent=_agent(),
        )
        mocks[RUN_AGENT].assert_not_called()
        # No additional comments posted (no second park, no fixing route).
        self.assertEqual(len(gh.posted_comments), comments_after_park)
        self.assertNotIn((PARK_ISSUE, FIXING), gh.label_history)

    def test_park_stops_at_a_meanwhile_comment(self) -> None:
        for surface, comment_id in (
            (PR_CONVERSATION, CONCURRENT_PR_COMMENT_ID),
            (ISSUE_THREAD, CONCURRENT_ISSUE_COMMENT_ID),
        ):
            with self.subTest(surface=surface):
                self._assert_meanwhile_survives(surface, comment_id)

    def _assert_meanwhile_survives(self, surface, comment_id) -> None:
        gh, issue, pr = self._park_setup()
        meanwhile = _WriteMeanwhile(
            gh.comment,
            pr.issue_comments if surface == PR_CONVERSATION else issue.comments,
            FakeComment(
                id=comment_id,
                body=CONCURRENT_BODY,
                user=FakeUser(HUMAN),
                created_at=datetime.now(UTC) - timedelta(hours=1),
            ),
        )

        with patch.object(gh, "comment", meanwhile):
            self._run_in_review(gh, issue, run_agent=_agent())

        # The park stands and the issue-side mark stopped under the comment
        # nobody read.
        self.assertTrue(gh.pinned_data(PARK_ISSUE).get("awaiting_human"))
        self.assertEqual(
            gh.pinned_data(PARK_ISSUE).get("pr_last_comment_id"),
            HANDOFF_WATERMARK,
        )

        # So the next tick still finds it and routes it to `fixing` -- which
        # on the issue thread also takes the bounded park, since an unbounded
        # one would have stamped the delivery cursor at the notice above it
        # and the scan drops everything that cursor covers.
        mocks = self._run_in_review(gh, issue, run_agent=_agent())

        mocks[RUN_AGENT].assert_not_called()
        self.assertIn((PARK_ISSUE, FIXING), gh.label_history)
        self.assertEqual(
            gh.pinned_data(PARK_ISSUE).get("pending_fix_issue_max_id"),
            comment_id,
        )


    def _park_setup(self):
        gh = FakeGitHubClient()
        issue = make_issue(PARK_ISSUE, label="in_review")
        gh.add_issue(issue)
        pr = FakePR(
            number=PARK_PR,
            head_branch=PARK_BRANCH,
            head=FakePRRef(sha="cafe1234"),
            approved=True,
            approval_head_sha="cafe1234",
            mergeable=False,
            check_state="success",
        )
        gh.add_pr(pr)
        gh.seed_state(
            PARK_ISSUE,
            pr_number=PARK_PR,
            branch=PARK_BRANCH,
            dev_agent="claude",
            dev_session_id="dev-sess",
            pr_last_comment_id=HANDOFF_WATERMARK,  # an old watermark from validating handoff
            last_action_comment_id=HANDOFF_WATERMARK,
        )
        return gh, issue, pr


class _SplitWatermarkFixtureMixin(_PatchedWorkflowMixin):
    def _setup(self, *, issue_comments=(), review_comments=(), state_extra=None):
        gh = FakeGitHubClient()
        issue = make_issue(SPLIT_WATERMARK_ISSUE, label="in_review")
        gh.add_issue(issue)
        pr = FakePR(
            number=SPLIT_WATERMARK_PR,
            head_branch=SPLIT_WATERMARK_BRANCH,
            head=FakePRRef(sha="cafe1234"),
            issue_comments=list(issue_comments),
            review_comments=list(review_comments),
        )
        gh.add_pr(pr)
        state = {
            "pr_number": SPLIT_WATERMARK_PR,
            "branch": SPLIT_WATERMARK_BRANCH,
            "dev_agent": "claude",
            "dev_session_id": "dev-sess",
        }
        if state_extra:
            state.update(state_extra)
        gh.seed_state(SPLIT_WATERMARK_ISSUE, **state)
        return gh, issue, pr


class InReviewSplitWatermarkTest(
    unittest.TestCase,
    _SplitWatermarkFixtureMixin,
):
    """Track issue and inline-review ids in independent namespaces."""

    def test_inline_review_comment_routes_to_fixing(self) -> None:
        gh, issue = self._setup(
            review_comments=[
                FakeComment(
                    id=INLINE_COMMENT_ID,
                    body="line 12: rename foo to bar",
                    user=FakeUser("alice"),
                    created_at=datetime.now(UTC) - timedelta(hours=1),
                ),
            ],
            # Inline-review watermark just below the comment id, so the
            # assertion below can tell "the route left it alone" from the 0
            # the legacy migration seeds an unset surface at.
            state_extra={"pr_last_review_comment_id": INLINE_COMMENT_WATERMARK},
        )[:2]

        mocks = self._run_in_review(
            gh,
            issue,
            run_agent=_agent(),
        )

        mocks[RUN_AGENT].assert_not_called()
        self.assertIn((SPLIT_WATERMARK_ISSUE, FIXING), gh.label_history)
        self.assertNotIn((SPLIT_WATERMARK_ISSUE, "workflow:validating"), gh.label_history)
        state = gh.pinned_data(SPLIT_WATERMARK_ISSUE)
        # Bookmark recorded but the inline-review watermark stays where it
        # was -- the fixing handler needs the triggering comment.
        self.assertEqual(state.get("pending_fix_review_max_id"), INLINE_COMMENT_ID)
        self.assertEqual(state.get("pr_last_review_comment_id"), INLINE_COMMENT_WATERMARK)

    def test_cross_space_id_overlap_keeps_comments(self) -> None:
        # Inline review comment id (5) is LOWER than the issue-comment
        # watermark (1000). With one merged-id watermark this comment would
        # be silently filtered out; with split watermarks it gets through
        # and triggers the route to `fixing`.
        long_ago = datetime.now(UTC) - timedelta(hours=1)
        gh, issue, _pr = self._setup(
            review_comments=[
                FakeComment(
                    id=5,
                    body="please add a docstring",
                    user=FakeUser("alice"),
                    created_at=long_ago,
                ),
            ],
            # Issue-side watermark high (1000), inline-review watermark low (4)
            # -- the two ratchet independently, and id=5 must still surface.
            state_extra={
                "pr_last_comment_id": 1000,
                "pr_last_review_comment_id": 4,
            },
        )

        mocks = self._run_in_review(
            gh,
            issue,
            run_agent=_agent(),
        )

        # The inline comment surfaces and routes to fixing even though
        # id=5 < pr_last_comment_id=1000.
        mocks[RUN_AGENT].assert_not_called()
        self.assertIn((SPLIT_WATERMARK_ISSUE, FIXING), gh.label_history)
        self.assertEqual(gh.pinned_data(SPLIT_WATERMARK_ISSUE).get("pending_fix_review_max_id"), 5)
