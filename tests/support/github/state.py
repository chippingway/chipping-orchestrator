# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Typed storage owned by the in-memory GitHub client."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from tests.support.github.models import FakeComment, FakeIssue
from tests.support.github.pull_request_models import FakePR

_LabelHistory = list[tuple[int, str | None]]
_CommentHistory = list[tuple[int, str]]


@dataclass
class _FakeIssueHistory:
    _posted_comments: _CommentHistory = field(default_factory=list)
    _label_history: _LabelHistory = field(default_factory=list)
    _created_child_issues: list[FakeIssue] = field(default_factory=list)
    _write_state_calls: int = 0


@dataclass
class _FakePullHistory:
    _posted_pr_comments: _CommentHistory = field(default_factory=list)
    _opened_prs: list[FakePR] = field(default_factory=list)
    _edited_pr_bodies: _CommentHistory = field(default_factory=list)
    _merge_calls: list[tuple[int, str, str]] = field(default_factory=list)
    _deleted_remote_branches: list[str] = field(default_factory=list)
    # Every thread scan a supersession made for itself. A caller that already
    # holds the answer hands it over instead, so this stays empty on the paths
    # that may not put a request between their proof and their write.
    _marker_scans: list[int] = field(default_factory=list)


@dataclass
class _FakeReportFailures:
    """Pull requests whose report and artifact requests GitHub leaves unanswered.

    Three ways, because each leaves GitHub holding something different. A read
    that failed says nothing about the thread; a refused post landed nothing;
    a lost response landed the comment and still raised, which is the accepted
    write a retry has to find rather than post again.

    One set for both evidence surfaces, since there is one conversation behind
    them: a thread nobody can read is unreadable for a verification artifact
    exactly as it is for a developer report.
    """

    unreadable: set[int] = field(default_factory=set)
    refused: set[int] = field(default_factory=set)
    lost: set[int] = field(default_factory=set)


@dataclass
class _FakePullState:
    # The pull requests whose developer-report requests go unanswered, which
    # the real client reports as unconfirmed rather than as absent.
    _report_failures: _FakeReportFailures = field(default_factory=_FakeReportFailures)
    _existing_open_pr: dict[str, FakePR] = field(default_factory=dict)
    _pulls: dict[int, FakePR] = field(default_factory=dict)
    _merge_returns_ok: bool = True
    _delete_remote_branch_returns_ok: bool = True
    # PR numbers whose supersession GitHub refuses, which the real client
    # reports as False rather than raising -- the caller retries the whole
    # notice-and-close, which is idempotent on the second pass.
    _unsupersedable_prs: set[int] = field(default_factory=set)
    # PR numbers whose commit list GitHub refuses to serve, which the real
    # client reports as an unreadable lookup rather than as "does not carry
    # the commit".
    _unreadable_pr_commits: set[int] = field(default_factory=set)
    # Branches whose pull requests GitHub will not enumerate at all, which is
    # the same answer one level up: the candidate that would have matched is
    # one the walk never reaches.
    _unreadable_pr_lookups: set[str] = field(default_factory=set)


@dataclass
class _FakeEventHistory:
    _recorded_events: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class _IssueSeed:
    label: str | None = None
    comments: Iterable[FakeComment] = ()
    title: str = "test issue"
    body: str = "test body"
    author: str = "geserdugarov"
    closed: bool = False
