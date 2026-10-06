# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Head-review verdicts and unread feedback on the `reviews` owner."""
from __future__ import annotations

import unittest

from orchestrator.github import reviews as _reviews
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PINNED_STATE_TEMPLATE
from tests.support.fakes import FakeComment, FakePRReview, FakeUser

_HEAD_SHA = "f00dcafe"
_STALE_SHA = "deadbeef"
_APPROVED = "APPROVED"
_CHANGES_REQUESTED = "CHANGES_REQUESTED"
_COMMENTED = "COMMENTED"
_REVIEWER = "alice"
_OTHER_REVIEWER = "bob"
_FEEDBACK_BODY = "please rename the helper"
_PINNED_BODY = PINNED_STATE_TEMPLATE.format(payload='{"branch": "main"} ')


def _review(
    review_id: int,
    state: str,
    *,
    body: str = "",
    login: str = _REVIEWER,
    commit_id: str = _HEAD_SHA,
) -> FakePRReview:
    return FakePRReview(
        id=review_id,
        body=body,
        state=state,
        user=FakeUser(login) if login else None,
        commit_id=commit_id,
    )


# Review as GitHub serves it -> the `(reviewer, (id, state))` record the
# per-head aggregation keeps, or `None` when the review is not a head verdict.
_HEAD_REVIEW_CASES = (
    (_review(1, _APPROVED), (_REVIEWER, (1, _APPROVED))),
    (_review(2, "approved"), (_REVIEWER, (2, _APPROVED))),
    (_review(3, "DISMISSED"), (_REVIEWER, (3, "DISMISSED"))),
    (_review(4, _APPROVED, commit_id=_STALE_SHA), None),
    (_review(5, "PENDING"), None),
    (_review(6, _APPROVED, login=""), None),
)

# `(state, body, after_id)` -> whether the summary carries unread feedback.
_ACTIONABLE_SUMMARY_CASES = (
    ((_CHANGES_REQUESTED, _FEEDBACK_BODY, None), True),
    ((_COMMENTED, _FEEDBACK_BODY, 4), True),
    ((_COMMENTED, _FEEDBACK_BODY, 7), False),
    ((_APPROVED, _FEEDBACK_BODY, None), False),
    ((_COMMENTED, "   ", None), False),
)

# Head-review set -> `(pr_is_approved, pr_has_changes_requested)`.
_VERDICT_CASES = (
    ((), (False, False)),
    ((_review(1, _APPROVED),), (True, False)),
    ((_review(1, "DISMISSED"),), (False, False)),
    ((_review(1, _CHANGES_REQUESTED),), (False, True)),
    (
        (
            _review(1, _APPROVED),
            _review(2, _CHANGES_REQUESTED, login=_OTHER_REVIEWER),
        ),
        (False, True),
    ),
    ((_review(1, _APPROVED, commit_id=_STALE_SHA),), (False, False)),
)

_UNREAD_COMMENTS = (
    FakeComment(id=9, body="later"),
    FakeComment(id=3, body="earlier"),
    FakeComment(id=8, body=_PINNED_BODY),
    FakeComment(id=1, body="already read"),
)
# Client method -> the PR surface it reads; both filter and sort identically.
_COMMENT_SURFACES = (
    ("pr_conversation_comments_after", "conversation_page"),
    ("pr_inline_comments_after", "inline_page"),
)


class _ReviewedPR:
    """PyGithub-shaped PR whose feedback surfaces are in-memory pages."""

    def __init__(
        self,
        *,
        review_page: tuple = (),
        conversation_page: tuple = (),
        inline_page: tuple = (),
    ) -> None:
        self._review_page = review_page
        self._conversation_page = conversation_page
        self._inline_page = inline_page
        self.review_fetches = 0

    def get_reviews(self) -> tuple:
        self.review_fetches += 1
        return self._review_page

    def get_issue_comments(self) -> tuple:
        return self._conversation_page

    def get_review_comments(self) -> tuple:
        return self._inline_page


class HeadReviewAggregationTest(unittest.TestCase):
    """Each reviewer contributes one state: their latest on the current head.

    A review on an earlier commit says nothing about the code that is up for
    merge now, an author-less record cannot be attributed to a reviewer, and
    an undecided state is not a verdict, so all three drop out of the fold.
    """

    def test_classifies_reviews_against_the_head(self) -> None:
        for review, expected in _HEAD_REVIEW_CASES:
            with self.subTest(review_id=review.id):
                self.assertEqual(
                    _reviews.review_state_for_head(review, _HEAD_SHA),
                    expected,
                )

    def test_unknown_head_skips_the_fetch(self) -> None:
        # An empty head sha leaves no commit to gate on, so every verdict is
        # withheld rather than read off the PR.
        pull_request = _ReviewedPR(review_page=(_review(1, _APPROVED),))

        self.assertEqual(
            _reviews.latest_review_states_for_head(
                pull_request,
                head_sha="",
            ),
            [],
        )
        self.assertEqual(pull_request.review_fetches, 0)

    def test_highest_id_per_reviewer_wins(self) -> None:
        # GitHub does not guarantee review order, so a reviewer who vetoes
        # after approving must land as a veto whichever way the page arrives.
        pull_request = _ReviewedPR(review_page=(
            _review(5, _CHANGES_REQUESTED),
            _review(1, _APPROVED),
            _review(2, _APPROVED, login=_OTHER_REVIEWER),
            _review(9, _APPROVED, login="carol", commit_id=_STALE_SHA),
        ))

        states = _reviews.latest_review_states_for_head(
            pull_request,
            head_sha=_HEAD_SHA,
        )

        self.assertEqual(sorted(states), [_APPROVED, _CHANGES_REQUESTED])


class _ReviewClientTestCase(unittest.TestCase):
    """Fixture handing each case a client with no network behind it."""

    def setUp(self) -> None:
        # Bypass the networked __init__; the review methods read only the PR.
        self.gh = GitHubClient.__new__(GitHubClient)


class UnreadFeedbackTest(_ReviewClientTestCase):
    """Feedback surfaces yield what a developer has not answered yet.

    The pinned-state comment is rewritten on the PR conversation every tick and
    an approval is a verdict rather than a request, so counting either as
    feedback would restart the fix loop forever. Callers consume the result in
    id order to advance one watermark.
    """

    def test_summary_filters_state_and_watermark(self) -> None:
        # An inline-only review posts an empty summary beside its comments, so
        # a blank body is not on its own something to answer.
        for (state, body, after_id), expected in _ACTIONABLE_SUMMARY_CASES:
            with self.subTest(state=state, after_id=after_id):
                self.assertIs(
                    _reviews.is_actionable_review_summary(
                        _review(7, state, body=body),
                        after_id,
                    ),
                    expected,
                )

    def test_returns_unread_comments_in_id_order(self) -> None:
        for method_name, page_name in _COMMENT_SURFACES:
            with self.subTest(method=method_name):
                pull_request = _ReviewedPR(**{page_name: _UNREAD_COMMENTS})
                read_after = getattr(self.gh, method_name)

                self.assertEqual(
                    [comment.id for comment in read_after(pull_request, 2)],
                    [3, 9],
                )
                self.assertEqual(
                    [comment.id for comment in read_after(pull_request, None)],
                    [1, 3, 9],
                )

    def test_the_whole_thread_leaves_nothing_out(self) -> None:
        # A caller finding words it posted itself reads the conversation
        # whole, in id order: a body quoting the pinned state's marker -- a
        # reviewer's findings may -- is kept, and so is one already read.
        pull_request = _ReviewedPR(conversation_page=_UNREAD_COMMENTS)

        self.assertEqual(
            [comment.id for comment in self.gh.pr_conversation_thread(pull_request)],
            [1, 3, 8, 9],
        )

    def test_reviews_after_keeps_only_unread_feedback(self) -> None:
        pull_request = _ReviewedPR(review_page=(
            _review(8, _COMMENTED, body=_FEEDBACK_BODY),
            _review(6, _CHANGES_REQUESTED, body=_FEEDBACK_BODY),
            _review(7, _APPROVED, body="ship it"),
            _review(4, _COMMENTED, body=_FEEDBACK_BODY),
        ))

        unread = self.gh.pr_reviews_after(pull_request, 5)

        self.assertEqual([review.id for review in unread], [6, 8])


class ReviewVerdictTest(_ReviewClientTestCase):
    """Approval needs a current-head yes and no current-head veto.

    A veto outranks a co-reviewer's approval, `DISMISSED` withdraws a verdict
    without becoming one, and an approval left on a superseded commit does not
    carry over to the head the merge gate is about to act on.
    """

    def test_reads_verdicts_off_the_head_reviews(self) -> None:
        for head_reviews, expected in _VERDICT_CASES:
            states = [review.state for review in head_reviews]
            with self.subTest(states=states):
                self.assertEqual(self._verdicts(head_reviews), expected)

    def _verdicts(self, head_reviews: tuple) -> tuple[bool, bool]:
        pull_request = _ReviewedPR(review_page=head_reviews)
        return (
            self.gh.pr_is_approved(pull_request, head_sha=_HEAD_SHA),
            self.gh.pr_has_changes_requested(pull_request, head_sha=_HEAD_SHA),
        )


class ReviewOwnershipTest(unittest.TestCase):
    """The composed client resolves its review surface from the owner.

    The verdict methods and the head-state aggregation reach the client through
    the owner's mixin and static alias, so a monkeypatch on the owner stays
    observable rather than hitting a divergent copy.
    """

    def test_client_inherits_the_review_mixin_owner(self) -> None:
        self.assertIn(_reviews.GitHubReviewMixin, GitHubClient.__mro__)

    def test_static_helper_alias_yields_the_function(self) -> None:
        # The head-state aggregation is bound onto the client unchanged, so the
        # classmethod verdicts call the module function rather than a bound one.
        self.assertIs(
            GitHubClient._latest_review_states_for_head,
            _reviews.latest_review_states_for_head,
        )


if __name__ == "__main__":
    unittest.main()
