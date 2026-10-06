# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Current-head review verdicts, feedback watermarks, and the client mixin."""
from __future__ import annotations

from typing import Any

from github.IssueComment import IssueComment
from github.PullRequest import PullRequest

from orchestrator.github import pinned_state
from orchestrator.github.aliases import StaticMethodAlias

REVIEW_CHANGES_REQUESTED = "CHANGES_REQUESTED"
REVIEW_APPROVED = "APPROVED"
_ReviewStateForHead = tuple[str, tuple[int, str]]


def review_state_for_head(
    review: Any,
    head_sha: str,
) -> _ReviewStateForHead | None:
    """Return a head review as ``(reviewer, (id, state))``, else ``None``."""
    if (getattr(review, "commit_id", "") or "") != head_sha:
        return None
    review_state = (review.state or "").upper()
    if review_state not in (
        REVIEW_APPROVED,
        REVIEW_CHANGES_REQUESTED,
        "DISMISSED",
    ):
        return None
    reviewer_login = review.user.login if review.user else ""
    if not reviewer_login:
        return None
    review_id = getattr(review, "id", 0) or 0
    return reviewer_login, (review_id, review_state)


def record_latest_review(
    latest_per_user: dict[str, tuple[int, str]],
    candidate: tuple[str, tuple[int, str]],
) -> None:
    """Keep only each reviewer's highest-id review record."""
    reviewer_login, review_record = candidate
    previous_review = latest_per_user.get(reviewer_login)
    if previous_review is None or review_record[0] > previous_review[0]:
        latest_per_user[reviewer_login] = review_record


def latest_review_states_for_head(
    pr: PullRequest,
    *,
    head_sha: str,
) -> list[str]:
    """Return each reviewer's latest state on the current PR head."""
    if not head_sha:
        return []
    latest_per_user: dict[str, tuple[int, str]] = {}
    for review in pr.get_reviews():
        candidate = review_state_for_head(review, head_sha)
        if candidate is not None:
            record_latest_review(latest_per_user, candidate)
    return [
        review_state
        for _, review_state in latest_per_user.values()
    ]


def is_actionable_review_summary(
    review: Any,
    after_id: int | None,
) -> bool:
    """Return whether a review summary carries unread developer feedback."""
    review_state = (review.state or "").upper()
    if review_state not in (REVIEW_CHANGES_REQUESTED, "COMMENTED"):
        return False
    if not (review.body or "").strip():
        return False
    return after_id is None or review.id > after_id


LATEST_REVIEW_STATES_METHOD = StaticMethodAlias(latest_review_states_for_head)


class GitHubReviewMixin:
    """Current-head review verdicts and unread PR feedback surfaces."""

    _latest_review_states_for_head = LATEST_REVIEW_STATES_METHOD

    def pr_conversation_comments_after(
        self,
        pr: PullRequest,
        after_id: int | None,
    ) -> list[IssueComment]:
        """Return PR conversation comments newer than their watermark."""
        pr_comments: list[IssueComment] = []
        for pr_comment in pr.get_issue_comments():
            if pinned_state.PINNED_STATE_MARKER in (pr_comment.body or ""):
                continue
            if after_id is None or pr_comment.id > after_id:
                pr_comments.append(pr_comment)
        pr_comments.sort(key=lambda comment: comment.id)
        return pr_comments

    def pr_conversation_thread(self, pr: PullRequest) -> list[IssueComment]:
        """Return every PR conversation comment in id order, none left out.

        Unlike `pr_conversation_comments_after`, a body carrying the pinned
        state's marker is kept: a caller matching words it posted itself must
        find them even where those words quote that marker.
        """
        return sorted(pr.get_issue_comments(), key=lambda comment: comment.id)

    def pr_inline_comments_after(
        self,
        pr: PullRequest,
        after_id: int | None,
    ) -> list:
        """Return inline review comments newer than their own watermark."""
        review_comments: list = []
        for review_comment in pr.get_review_comments():
            if pinned_state.PINNED_STATE_MARKER in (review_comment.body or ""):
                continue
            if after_id is None or review_comment.id > after_id:
                review_comments.append(review_comment)
        review_comments.sort(key=lambda comment: comment.id)
        return review_comments

    def pr_reviews_after(
        self,
        pr: PullRequest,
        after_id: int | None,
    ) -> list:
        """Return actionable review summaries newer than their watermark."""
        review_summaries = [
            candidate_review
            for candidate_review in pr.get_reviews()
            if is_actionable_review_summary(candidate_review, after_id)
        ]
        review_summaries.sort(key=lambda review_summary: review_summary.id)
        return review_summaries

    @classmethod
    def pr_has_changes_requested(
        cls,
        pr: PullRequest,
        *,
        head_sha: str,
    ) -> bool:
        """Return whether any reviewer's latest head review is a veto."""
        return any(
            review_state == REVIEW_CHANGES_REQUESTED
            for review_state in cls._latest_review_states_for_head(
                pr,
                head_sha=head_sha,
            )
        )

    @classmethod
    def pr_is_approved(
        cls,
        pr: PullRequest,
        *,
        head_sha: str,
    ) -> bool:
        """Require one current-head approval and no current-head veto."""
        review_states = cls._latest_review_states_for_head(
            pr,
            head_sha=head_sha,
        )
        if not review_states:
            return False
        if any(
            review_state == REVIEW_CHANGES_REQUESTED
            for review_state in review_states
        ):
            return False
        return any(
            review_state == REVIEW_APPROVED
            for review_state in review_states
        )
