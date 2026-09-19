# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""In-memory issue, user, label, and comment records used by workflow tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from tests.support.github.comment_ids import next_thread_comment_id
from tests.support.github.model_helpers import _copy_issue_comments

# The account backing the token, and so the author GitHub records on every
# comment posted through it. Named once because the pinned-state read
# authenticates a record against exactly this login: a thread whose own writes
# were attributed to anybody else would hand back records the real read
# refuses.
DEFAULT_BOT_LOGIN = "orchestrator"

_STATE_CLOSED = "closed"
_STATE_OPEN = "open"

_UNANSWERED_LOGIN = "GitHub did not answer the author's login read"


@dataclass
class FakeUser:
    login: str = "human"
    type: str = "User"


class UnreadableUser:
    """An author whose login is a request GitHub would not answer."""

    @property
    def login(self) -> str:
        """Raise the way a lazy member does on a completion that failed."""
        raise RuntimeError(_UNANSWERED_LOGIN)


@dataclass
class FakeComment:
    id: int
    body: str
    user: FakeUser = field(default_factory=FakeUser)
    created_at: datetime | None = None

    def edit(self, body: str) -> None:
        """Rewrite this comment in place, the way PyGithub's edit does.

        The id and the author survive it, which is the whole reason a pinned
        record is edited rather than reposted: a replacement would leave the
        record it supersedes on the issue beside it.
        """
        self.body = body


@dataclass
class FakeLabel:
    name: str


@dataclass
class FakeIssue:
    number: int
    title: str = "test issue"
    body: str = "test body"
    labels: list[FakeLabel] = field(default_factory=list)
    comments: list[FakeComment] = field(default_factory=list)
    closed: bool = False
    user: FakeUser = field(default_factory=lambda: FakeUser("geserdugarov"))
    # Who GitHub attributes a comment posted THROUGH this issue to, as opposed
    # to `user`, who opened it. The two are rarely the same account and the
    # pinned-state read turns on the difference.
    commenter: FakeUser = field(
        default_factory=lambda: FakeUser(DEFAULT_BOT_LOGIN),
    )

    get_comments = _copy_issue_comments

    def create_comment(self, body: str) -> FakeComment:
        """Post one comment onto this thread and hand the posted one back.

        What PyGithub returns is where the caller reads the new id off, so the
        comment is on the thread before it is returned: a write that minted an
        id without landing the comment would leave the next read recreating
        the record it believes it just wrote.
        """
        posted = FakeComment(
            id=next_thread_comment_id(self),
            body=body,
            user=self.commenter,
        )
        self.comments.append(posted)
        return posted

    @property
    def state(self) -> str:
        """Mirror the state exposed by PyGithub issues."""
        return _STATE_CLOSED if self.closed else _STATE_OPEN

    def edit(self, *, state: str | None = None) -> None:
        if state == _STATE_CLOSED:
            self.closed = True
