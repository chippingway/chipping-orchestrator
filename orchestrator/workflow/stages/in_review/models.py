# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one in_review tick hands between its owners.

`_InReviewContext` is the tick itself. Every route below the handler needs the
same six handles, and the PR among them is the live one fetched once at the
top: re-reading it per route would let the mergeability answer and the head
SHA a ping is keyed on come from two different fetches. `pr_number` rides
along because the handler has already proven it is present -- the park for a
missing one happens before this record exists.

`_DriftResume` carries what the drift disposition cannot re-derive after the
run: the worktree the resume actually ran in (the resolve may have recreated
it), whether an operator paused mid-run, `before_sha`, which is the only
thing that tells a pushed fix from a no-commit acknowledgement, and the
requirements revision the resume was handed, which its report is stamped with.

`_AnsweredIssueSpace` is the three answers the watermark walk asks of every
comment above the mark, bundled because they are one reading of one pinned
state: which posts this orchestrator can prove are its own, how far the issue
thread alone has been delivered, and which ids this very tick quoted. Read
apart, a walk could advance on one and owe on another.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState


@dataclass(frozen=True)
class _InReviewContext:
    """The per-tick `in_review` invocation handles, bundled so the fresh-feedback
    scan, fixing-route, drift, and mergeability sub-handlers thread them as a
    single value instead of five/six positional arguments (mirrors fixing's
    `_FixingContext`). `pr` is the live PR fetched this tick; `pr_number` is the
    pinned PR number `_handle_in_review` already validated as present.
    """
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    pr: Any
    pr_number: Any


@dataclass(frozen=True)
class _AnsweredIssueSpace:
    """What a watermark walk may advance through without owing anybody.

    `ours` is the orchestrator id ledger, `consumed` the issue thread's own
    delivery cursor (`last_action_comment_id`, which says nothing about the
    pull request's conversation), and `delivered` the ids this tick quoted
    into a prompt of its own.
    """
    ours: set
    consumed: int | None
    delivered: set


@dataclass(frozen=True)
class _DriftResume:
    """Outcome of the drift dev-resume: the (possibly recreated) worktree, the
    agent result, whether an operator paused mid-run, the pre-resume HEAD
    used to tell a pushed fix from a no-commit ack, and the hash the drift
    check took of the content the resume was handed.
    """
    worktree: Any
    dev_result: Any
    paused: bool
    before_sha: Any
    requirements_revision: str = ""
