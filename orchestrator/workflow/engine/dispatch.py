# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Drive a sequential poll or submit its partition through the issue scheduler.

Poll-time closure evidence determines which processing scope to enter.
Refetched issues preserve observed closes, and scheduled work includes
cleanup that a prior pass left owed outside the current poll results.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import (
    CLEANUP_SWEEP_LABELS,
    issue_is_closed,
)
from orchestrator.scheduler.service import IssueScheduler
from orchestrator.workflow.engine import (
    cleanup_observation as _cleanup_observation,
    dispatch_partition as _dispatch_partition,
    dispatch_workers as _dispatch_workers,
    issue_processing as _issue_processing,
    observations,
    poll_models as _poll_models,
    poll_reading as _poll_reading,
    scheduled_dispatch as _scheduled_dispatch,
)

log = logging.getLogger("orchestrator.workflow")

# The narrower pair, and the one question that is about an OPEN issue: the two
# an adjudication actually RUNS under are the two where a close landing after
# the poll changes which handler this tick calls, so the sequential path pays a
# refetch for them. The recovery labels beside them are only ever asked about
# while closed -- an open `ready` issue is not an ending in progress -- so
# nothing there earns that request.
_CLEANUP_SWEEP_LABELS = frozenset(CLEANUP_SWEEP_LABELS)


def _process_polled_issue(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue,
) -> None:
    """Dispatch one issue this thread polled and still holds.

    The sequential path's own entry, and what it adds over `_process_issue` is
    the classification the other two paths get on their way to a worker: an
    issue on a cleanup-swept label is refetched before anything routes it, and
    a CLOSED reading at poll time additionally BINDS it to the sweep.

    The refetch is the load-bearing half, and it is taken on both readings of
    the close rather than on one. The object in hand is the enumeration's,
    and the two labels this applies to are the two where the close decides
    which handler runs: an owner closed after the poll would otherwise reach
    the stage its label names on a stale open reading -- spawning the
    decomposer, or walking a dependency graph and activating children, on an
    issue a human just ended -- and an owner reopened after the poll would
    have a cleanup pass settle a ledger the live cycle is writing again, since
    the sweep's own close re-read would be re-reading the same stale object.

    The binding is the other half, and it is one-way for the reason the
    workers' is: a closed classification may not become an agent-spawning
    stage handler on the strength of a reopen this tick raced, while an issue
    that was open when it was polled has been classified as ordinary work all
    along and the freshly-read close is what sends it to the sweep.

    Refetched on the caller's own client rather than through
    `_refetch_and_process`: nothing here crosses a thread, so what that mints
    a per-worker client for does not apply, while the read it takes does.

    Hard-skipped issues are dropped here as the partition drops them, rather
    than inside `_process_issue`, so the classification this path takes is the
    same one the other two take.

    Which labels that applies to is `_cleanup_routed`'s question, and it is
    not the same one the partition asks: a closed issue is routed by any of
    the four cleanup labels, while only the two an adjudication runs under
    earn the refetch an OPEN issue costs.

    A latched close overrides the label as it does in the partition, and for
    the same reason: the reading it carries is one the reopen it survived took
    off the remote, so nothing this path could read would find it. It
    overrides the hard-skip filter with it -- an operator's park defers the
    external half of the ending, which is what the sweep does with a parked
    issue anyway, and never the mark. And the cleanup it routes to is wrapped
    in the same observation hold the worker paths use, because a pass that
    raises here marked nothing either.
    """
    issue_number = int(issue.number)
    latched = observations.close_observed(spec.slug, issue_number)
    skip, label = _poll_reading._classify_pollable_issue(gh, spec, issue)
    if skip and not latched:
        return
    closed = issue_is_closed(issue)
    if not latched and not _cleanup_routed(label, closed=closed):
        _dispatch_workers._polled_ordinary(gh, spec, issue, closed=closed)
        return
    if not latched and not closed:
        _dispatch_workers._polled_open_owner(gh, spec, issue_number)
        return
    # The refetch is INSIDE the hold, because it is the first thing a cleanup
    # spends and the likeliest thing to fail: a read that raised marked
    # nothing, and the reading this pass was taking would otherwise be gone.
    with _cleanup_observation._cleanup_observation(gh, spec, issue_number):
        _issue_processing._process_issue(
            gh, spec, gh.get_issue(issue_number),
            reading=_poll_models._PollReading(cleanup_only=True, closed=True),
        )


def _cleanup_routed(label: str | None, *, closed: bool) -> bool:
    """Whether this tick's own path has to treat the issue as a cleanup.

    The two an adjudication RUNS under answer yes whatever the issue reads
    as, because the close is exactly what this path has no hand-off to take
    for it: an owner closed after the poll would otherwise reach the stage
    its label names on a stale open reading. The two an interrupted ending
    can be LEFT on answer yes only while closed -- an open `ready` issue is a
    developer's to pick up rather than an ending in progress, and refetching
    every one of them per tick would spend a request on a question nobody is
    asking.
    """
    if label in _CLEANUP_SWEEP_LABELS:
        return True
    return closed and label in _poll_models._CLEANUP_ROUTE_LABELS


def _dispatch_via_scheduler(
    gh: GitHubClient, spec: _config_models.RepoSpec, scheduler: IssueScheduler,
) -> None:
    """Enumerate pollable issues this tick and hand work to the scheduler.

    Family-aware work (unlabeled pickup + decomposing / blocked /
    umbrella -- the cross-issue writers) is folded into ONE bucket
    submit per repo that drains its issues sequentially on a single
    worker thread; non-family issues are submitted individually. The
    in-tick parallel path in ``tick()`` partitions the same way (one
    drain task for the family bucket, per-issue futures for fanout).

    One bucket per repo is what keeps the family mutex from starving
    itself. The scheduler grants the family slot to the first accepted
    ``family=True`` submit and silently skips every later one this tick,
    so a per-issue family submit would let a stale ``blocked`` child
    take the slot while the parent ``umbrella`` that should relabel it
    never runs -- and the pair would trade the slot back and forth
    forever. Draining every family issue inside the one accepted submit
    means the umbrella always gets its turn within the same tick.

    The bucket task uses ``scheduler.track_active`` around each
    per-issue iteration so ``scheduler.is_active(repo, n)`` reports True
    for the issue currently being processed inside the bucket -- the
    pre-tick base refresh relies on that signal to avoid rebasing a
    worktree under a running agent. Without per-iteration tracking,
    only the bucket's sentinel key would appear in the in-flight set
    and a concurrent refresh would race the agent.

    Each per-issue callable mirrors the in-tick parallel path: mint a
    fresh ``GitHubClient`` via ``gh._for_worker_thread()`` and refetch
    the Issue against that client so the worker drives its own
    Requester chain (PyGithub is not documented thread-safe).

    Completion reaping is the polling loop's job, not this function's.
    ``runtime.ticks.run_tick`` calls ``scheduler.reap()`` exactly once
    after every configured repo's tick returns, which is the cadence surfaced
    to operators and documented in ``docs/observability.md`` ("one reap
    per polling pass"). Reaping here as well would multiply that to N+1
    reaps per pass under ``REPOS``.

    ``spec.parallel_limit`` is forwarded as the scheduler's per-call cap
    override so a per-repo configuration tighter than the scheduler
    default still binds. Label-read failures route the offending issue
    into the family bucket so ``_process_issue``'s own exception
    isolation picks up any sustained failure -- the same recovery the
    in-tick parallel path uses.

    When every family-aware issue this tick runs a no-agent handler
    (label in ``_CAP_EXEMPT_FAMILY_LABELS`` -- ``blocked`` or
    ``umbrella``, both pure label/dep-graph walks), the bucket submit is
    marked ``cap_exempt=True`` so it does not consume a
    ``MAX_PARALLEL_ISSUES_PER_REPO`` or ``MAX_PARALLEL_ISSUES_GLOBAL``
    slot. Such a bucket must always get its turn even when the caps are
    saturated by ordinary implementation work -- otherwise a ``blocked``
    parent polling its own children would be starved of the only
    per-repo slot (under the default ``parallel_limit=1``) and deadlock
    the very children it waits on. A bucket containing ``decomposing``
    (spawns the decomposer agent) or an unlabeled-pickup ``None`` stays
    cap-counted. ``backlog`` / ``paused`` issues are filtered out before
    this split -- a parked issue carries no workflow label, so leaving it in
    would fold it into the bucket and force ``cap_exempt=False``, starving
    fanout behind a hard-skip hold under ``parallel_limit=1``. The family mutex
    still applies, so a follow-up tick that finds another family issue
    still serializes against this bucket.

    Closed fan-out issues are likewise submitted ``cap_exempt=True``: a
    closed issue carrying a sweep label (``in_review`` / ``fixing`` /
    ``resolving_conflict`` / ``question`` / ...) only runs a terminal
    finalization (flip to ``done`` / ``rejected`` + branch cleanup) with no
    agent spawn, so it must not be starved behind active agent work -- a
    merged-PR issue could otherwise sit closed-but-labeled for many ticks
    while a sibling ``validating`` / ``documenting`` agent holds the only
    per-repo slot. A closed ``decomposing`` / ``umbrella`` owner is a fan-out
    submit for exactly this reason: its handler is the cleanup sweep, which
    settles a ledger and spawns nothing, and folding it into the bucket would
    make its turn depend on whatever else landed there.
    """
    per_repo_cap = _scheduled_dispatch._scheduler_per_repo_cap(spec)
    # `_partition_pollable_issues` owns the skip-label filtering, per-issue
    # label-read isolation, and the family/fanout split (including the closed
    # fan-out set). `backlog` / `paused` issues are dropped there so a parked,
    # workflow-label-less issue never folds into the bucket and flips it
    # cap-counted, which would reserve the only per-repo slot and starve
    # fanout under `parallel_limit=1`.
    partition = _dispatch_partition._partition_pollable_issues(
        gh, spec, observations.observed_closes(spec.slug),
    )

    # One `family=True` submit per repo drains every family-aware issue
    # sequentially (see `_drain_scheduler_family_bucket`). The bucket is
    # cap-exempt only when every family issue runs a no-agent handler
    # (`_family_bucket_cap_exempt`); the helper keeps the exempt probe and
    # the submit off the no-family path entirely.
    _scheduled_dispatch._submit_scheduler_family_bucket(gh, spec, scheduler, partition, per_repo_cap)
    _scheduled_dispatch._submit_scheduler_fanout_issues(gh, spec, scheduler, partition, per_repo_cap)
