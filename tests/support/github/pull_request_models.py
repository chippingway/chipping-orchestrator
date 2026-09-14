# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""In-memory pull-request, head-ref, and review records used by workflow tests."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime

from tests.support.github.models import _STATE_OPEN, FakeComment, FakeLabel, FakeUser

# The head every fake pull request stands on unless a case moves it. Named
# rather than repeated, because it is also the head a stage fixture's round
# STARTS on: in production the branch is in sync with its pull request when a
# fix or docs round opens -- the reviewer just read that head -- so a fixture
# spelling the two apart would model a race rather than a tick.
DEFAULT_PR_HEAD_SHA = "deadbeef" * 5


@dataclass
class FakePRRepo:
    """The repository a pull request's head branch lives in.

    Empty until a client holds the pull request, which is what fills it: on
    GitHub a same-repo branch's head repo IS the repository the pull request
    is in, and a fixture cannot know which client it is about to be added to.
    A case naming one is writing the shape that makes this worth reading at
    all -- a FORK, which carries this repository's ref names over its commits,
    so nothing about a branch or a head tells the two apart.
    """

    full_name: str = ""


@dataclass
class FakePRRef:
    sha: str = DEFAULT_PR_HEAD_SHA
    ref: str = ""
    repo: FakePRRepo = field(default_factory=FakePRRepo)


@dataclass
class FakePRReview:
    """Stand-in for a PullRequestReview object."""

    id: int
    body: str
    state: str = "COMMENTED"
    user: FakeUser = field(default_factory=lambda: FakeUser("alice"))
    submitted_at: datetime | None = None
    commit_id: str = ""


@dataclass
class FakePR:
    number: int
    head_branch: str = ""
    base_branch: str = "main"
    title: str = ""
    body: str = ""
    merged: bool = False
    state: str = _STATE_OPEN
    mergeable: bool | None = True
    head: FakePRRef = field(default_factory=FakePRRef)
    approved: bool = False
    check_state: str = "none"
    user: FakeUser = field(default_factory=lambda: FakeUser("orchestrator"))
    labels: list[FakeLabel] = field(default_factory=list)
    issue_comments: list[FakeComment] = field(default_factory=list)
    review_comments: list[FakeComment] = field(default_factory=list)
    reviews: list[FakePRReview] = field(default_factory=list)
    # The commits the PR is made of, beyond whatever its head is now. A human
    # pushing to the branch moves the head while what was published stays in
    # the pull request, which is the whole reason the real lookup asks.
    commit_shas: tuple[str, ...] = ()
    approval_head_sha: str | None = None
    changes_requested: bool = False
    changes_requested_head_sha: str | None = None

    def __post_init__(self) -> None:
        """Say which branch the head is the tip OF, as GitHub always does.

        `head_branch` and `head.ref` are one fact on a real pull request, and
        readers that ask where a recorded number would be pushed read the
        second. A double letting a fixture set only the first would answer
        that question with "no branch at all", which no real pull request
        does -- so the ref follows the branch unless a case named one, which
        is how a pull request open somewhere else is written.
        """
        if self.head_branch and not self.head.ref:
            self.head = replace(self.head, ref=self.head_branch)
