# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pull-request services for the in-memory GitHub client."""
from __future__ import annotations

from collections.abc import Iterable

from orchestrator.github import pull_request_reads as _pr_reads
from orchestrator.github.pinned_state import PINNED_STATE_MARKER
from tests.support.github.model_helpers import _review_has_feedback
from tests.support.github.models import FakeComment, FakeLabel, FakeUser
from tests.support.github.pr_helpers import (
    _pr_combined_check_state,
    _pr_has_changes_requested,
    _pr_has_label,
    _pr_is_approved,
    _pr_is_mergeable,
    _pr_state,
)
from tests.support.github.pull_request_models import FakePR, FakePRRef, FakePRRepo, FakePRReview

_STATE_CLOSED = "closed"
_STATE_OPEN = "open"


class _PullCreationService:
    pr_has_label = _pr_has_label

    def open_pr(
        self,
        *,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> FakePR:
        pull_request = FakePR(
            number=next(self._pr_id),
            head_branch=branch,
            base_branch=base,
            title=title,
            body=body,
            # GitHub always answers with the ref the pull request is open on
            # and the repository that ref lives in, and readers that ask which
            # publication a recorded number names read both here: a head left
            # at its default says the pull request is on no branch and in no
            # repository, which no real one ever is.
            head=FakePRRef(
                ref=branch, repo=FakePRRepo(full_name=self._repo_slug),
            ),
        )
        self.opened_prs.append(pull_request)
        # Held and findable from here on, as GitHub holds one: a pull request
        # that has been opened IS the open pull request on its branch, and a
        # double that answered a later lookup with nothing would report a
        # second one being opened over the same work as working.
        self.add_pr(pull_request)
        self.existing_open_pr[branch] = pull_request
        return pull_request

    def pr_comment(self, pr_number: int, body: str) -> FakeComment:
        new_comment = FakeComment(
            id=self._next_comment_id(),
            body=body,
            user=FakeUser("orchestrator"),
        )
        self.posted_pr_comments.append((pr_number, body))
        pull_request = self.pulls.get(pr_number)
        if pull_request is not None:
            pull_request.issue_comments.append(new_comment)
        return new_comment

    def find_open_pr(
        self, *, branch: str, base: str | None = None,
    ) -> FakePR | None:
        """The open pull request on this head branch, filtered as GitHub does.

        `base` is honored rather than ignored, because omitting it is what a
        caller asking whether anybody is still standing on the branch does --
        and a double that answered the same either way would report that
        widening as working while the real query still narrowed.
        """
        found = self.existing_open_pr.get(branch)
        if found is None or base in (None, found.base_branch):
            return found
        return None

    def iter_open_prs(self) -> Iterable[FakePR]:
        return [
            pull_request
            for pull_request in self.pulls.values()
            if pull_request.state == _STATE_OPEN
        ]

    def add_pr_label(self, pr: FakePR, label_name: str) -> None:
        if not self.pr_has_label(pr, label_name):
            pr.labels.append(FakeLabel(label_name))

    def add_pr(self, pr: FakePR) -> None:
        """Hold one pull request, and say which repository its head is in.

        Stamped here rather than on the model because only a client knows the
        answer: on GitHub a same-repo branch's head repo IS the repository the
        pull request lives in, and a fixture building the object has no client
        yet. A case that named one is writing a FORK, which is the whole
        reason anything reads this field, so it is left exactly as it stands.

        Only a plain model is stamped. A pull request wrapped to refuse one of
        its lazy reads is held exactly as handed over: reaching through it here
        would raise the very failure the wrapper exists to deliver to the
        reader under test, and the model inside it was stamped when it was
        added.
        """
        if isinstance(pr, FakePR) and not pr.head.repo.full_name:
            pr.head.repo.full_name = self._repo_slug
        self.pulls[pr.number] = pr

    def get_pr(self, pr_number: int) -> FakePR:
        return self.pulls[pr_number]


class _PullBodyService:
    """The two ways a description is rewritten, each recorded as an edit."""

    def edit_pr_body(self, pr: FakePR, body: str) -> None:
        self.edited_pr_bodies.append((pr.number, body))
        pr.body = body

    def edit_unchanged_pr_body(
        self, pr_number: int, expected: str | None, body: str,
    ) -> bool:
        """Rewrite the held pull request's body unless it moved off `expected`."""
        held = self.pulls[pr_number]
        if (held.body or "") != (expected or ""):
            return False
        self.edit_pr_body(held, body)
        return True


class _PullStatusService(_PullBodyService):
    pr_state = _pr_state
    pr_is_mergeable = _pr_is_mergeable
    pr_is_approved = _pr_is_approved
    pr_has_changes_requested = _pr_has_changes_requested
    pr_combined_check_state = _pr_combined_check_state

    def find_pr_for_commit(
        self, *, branch: str, head_sha: str, base: str | None = None,
    ) -> FakePR | None:
        """The PR on this branch carrying `head_sha`, whatever state it is in.

        Searched over every PR the fake holds rather than over the open-PR
        table beside it, since the whole point of the real lookup is the one a
        merge has already closed -- and by the commits it carries as well as by
        its head, since a human pushing to the branch moves one and not the
        other.

        `unreadable_pr_commits` names the PRs whose commit list GitHub refuses,
        which the real client answers with `PR_LOOKUP_UNREADABLE` rather than
        with "does not carry it": the head is still free to match, and only a
        candidate that had to be asked about its commits and could not be
        leaves the whole lookup unanswered. `unreadable_pr_lookups` is the same
        answer one level up -- the enumeration itself failing, which reaches no
        candidate at all.
        """
        if branch in self.unreadable_pr_lookups:
            return _pr_reads.PR_LOOKUP_UNREADABLE
        unreadable = False
        for pull_request in self.pulls.values():
            carries = self._pr_carries(pull_request, branch, head_sha, base)
            if carries:
                return pull_request
            unreadable = unreadable or carries is None
        if unreadable:
            return _pr_reads.PR_LOOKUP_UNREADABLE
        return None

    def merge_pr(
        self,
        pr: FakePR,
        *,
        sha: str,
        method: str = "squash",
    ) -> bool:
        self.merge_calls.append((pr.number, sha, method))
        if not self.merge_returns_ok:
            return False
        pr.merged = True
        pr.state = _STATE_CLOSED
        return True

    def supersede_pr(
        self,
        pr: FakePR,
        *,
        notice: str,
        marker: str,
        carries_marker: bool | None = None,
    ) -> bool:
        """Post one marked supersession notice and close an open PR.

        Idempotent through the thread, exactly as the real helper is: the
        marker is looked for among the pull request's own conversation
        comments, so a second call after a crash adds nothing and closes
        nothing that is already settled.

        `carries_marker` is that search already made, and it is honored here
        for the reason the real helper honors it: the search is a request, and
        a caller that hands over an answer it already has leaves no round-trip
        between its own proof and this write. Every scan this fake DOES make
        is recorded, so a test can say that a mutation path took none.
        """
        if pr.number in self.unsupersedable_prs:
            return False
        if carries_marker is None:
            carries_marker = self._pr_carries_marker(pr, marker)
        if not carries_marker:
            self.pr_comment(pr.number, notice)
        if self.pr_state(pr) == _STATE_OPEN:
            pr.state = _STATE_CLOSED
        return True

    def delete_remote_branch(self, branch: str) -> bool:
        self.deleted_remote_branches.append(branch)
        return self.delete_remote_branch_returns_ok

    def _pr_carries_marker(self, pr: FakePR, marker: str) -> bool:
        """Whether this thread already carries `marker`, recording the ask."""
        self.marker_scans.append(pr.number)
        return any(
            marker in (pr_comment.body or "")
            for pr_comment in pr.issue_comments
        )

    def _pr_carries(
        self, pr: FakePR, branch: str, head_sha: str, base: str | None,
    ) -> bool | None:
        """Whether one PR carries the commit, or None when it cannot be read.

        Filtered by base only when the caller named one, which is the query
        the real client builds: a caller asking whether GitHub holds this
        commit at all names none, and a pull request retargeted onto another
        base still carries it.
        """
        if pr.head_branch != branch:
            return False
        if base is not None and pr.base_branch != base:
            return False
        if pr.head.sha == head_sha:
            return True
        if pr.number in self.unreadable_pr_commits:
            return None
        return head_sha in pr.commit_shas


class _PullFeedbackService:
    def pr_conversation_comments_after(
        self,
        pr: FakePR,
        after_id: int | None,
    ) -> list[FakeComment]:
        comments = _comments_after(pr.issue_comments, after_id)
        comments.sort(key=lambda listed_comment: listed_comment.id)
        return comments

    def pr_inline_comments_after(
        self,
        pr: FakePR,
        after_id: int | None,
    ) -> list[FakeComment]:
        comments = _comments_after(pr.review_comments, after_id)
        comments.sort(key=lambda listed_comment: listed_comment.id)
        return comments

    def pr_reviews_after(
        self,
        pr: FakePR,
        after_id: int | None,
    ) -> list[FakePRReview]:
        return sorted(
            (
                review
                for review in pr.reviews
                if _review_has_feedback(review)
                and (after_id is None or review.id > after_id)
            ),
            key=lambda review: review.id,
        )

    def _for_worker_thread(self):
        return self


def _comments_after(
    comments: Iterable[FakeComment],
    after_id: int | None,
) -> list[FakeComment]:
    return [
        comment
        for comment in comments
        if PINNED_STATE_MARKER not in (comment.body or "")
        and (after_id is None or comment.id > after_id)
    ]
