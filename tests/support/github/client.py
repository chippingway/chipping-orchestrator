# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Composition root for the in-memory GitHub client."""
from __future__ import annotations

from collections.abc import Iterable
from itertools import count

from tests.support.github import issues as issue_service, pr_service as pull_service, pr_views as pull_views
from tests.support.github.comment_ids import _FIRST_COMMENT_ID, _CommentIdAllocator
from tests.support.github.models import FakeIssue
from tests.support.github.state import (
    _FakeEventHistory,
    _FakeIssueHistory,
    _FakePullHistory,
    _FakePullState,
)


class _IssueViews(
    issue_service._IssueHistoryView,
    issue_service._EventHistoryView,
):
    """Combine issue-facing history views."""


class _IssueServices(
    issue_service._IssueService,
    issue_service._WorkflowStateService,
    issue_service._IssueCommentService,
):
    """Combine issue operations behind one inheritance branch."""


class _IssueClient(_IssueViews, _IssueServices):
    """Compose the complete issue-side fake surface."""


class _PullViews(
    pull_views._PullHistoryView,
    pull_views._PullStateView,
):
    """Combine pull-request state and history views."""


class _PullServices(
    pull_service._PullCreationService,
    pull_service._PullStatusService,
    pull_service._PullFeedbackService,
):
    """Combine pull-request operations behind one inheritance branch."""


class _PullClient(_PullViews, _PullServices):
    """Compose the complete pull-request-side fake surface."""


class FakeGitHubClient(_IssueClient, _PullClient, _CommentIdAllocator):
    """In-memory stand-in for orchestrator.github.client.GitHubClient."""

    def __init__(
        self,
        issues: Iterable[FakeIssue] = (),
        *,
        repo_slug: str = "chippingway/orchestrator",
        stale_label_cache: bool = False,
        bot_login: str = "orchestrator",
    ) -> None:
        self._repo_slug = repo_slug
        self._bot_login = bot_login
        self._stale_label_cache = stale_label_cache
        self._pollable_calls = 0
        self._issues = {issue.number: issue for issue in issues}
        self._pinned = {}
        # The highest comment id this client has minted, on any thread. A
        # plain counter rather than an iterator because the thread's own
        # comments move it too: ids ascend across a whole thread on GitHub,
        # so a seeded reply above this mark pushes the next minted id past it.
        self._comment_id = _FIRST_COMMENT_ID
        self._pr_id = count(start=1)
        self._next_issue_number = count(
            start=max(self._issues, default=0) + 100,
        )
        self._issue_history = _FakeIssueHistory()
        self._event_history = _FakeEventHistory()
        self._pull_history = _FakePullHistory()
        self._pull_state = _FakePullState()

    @property
    def repo_slug(self) -> str:
        """The repository this client stands in for, as `owner/name`."""
        return self._repo_slug

    def is_own_repository(self, full_name: str | None) -> bool:
        """Whether `full_name` names the repository this client is for.

        The same surface the real client publishes, and readers deciding
        whether a pull request's head is one of THIS repository's ask it here
        -- so a fork's pull request, which carries the same ref names over the
        same commits, is told apart by the one fact that differs. Matched
        case-insensitively for the reason the real one is: owner and repository
        names are case-insensitive on GitHub, so the same repository can be
        spelled two ways across a configuration and an answer.
        """
        if not full_name:
            return False
        return full_name.casefold() == self._repo_slug.casefold()
