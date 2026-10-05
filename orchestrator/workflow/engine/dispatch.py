# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Drive a sequential poll or submit its partition through the issue scheduler.

Poll-time closure evidence determines which processing scope to enter, and the
sequential entry takes the issue's writer claim before any of them and reads
the issue again under it. Refetched issues preserve observed closes, and
scheduled work includes cleanup that a prior pass left owed outside the
current poll results.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import issue_is_closed
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


def _process_polled_issue(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, *, read_at: int,
) -> None:
    """Dispatch one issue this thread polled and still holds.

    `read_at` is the moment the loop read before it listed anything
    (`claim_notes.moment`), so no later than the read `issue` is.

    The sequential path's own entry: it takes the classification the other two
    paths take on their way to a worker, dropping hard-skipped issues as the
    partition does, then runs under the issue's writer claim -- a contender
    writes nothing and keeps only a closed reading in its latch, tied to a
    cycle only where a read proves it. The closed reading is taken off the
    enumeration's object before the classification, as the partition's is.

    Under the claim the issue is read again before anything routes it, since
    another poller may have advanced, closed, or reopened it since the poll;
    the poll's reading carries over only where it is a close, one-way as the
    workers' does. A latched close, or a closed reading on a cleanup label,
    goes to the sweep inside the observation hold the worker paths use --
    past the hard-skip filter too, since an operator's park defers the
    ending's external half and never the mark.
    """
    latched = observations.close_observed(spec.slug, int(issue.number))
    closed = issue_is_closed(issue)
    skip, label = _poll_reading._classify_pollable_issue(gh, spec, issue)
    if skip and not (latched or closed):
        return
    _claimed_poll(
        gh, spec, issue,
        _poll_models._PollReading(closed=closed, read_at=read_at),
        cleanup=latched or (closed and label in _poll_models._CLEANUP_ROUTE_LABELS),
    )


def _claimed_poll(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    reading: _poll_models._PollReading,
    *,
    cleanup: bool,
) -> None:
    """Take one polled issue's writer claim, and pass it down the route it earned.

    The reading carries the moment the loop read before listing, not one read
    here: a hold another thread of this process found while this one
    classified the issue would otherwise read as one the close was read after.
    """
    issue_number = int(issue.number)
    with _issue_processing._writer_claim(
        gh, spec, issue_number, closed=issue if reading.closed else None,
    ) as held:
        if not held:
            return
        if cleanup:
            _claimed_cleanup(gh, spec, issue_number, reading)
            return
        _dispatch_workers._polled_refetch(gh, spec, issue_number, reading=reading)


def _claimed_cleanup(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    reading: _poll_models._PollReading,
) -> None:
    """Sweep one polled issue whose writer claim this thread holds.

    A closed reading is latched first, fresh and with its moment, as the
    enumeration latches its own on the worker paths; the refetch is inside
    the hold, being the likeliest thing to fail, and a read that raised
    marked nothing.
    """
    if reading.closed:
        observations.observe_close(spec.slug, issue_number, reading.read_at, fresh=True)
    with _cleanup_observation._cleanup_observation(gh, spec, issue_number):
        _issue_processing._process_issue(
            gh, spec, gh.get_issue(issue_number),
            reading=_poll_models._PollReading(cleanup_only=True, closed=True),
        )


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
