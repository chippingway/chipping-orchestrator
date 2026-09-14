# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read linked pull-request state and retain unreadable or deferred terminal evidence.

A failed read never proves closure. Closed-issue recovery defers a merged
publication to the merge path so the terminal cannot report rejection for
work that already landed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState

log = logging.getLogger("orchestrator.workflow")


# The pinned field every terminal here reads the linked pull request by.
_PR_NUMBER = "pr_number"

# What a pull request a human already landed reads as.
_MERGED = "merged"

# The two attributes a pull request's tip is reached through. Named because
# every arc here reads one of them off a lazily fetched object, and a literal
# repeated at each site is one a rename would leave behind at some of them.
_HEAD_ATTR = "head"
_HEAD_SHA_ATTR = "sha"


@dataclass(frozen=True)
class _LinkedPullRequest:
    """The pull request an issue records, fetched once and read once.

    One object rather than a fetch per question, because the two terminal
    states a pull request can be in are two readings of ONE fact. Asked with a
    fetch each, a merge landing between them answers `open` to the first and
    `merged` to the second -- which a closed-without-merge arc is right to
    ignore -- and the stage behind both carries on over a pull request that is
    finished, spawning a reviewer or measuring a candidate onto work that has
    landed.

    Three shapes, and each is a different answer for a caller. `pr` set is a
    reading any terminal may act on. `unreadable` is a request that did not
    come back, which says nothing about either state. Neither set is an issue
    that records no pull request at all.

    The HEAD travels with the state for the same reason the two states do. A
    caller that has to tell what a pull request IS before deciding what to do
    about it -- the `implementing` stage, whose recorded number can still be
    the `discussion` plan -- classifies on the head and finalizes on the
    state, and taking those from two fetches is two moments: a head that moved
    between them classifies one snapshot and ends another.
    """

    pr: Any = None
    state: str = ""
    head: str | None = None
    unreadable: bool = False

    @property
    def was_read(self) -> bool:
        """Whether there is a state here a terminal may decide on."""
        return self.pr is not None


def _linked_pull_request(
    gh: GitHubClient, issue: Issue, state: PinnedState, checking: str,
) -> _LinkedPullRequest:
    """Read the pull request this issue records, once, guarded.

    The state is read INSIDE the guard with the lookup, because a fetched pull
    request is lazy: `get_pr` asks GitHub nothing and the request that can fail
    is the attribute access behind it.

    `checking` is what the log says the reading was for, since what a failure
    costs differs by the caller that took it.
    """
    pr_number = state.get(_PR_NUMBER)
    if pr_number is None:
        return _LinkedPullRequest()
    try:
        return _pull_request_facts(gh, int(pr_number))
    except Exception:
        log.exception(
            "issue=#%s could not fetch PR #%s while %s; leaving alone",
            issue.number, pr_number, checking,
        )
    return _LinkedPullRequest(unreadable=True)


def _pull_request_facts(gh: GitHubClient, number: int) -> _LinkedPullRequest:
    """The lookup and the lazy reads behind it, as one reading."""
    pull_request = gh.get_pr(number)
    return _LinkedPullRequest(
        pr=pull_request,
        state=gh.pr_state(pull_request),
        head=getattr(
            getattr(pull_request, _HEAD_ATTR, None), _HEAD_SHA_ATTR, None,
        ),
    )


@dataclass(frozen=True)
class _ClosedIssuePR:
    number: int | None
    pr: Any = None
    defer: bool = False


def _closed_issue_pr(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> _ClosedIssuePR:
    raw_number = state.get(_PR_NUMBER)
    if raw_number is None:
        return _ClosedIssuePR(number=None)
    number = int(raw_number)
    try:
        pr = gh.get_pr(number)
    except Exception:
        log.exception(
            "issue=#%s could not fetch PR #%s while finalizing a "
            "closed issue; deferring (next tick retries the "
            "merged-PR path)", issue.number, raw_number,
        )
        return _ClosedIssuePR(number=number, defer=True)
    return _ClosedIssuePR(
        number=number,
        pr=pr,
        defer=gh.pr_state(pr) == "merged",
    )
