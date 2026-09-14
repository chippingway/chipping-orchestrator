# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pull-request status, branch lookup, and commit-pinned publication proofs.

An unreadable lookup differs from an absent publication. A recovery that
cannot read a candidate must retain that uncertainty instead of creating
another pull request or restoring a branch a human already settled.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from github import GithubException
from github.PullRequest import PullRequest

from orchestrator.github.pinned_state import GitHubStateMixin

log = logging.getLogger("orchestrator.github")


_ISSUE_STATE_OPEN = "open"
_ISSUE_STATE_CLOSED = "closed"
# What a lookup asks for when a PR that is no longer open is still the answer:
# a publication that crashed before recording its number can have been merged
# (and its branch auto-deleted) by the time anything comes looking.
_ISSUE_STATE_ALL = "all"


class _UnreadablePrLookup:
    """What the commit-pinned lookup answers when GitHub could not be asked.

    Neither a pull request nor the absence of one, because what a caller does
    with those two differs and only one of them is safe to do on a guess. A
    recovery told "no pull request carries this commit" pushes the branch back
    into existence and asks for a second pull request -- which, after the
    original was amended and squash-merged and its head branch auto-deleted,
    means recreating a branch GitHub removed on purpose and opening a PR that
    reverts the amendment. Told instead that the question could not be put, it
    holds and asks again on the next tick, having changed nothing.
    """

    def __repr__(self) -> str:
        return "PR_LOOKUP_UNREADABLE"


# The one answer `find_pr_for_commit` gives that is not about pull requests at
# all: the commit list of at least one candidate could not be read, so nothing
# here can say whether this commit is already published.
PR_LOOKUP_UNREADABLE = _UnreadablePrLookup()


def pr_has_label(pr: PullRequest, label_name: str) -> bool:
    """Return whether a pull request has a case-insensitive label name."""
    wanted_label = (label_name or "").lower()
    return any(
        ((getattr(label, "name", "") or "").lower() == wanted_label)
        for label in (pr.labels or [])
    )


def _pr_carries_commit(pr: PullRequest, head_sha: str) -> bool | None:
    """Whether `head_sha` is one of the commits this pull request is made of.

    The head is checked first because it is free and answers the ordinary case:
    a publication that opened a PR and died before recording its number left
    that PR sitting on exactly the commit it pushed.

    It is not the whole question, though. A human can push onto that branch, or
    merge the base into it to make it mergeable, in the same window -- and each
    moves the head while the commit this publication put there stays in the
    pull request. Asked of the head alone, the recovery finds nothing and goes
    on to push the older SHA over their work or to open a second pull request
    for a design that already has one. The commit list is what the PR actually
    carries, and it answers the same for an open PR and for one a merge has
    since closed.

    A read that failed is its own answer rather than a no. The commit list is
    the only place a squash-merged, since-amended publication is still visible
    -- its head moved and its branch is gone -- so a transient failure read as
    "this PR does not carry it" is precisely the reading that makes a recovery
    republish over work that already landed.
    """
    if getattr(pr.head, "sha", None) == head_sha:
        return True
    try:
        return any(commit.sha == head_sha for commit in pr.get_commits())
    except GithubException as error:
        log.warning(
            "could not read the commits of PR #%s (HTTP %s): %s",
            pr.number, error.status, error.data,
        )
        return None


def pr_state(pr: PullRequest) -> str:
    """Return ``merged``, ``closed``, or ``open`` for a pull request."""
    if pr.merged:
        return "merged"
    if pr.state == "closed":
        return "closed"
    return _ISSUE_STATE_OPEN


def pr_is_mergeable(pr: PullRequest) -> bool | None:
    """Refresh a lazily-computed mergeable field once when needed."""
    if pr.mergeable is None:
        try:
            pr.update()
        except GithubException:
            return None
    return pr.mergeable


class GitHubPullRequestReads(GitHubStateMixin):
    """Repository pull-request enumeration and proofs that a commit is already published."""

    def find_open_pr(
        self,
        *,
        branch: str,
        base: str | None = None,
    ) -> PullRequest | None:
        """Return an open PR for the repository-owned head branch.

        `base` narrows the search to pull requests targeting one branch, which
        is what a caller about to open or reuse a pull request for its own
        cycle wants: a thread aimed somewhere else is not the one it would
        push onto.

        Omitting it widens the search to every base, which is what a caller
        asking whether ANYBODY is still standing on this branch has to do. A
        pull request a human retargeted onto a release line, or onto another
        issue's branch, is still open on this head -- and a lookup pinned to
        the configured base would report the branch as free.
        """
        return next(iter(self._branch_pulls(
            branch, base, state=_ISSUE_STATE_OPEN,
        )), None)

    def find_pr_for_commit(
        self,
        *,
        branch: str,
        head_sha: str,
        base: str | None = None,
    ) -> PullRequest | _UnreadablePrLookup | None:
        """Return the PR for this head branch that carries `head_sha`, any state.

        The lookup a crash window needs and `find_open_pr` cannot serve. A tick
        that opened a pull request and died before persisting its number leaves
        nothing pinned pointing at it, and the next tick re-derives the same
        commit -- but by then a human may have merged that PR, which closes it
        and (with the repository's auto-delete on) takes its head branch with
        it. Searched by open state alone, the recovery finds nothing, pushes
        the branch back into existence, and asks GitHub to open a second pull
        request for a commit that is already in the base.

        The commit is what makes the answer safe to act on. A branch name is
        reused across a whole issue lifetime and can carry several pull
        requests over it, so state is widened only because the commit narrows
        it back: what comes back is the pull request this exact publication
        landed on, or nothing.

        CARRIES the commit, not "is currently on it". The window this exists
        for is the one between opening a pull request and recording its number,
        and a human pushing to that branch -- or merging the base into it --
        moves the head inside that window while the published commit stays in
        the pull request. Matched on the head alone, the recovery would miss
        its own PR and either push the older commit over their work or ask for
        a second pull request for a design that already has one.

        `PR_LOOKUP_UNREADABLE` when a candidate's commit list could not be
        read, since "no pull request carries this" and "nobody could say" are
        different answers to the caller: the first one publishes. A candidate
        that DOES carry it still wins -- a definite answer needs no other
        pull request to have been readable -- so the unreadable one only
        decides the case where nothing else matched.

        `base` narrows the search the way it does for the open-PR lookup, and
        is omitted by a caller asking whether GitHub holds this commit at all.
        A pull request retargeted onto another base carries the commit exactly
        as well as one aimed at the configured base, so a caller measuring
        whether work is published -- rather than which thread it would push
        onto -- must not filter it out.

        The enumeration itself is the same question one level up, and it fails
        the same way: `get_pulls` is a request, and the pages it is walked
        through are a request each, so a candidate that would have matched can
        be one this call never reaches. Nothing distinguishes that from a
        branch with no pull requests on it except that nobody asked, so it is
        the same answer -- and it has to be, because the caller's `None` is
        what pushes. A page that raises halfway also discards whatever the
        pages before it said: a match found there is returned as it is
        reached, so what a failure loses is only the question, never an answer.
        """
        try:
            return self._scan_prs_for_commit(branch, base, head_sha)
        except GithubException as error:
            log.warning(
                "could not list the pull requests on %s (HTTP %s): %s",
                branch, error.status, error.data,
            )
            return PR_LOOKUP_UNREADABLE

    def iter_open_prs(self) -> Iterable[PullRequest]:
        """Yield every open pull request regardless of head branch."""
        yield from self.repo.get_pulls(state=_ISSUE_STATE_OPEN)

    def get_pr(self, pr_number: int) -> PullRequest:
        """Return one pull request by repository number."""
        return self.repo.get_pull(pr_number)

    def _scan_prs_for_commit(
        self, branch: str, base: str | None, head_sha: str,
    ):
        """Walk this branch's pull requests for one carrying `head_sha`."""
        unreadable = False
        for pull_request in self._branch_pulls(
            branch, base, state=_ISSUE_STATE_ALL,
        ):
            carries = _pr_carries_commit(pull_request, head_sha)
            if carries:
                return pull_request
            unreadable = unreadable or carries is None
        return PR_LOOKUP_UNREADABLE if unreadable else None

    def _branch_pulls(
        self, branch: str, base: str | None, *, state: str,
    ) -> Iterable[PullRequest]:
        """The pull requests on one repository-owned head branch.

        The `base` filter is left off the query entirely when the caller named
        none, rather than passed as an empty value: PyGithub omits an argument
        it was never given, and a base spelled as "" would be a base no pull
        request targets.
        """
        owner_login = self.repo.owner.login
        query = {"state": state, "head": f"{owner_login}:{branch}"}
        if base is not None:
            query["base"] = base
        return self.repo.get_pulls(**query)
