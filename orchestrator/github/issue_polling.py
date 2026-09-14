# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one walk over a repository's issues that a tick is served from.

Two queries under one method: every open issue, and -- on the
``CLOSED_ISSUE_SWEEP_EVERY_N_TICKS`` cadence -- the closed ones a sweep still
owes a pass, one query per swept label spelling. What holds them together is
the shared number set they all filter through: the queries overlap, and a
stage handler dispatched twice against one issue in a tick would act on a
record it had just written itself.

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

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.issues import (
    _ISSUE_STATE_CLOSED,
    _ISSUE_STATE_OPEN,
    CLEANUP_ROUTE_LABELS,
    CLOSED_SWEEP_LABELS,
    GitHubIssueMixin,
    issue_query_options,
)
from orchestrator.workflow.state import WorkflowLabel, legacy_label_name


def _sweep_lookups(
    sweep_labels: tuple[WorkflowLabel, ...],
) -> tuple[tuple[str, bool], ...]:
    """Pair every swept label spelling with whether a miss on it is expected.

    The pre-namespace spelling is queried beside the namespaced one because a
    closed issue is the one case no other pass revisits: if the bootstrap could
    not rename the label, nothing else would ever surface that issue again.
    Both queries feed one ``seen_numbers`` set, so an issue a repository
    carries under both spellings is still yielded once.

    A miss on a legacy name is the expected answer on a migrated repository,
    so it is throttled rather than re-asked every sweep -- throttled, not
    remembered, because the label can still come back by hand.
    """
    lookups: list[tuple[str, bool]] = []
    for sweep_label in sweep_labels:
        lookups.append((str(sweep_label), False))
        legacy_name = legacy_label_name(sweep_label)
        if legacy_name is not None:
            lookups.append((legacy_name, True))
    return tuple(lookups)


CLOSED_SWEEP_LOOKUPS = _sweep_lookups(CLOSED_SWEEP_LABELS)

CLEANUP_SWEEP_LOOKUPS = _sweep_lookups(CLEANUP_ROUTE_LABELS)

# One walk over both, because both are the same request against the same
# cadence and the same label cache, and the dispatcher tells the two apart by
# what it finds on the issue rather than by which query produced it.
SWEEP_LOOKUPS = CLOSED_SWEEP_LOOKUPS + CLEANUP_SWEEP_LOOKUPS


def iter_new_non_pr_issues(
    issues: Iterable[Issue],
    seen_numbers: set[int],
) -> Iterable[Issue]:
    """Yield unseen non-PR issues while updating the shared number set."""
    for issue in issues:
        if issue.pull_request is None and issue.number not in seen_numbers:
            seen_numbers.add(issue.number)
            yield issue


class GitHubIssuePollingMixin(GitHubIssueMixin):
    """The repository-wide issue walk the concrete GitHub client exposes.

    A link in the chain rather than a collaborator standing beside it, on the
    same terms as every other link: each inherits its neighbour to be composed,
    not to borrow from it. Nothing here calls an issue method -- the seams the
    walk reads are the client's own, the repository and the poll and sweep
    counters and the cached label reads -- so an issue operation and a poll can
    each be changed without disturbing the other.
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

        Reached only past the cadence gate, so the sweep count it keeps -- and
        the absent-label window denominated in it -- advances once per sweep
        rather than once per poll.

        The two cleanup states ride the same walk, the same cadence, and the
        same label cache: an extra pass over them would double the fixed cost
        the cadence exists to amortize while asking the identical question one
        tick apart.
        """
        self._closed_sweeps += 1
        # Scoped to this pass: the spellings it confirms absent are summarized
        # at the end of it, and a sweep that raises before then takes them with
        # it rather than leaving them for the next one to restate.
        absent_legacy_names: list[str] = []
        for label_name, absence_is_expected in SWEEP_LOOKUPS:
            label_object = self._cached_label(
                label_name,
                throttle_absent=absence_is_expected,
                absent_names=absent_legacy_names,
            )
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
        # After the loop, so every legacy spelling this sweep confirmed absent
        # lands in one repository-qualified line instead of one line each.
        self._report_absent_legacy_labels(absent_legacy_names)
