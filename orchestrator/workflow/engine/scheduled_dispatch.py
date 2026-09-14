# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Submit family and fanout work with capacity rules and publication claims.

Family issues drain in order under active tracking. Fanout claims are
released after execution or refused submission, and observed closes keep
their capacity exemption and durable cleanup retry.
"""
from __future__ import annotations

import contextlib
import functools
import logging
from collections.abc import Callable

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.scheduler.service import IssueScheduler
from orchestrator.workflow.engine import (
    dispatch_closure as _dispatch_closure,
    dispatch_workers as _dispatch_workers,
    poll_models as _poll_models,
    publication_holds as _publication_holds,
)

log = logging.getLogger("orchestrator.workflow")


# Every isolated per-issue failure reports through one line so an operator
# grepping a tick's log sees the same shape whether the issue was dispatched
# sequentially, refetched on a worker, or drained from the family bucket.
_PROCESSING_FAILED_LOG = "repo=%s issue=#%s processing failed"

_FAMILY_BUCKET_ISSUE: int = 0


def _drain_scheduler_family_bucket(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    scheduler: IssueScheduler,
    family_numbers: list[int],
) -> None:
    """Drain this tick's family-aware issues sequentially under one bucket.

    Runs as the single ``family=True`` scheduler submit per repo, so the
    family slot is held for the whole drain: a concurrent tick mid-drain
    cannot squeeze a second family worker past the gate and no two
    family-aware handlers ever run at once. ``scheduler.track_active`` wraps
    each iteration so ``is_active(repo, n)`` reports True for the issue
    currently being processed inside the bucket -- the pre-tick base refresh
    relies on that signal to avoid rebasing a worktree under a running agent;
    without the per-iteration claim only the bucket's sentinel key would
    appear in the in-flight set and a concurrent refresh would race the agent.

    ``track_active`` yields a ``claimed`` bool: when False the issue is
    already in flight on another worker (e.g. a fanout submit accepted on a
    previous tick before this issue was relabeled into the family bucket), so
    the drain skips ``_process_issue`` for that iteration and the next polling
    pass picks it up once the other worker exits -- two workers running the
    same handler concurrently would race the worktree and pinned state.
    Per-issue exception isolation lives inside the loop so one raising family
    handler does not abort the rest of the bucket.

    Each per-issue call mirrors the fanout path: ``_refetch_and_process``
    mints a fresh ``GitHubClient`` via ``gh._for_worker_thread()`` and
    refetches the Issue against it (PyGithub is not documented thread-safe).
    """
    for issue_number in family_numbers:
        try:
            with scheduler.track_active(spec.slug, issue_number) as claimed:
                if not claimed:
                    log.info(
                        "repo=%s issue=#%s already in flight; "
                        "family bucket skipping this iteration",
                        spec.slug, issue_number,
                    )
                    continue
                _dispatch_workers._refetch_and_process(gh, spec, issue_number)
        except Exception:
            log.exception(
                _PROCESSING_FAILED_LOG,
                spec.slug, issue_number,
            )


def _scheduler_per_repo_cap(spec: _config_models.RepoSpec) -> int:
    return max(1, int(getattr(spec, "parallel_limit", 1) or 1))


def _submit_scheduler_family_bucket(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    scheduler: IssueScheduler,
    partition: _poll_models._PollablePartition,
    per_repo_cap: int,
) -> None:
    family_numbers = partition.family_numbers
    if not family_numbers:
        return

    submitted = scheduler.submit(
        spec.slug,
        _FAMILY_BUCKET_ISSUE,
        functools.partial(
            _drain_scheduler_family_bucket, gh, spec, scheduler, family_numbers,
        ),
        family=True,
        cap_exempt=_poll_models._family_bucket_cap_exempt(partition.family_labels),
        per_repo_cap=per_repo_cap,
    )
    if submitted:
        return

    # The scheduler logs the precise skip reason (closed, family_slot_held,
    # cap, ...) inside `submit`; this line gives the dispatch-layer context
    # -- which issues were waiting on this bucket -- so an operator can
    # correlate "umbrella not advancing" with a previous tick's bucket
    # still in flight.
    log.info(
        "repo=%s family bucket (%d issues) not submitted this "
        "tick; next polling pass retries",
        spec.slug, len(family_numbers),
    )


def _submit_scheduler_fanout_issues(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    scheduler: IssueScheduler,
    partition: _poll_models._PollablePartition,
    per_repo_cap: int,
) -> None:
    for issue_number in partition.fanout_numbers:
        cleanup_only = issue_number in partition.cleanup_numbers
        # Held from here rather than from wherever the worker first reads
        # something: the claim exists the moment this submit is admitted, and
        # a poll meeting the issue between that and the handler is refused
        # because a worker has it -- which is exactly when its own reading
        # must not be dropped. Given back by the task, or below if the submit
        # was refused and no task will run.
        _publication_holds.claim_publication(spec.slug, issue_number)
        submitted = scheduler.submit(
            spec.slug,
            issue_number,
            _released_after(spec, issue_number, _dispatch_workers._fanout_task(
                gh, spec, issue_number, reading=_poll_models._PollReading(
                    cleanup_only=cleanup_only,
                    closed=issue_number in partition.fanout_closed,
                ),
            )),
            family=False,
            # A closed issue's handler is a cheap terminal finalization with
            # no agent spawn -- exempt it from the per-repo / global caps so
            # a merged-PR or closed-question issue flips to `done` promptly
            # instead of being starved behind active agent work under
            # `parallel_limit=1` (mirrors the `_CAP_EXEMPT_FAMILY_LABELS`
            # exemption for `blocked` / `umbrella`).
            cap_exempt=(issue_number in partition.fanout_closed),
            per_repo_cap=per_repo_cap,
        )
        if submitted:
            continue
        _publication_holds.release_publication(spec.slug, issue_number)
        _dispatch_closure._refused_submit(
            gh, spec, issue_number,
            cleanup_only=cleanup_only,
            closed=issue_number in partition.fanout_closed,
        )


def _released_after(
    spec: _config_models.RepoSpec, issue_number: int, task: Callable[[], None],
) -> Callable[[], None]:
    """The submitted task with the claim's own hold given back behind it.

    The hold starts at the submit and has to outlive the queue, so the worker
    is what ends it -- and it ends whichever way the task goes, since a pass
    that raised is one that stopped holding the issue just as surely as one
    that returned.
    """
    return functools.partial(_releases_the_claim, spec.slug, issue_number, task)


def _releases_the_claim(
    repo_slug: str, issue_number: int, task: Callable[[], None],
) -> None:
    """Run one submitted task, and give the claim's hold back after it.

    Registered before the task runs rather than called after it, so a pass
    that raises gives the hold back too: one that stopped holding the issue
    did so whichever way it ended.
    """
    with contextlib.ExitStack() as given_back:
        given_back.callback(
            _publication_holds.release_publication, repo_slug, issue_number,
        )
        task()
