# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one walk over a repository's issues that a tick is served from.

Two queries under one method: every open issue, and -- on the
``CLOSED_ISSUE_SWEEP_EVERY_N_TICKS`` cadence -- the closed ones a sweep still
owes a pass, one query per swept label, asked for by its canonical name. What
holds them together is the shared number set they all filter through: the
queries overlap, and a stage handler dispatched twice against one issue in a
tick would act on a record it had just written itself.

Which labels each half asks about is read from ``issues`` rather than restated
here. Those sets say which closed issues are still owed something, which is a
statement about issue state that the dispatcher routes on too -- and a router
has no business reading its vocabulary out of a poller. The same read is what
puts this owner directly above ``issues`` in the client's mixin chain: the
link it inherits is the one module it already names.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from github.GithubObject import _ValuedAttribute, is_undefined
from github.Issue import Issue
from github.IssuePullRequest import IssuePullRequest

from orchestrator import config
from orchestrator.github.issues import (
    _ISSUE_STATE_CLOSED,
    _ISSUE_STATE_OPEN,
    CLEANUP_ROUTE_LABELS,
    CLOSED_SWEEP_LABELS,
    issue_query_options,
)
from orchestrator.github.label_moves import GitHubLabelMoveMixin
from orchestrator.workflow.state import WorkflowLabel

# One walk over both, because both are the same request against the same
# cadence and the same label cache, and the dispatcher tells the two apart by
# what it finds on the issue rather than by which query produced it.
SWEEP_LABELS: tuple[WorkflowLabel, ...] = (
    CLOSED_SWEEP_LABELS + CLEANUP_ROUTE_LABELS
)

# What a row carrying no PyGithub ``_pull_request`` slot at all reads as.
_NO_RECORDED_PULL_REQUEST = object()


def _is_pull_request(issue: Issue) -> bool:
    """Whether a listed row is a pull request, answered without completing it.

    The issue list endpoint puts a ``pull_request`` object on a pull request's
    row and leaves the key off a real issue's, and PyGithub keeps a key the
    payload never carried as ``NotSet``. Its public ``pull_request`` property
    reads ``NotSet`` as a field still to fetch, so asking it would spend one
    detail GET per open issue on a question the page already answered. On a
    list row the private slot is exact: ``NotSet`` is an issue, and a valued
    slot holds the pull-request object or ``None``.

    Anything else -- a row with no such slot, as a plain test double has, or a
    slot in a shape this PyGithub does not produce -- is asked through the
    public property, which is right on every object and only costlier on a
    PyGithub one.
    """
    recorded = getattr(issue, "_pull_request", _NO_RECORDED_PULL_REQUEST)
    if is_undefined(recorded):
        return False
    if isinstance(recorded, _ValuedAttribute):
        listed = recorded.value
        if listed is None or isinstance(listed, IssuePullRequest):
            return listed is not None
    return issue.pull_request is not None


def iter_new_non_pr_issues(
    issues: Iterable[Issue],
    seen_numbers: set[int],
) -> Iterable[Issue]:
    """Yield unseen non-PR issues while updating the shared number set.

    Every row is classified from what its list page carried, so a walk costs
    the query's pages and nothing per issue.
    """
    for issue in issues:
        if not _is_pull_request(issue) and issue.number not in seen_numbers:
            seen_numbers.add(issue.number)
            yield issue


class GitHubIssuePollingMixin(GitHubLabelMoveMixin):
    """The repository-wide issue walk the concrete GitHub client exposes.

    A link in the chain rather than a collaborator standing beside it, on the
    same terms as every other link: each inherits its neighbour to be composed,
    not to borrow from it. Nothing here calls an issue method -- the seams the
    walk reads are the client's own, the repository and the poll counter and
    the cached label reads -- so an issue operation and a poll can each be
    changed without disturbing the other.
    """

    def list_pollable_issues(
        self,
        since: datetime | None = None,
    ) -> Iterable[Issue]:
        """Yield open issues, plus the closed ones a sweep still owes a pass.

        Two kinds of closed issue, on one cadence: the recoverable ones whose
        terminal arc has not drained, and the cleanup owners whose ledger may
        still hold the remote to a branch or a snapshot ref.
        """
        seen_numbers: set[int] = set()
        self._pollable_calls += 1
        yield from iter_new_non_pr_issues(
            self.repo.get_issues(
                **issue_query_options(
                    issue_state=_ISSUE_STATE_OPEN,
                    since=since,
                ),
            ),
            seen_numbers,
        )
        sweep_cadence = config.CLOSED_ISSUE_SWEEP_EVERY_N_TICKS
        if (
            sweep_cadence > 1
            and (self._pollable_calls - 1) % sweep_cadence != 0
        ):
            return
        yield from self._iter_closed_sweep_issues(since, seen_numbers)

    def _iter_closed_sweep_issues(
        self,
        since: datetime | None,
        seen_numbers: set[int],
    ) -> Iterable[Issue]:
        """Yield the closed issues still carrying a swept workflow label.

        Each label is asked for by its canonical name and by nothing else, so a
        closed issue whose only workflow label is a pre-namespace spelling is
        not reached: that spelling is not a current label, and a sweep exists
        to finish current work. A label whose lookup fails is skipped for this
        pass alone, and the next sweep asks for it again.

        The two cleanup states ride the same walk, the same cadence, and the
        same label cache: an extra pass over them would double the fixed cost
        the cadence exists to amortize while asking the identical question one
        tick apart.
        """
        for sweep_label in SWEEP_LABELS:
            label_object = self._cached_label(str(sweep_label))
            if label_object is None:
                continue
            yield from iter_new_non_pr_issues(
                self.repo.get_issues(
                    **issue_query_options(
                        issue_state=_ISSUE_STATE_CLOSED,
                        since=since,
                        label=label_object,
                    ),
                ),
                seen_numbers,
            )
