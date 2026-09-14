# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""In-memory issue, user, label, and comment records used by workflow tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from tests.support.github.model_helpers import _copy_issue_comments

_STATE_CLOSED = "closed"
_STATE_OPEN = "open"


@dataclass
class FakeUser:
    login: str = "human"
    type: str = "User"


@dataclass
class FakeComment:
    id: int
    body: str
    user: FakeUser = field(default_factory=FakeUser)
    created_at: datetime | None = None


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

    get_comments = _copy_issue_comments

    @property
    def state(self) -> str:
        """Mirror the state exposed by PyGithub issues."""
        return _STATE_CLOSED if self.closed else _STATE_OPEN

    def edit(self, *, state: str | None = None) -> None:
        if state == _STATE_CLOSED:
            self.closed = True
