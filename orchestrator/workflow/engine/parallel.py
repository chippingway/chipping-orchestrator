# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One tick's issues run across a bounded pool: the plan, and the drain.

`tick.py` decides that a repo's pass runs in-tick under a `parallel_limit`
above 1 and hands the whole of that execution here; the per-repo pass ordering
and the sequential mode stay there. What this owner adds over that mode is the
bound, the partition the bound is measured against, and the isolation each of
the two buckets needs.

The two in-tick modes are not one loop at two widths. This one MUST materialize
the enumeration -- the executor needs the submission count up front to bound
`max_workers` -- and so accepts that an enumeration failure costs the whole
tick, which the next one retries; the sequential mode streams for the opposite
reason, that a partial enumeration must not lose what it already yielded.

The family bucket the partition hands over is submitted as exactly ONE task no
matter how many family-aware issues are pending, so it occupies a single worker
slot and leaves the other `limit - 1` free for fanout. Per-family-issue futures
behind a shared lock would instead let a waiting family future hold a second
slot and starve fanout under a small `limit`.

Every collaborator is named on the owner that defines it: the partition, the
fanout task, and the per-worker refetch on `dispatch.py`, and the closes an
earlier poll is still holding on `observations.py`. A mock aimed at one of them
lands on that owner; one left anywhere else would let the real pass run. The
line an isolated per-issue failure reports on comes from `dispatch.py` for the
same reason -- the isolation points here and on `tick.py` beside it would
otherwise spell one message four ways.
"""
from __future__ import annotations

import contextlib
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.engine import (
    dispatch_partition as _dispatch_partition,
    dispatch_workers as _dispatch_workers,
    observations as _observations,
    poll_models as _poll_models,
    scheduled_dispatch as _scheduled_dispatch,
)

log = logging.getLogger("orchestrator.workflow")


def _drain_family_bucket(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    family_numbers: list[int],
    *,
    semaphore_cm: contextlib.AbstractContextManager,
) -> None:
    """Process this tick's family-aware issues sequentially on one thread.

    The whole family bucket is submitted as ONE executor task so its footprint
    stays at exactly one worker slot regardless of how many family-aware issues
    are pending, leaving the other `limit - 1` slots free for fanout. Per-issue
    exception isolation lives INSIDE this loop (one try/except per issue) so
    the bucket keeps draining if any single family handler raises; the function
    itself never raises, so the caller's `fut.result()` only ever surfaces a
    programming-level failure.
    """
    for issue_number in family_numbers:
        try:
            _dispatch_workers._refetch_and_process(
                gh, spec, issue_number, semaphore_cm=semaphore_cm,
            )
        except Exception:
            log.exception(
                _scheduled_dispatch._PROCESSING_FAILED_LOG,
                spec.slug, issue_number,
            )


@dataclass(frozen=True)
class _ParallelTickPlan:
    gh: GitHubClient
    spec: _config_models.RepoSpec
    partition: _poll_models._PollablePartition
    semaphore_cm: contextlib.AbstractContextManager

    @property
    def task_count(self) -> int:
        family_count = 1 if self.partition.family_numbers else 0
        return family_count + len(self.partition.fanout_numbers)

    def submit(self, executor) -> tuple[dict[Any, Any], object]:
        family_sentinel: object = object()
        futures: dict[Any, Any] = {}
        if self.partition.family_numbers:
            futures[
                executor.submit(
                    _drain_family_bucket,
                    self.gh,
                    self.spec,
                    self.partition.family_numbers,
                    semaphore_cm=self.semaphore_cm,
                )
            ] = family_sentinel
        for issue_number in self.partition.fanout_numbers:
            futures[
                executor.submit(
                    # Built by the dispatcher rather than assembled here, so
                    # this path gets what the scheduler's own submit gets: the
                    # route carried rather than re-derived -- this worker
                    # refetches the issue, and a reopen in between must not
                    # turn a cleanup pass into the stage handler its label
                    # names -- and, for a cleanup, the observation held until
                    # the pass has actually run it.
                    _dispatch_workers._fanout_task(
                        self.gh,
                        self.spec,
                        issue_number,
                        reading=_poll_models._PollReading(
                            cleanup_only=(
                                issue_number
                                in self.partition.cleanup_numbers
                            ),
                            closed=(
                                issue_number in self.partition.fanout_closed
                            ),
                        ),
                        semaphore_cm=self.semaphore_cm,
                    ),
                )
            ] = issue_number
        return futures, family_sentinel


def _drain_parallel_futures(
    spec: _config_models.RepoSpec,
    futures: dict[Any, Any],
    family_sentinel: object,
) -> None:
    for future in as_completed(futures):
        tag = futures[future]
        try:
            future.result()
        except Exception:
            if tag is family_sentinel:
                # Per-issue failures are caught by the family drain itself;
                # only a programming-level drain failure reaches this path.
                log.exception(
                    "repo=%s family bucket drain raised (programming "
                    "error -- per-issue exceptions are handled inside "
                    "the drain)", spec.slug,
                )
            else:
                log.exception(
                    _scheduled_dispatch._PROCESSING_FAILED_LOG, spec.slug, tag,
                )


def _run_parallel_tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    limit: int,
    semaphore_cm: contextlib.AbstractContextManager,
) -> None:
    """Fan this tick's pollable issues out across a bounded thread pool.

    Family-aware (cross-issue writer) work is partitioned off from fanout so
    the family bucket drains sequentially inside ONE task while the rest fan
    out; `_partition_pollable_issues` owns the skip-label filtering, per-issue
    label-read isolation, and the family/fanout split. Each `_process_issue`
    is independent (per-issue worktree, PinnedState, GitHub label/comment
    surface) so worker threads serialize only at the PyGithub HTTP layer,
    which is already thread-safe.

    The executor needs the full submission set up front to bound
    `max_workers`, so the generator is materialized in `_partition_pollable_issues`;
    on an enumeration failure the whole tick aborts and the next tick's
    enumeration retries. Folding the whole family bucket into one drain task
    caps its footprint at exactly one executor slot regardless of how many
    family-aware issues there are, leaving the other `limit - 1` slots free
    for fanout -- submitting per-family-issue futures with a shared lock would
    instead let a waiting family future occupy the other worker slot and
    starve fanout under a small `limit`.
    """
    plan = _ParallelTickPlan(
        gh,
        spec,
        _dispatch_partition._partition_pollable_issues(
            gh, spec, _observations.observed_closes(spec.slug),
        ),
        semaphore_cm,
    )
    if plan.task_count == 0:
        return
    slug_token = spec.slug.replace("/", "__")
    # max_workers is capped at `limit` AND at the submitted-task count so a
    # quiet tick (e.g. one fan-out issue) does not spin up idle worker threads.
    with ThreadPoolExecutor(
        max_workers=min(limit, plan.task_count),
        thread_name_prefix=f"orch-{slug_token}",
    ) as executor:
        futures, family_sentinel = plan.submit(executor)
        # `as_completed` so a slow issue does not delay logging the failures
        # of faster ones. Each `fut.result()` is wrapped individually so one
        # raising issue cannot abort the remaining futures' result drain.
        _drain_parallel_futures(spec, futures, family_sentinel)
