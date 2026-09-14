# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One repo's polling pass: the order it drives, and how its issues execute.

`tick` is the whole per-repo unit of work, and the order of the passes it
drives is the contract. The base refresh goes first because everything after it
reads what that fetch left behind -- a handler would otherwise rebase onto the
base SHA its worktree was created at, and the skill catalog would ls-tree a
stale `<remote_name>/<base_branch>`. It is also the only pass whose failure is
caught here, because a fetch that fails must not cost the tick its issues; the
sweep and the catalog are internally fail-open and cannot raise at all.

The community sweep and the skill-catalog emission are driven from here rather
than from the stage tree because neither has a per-issue home: a PR the
orchestrator never opened carries no pinned state for a handler to consult, and
the catalog is producer-side observability about the repo rather than about any
issue. Both run before the scheduler / in-tick split so they fire exactly once
per tick on either path.

Past that split the tick either hands every issue to the scheduler and returns
without waiting, or runs them itself under `parallel_limit`. The two in-tick
modes are not one loop at two widths, so only one of them is here. `limit == 1`
streams `list_pollable_issues()` directly on this thread, because materializing
it first would lose every already-yielded issue when a pagination error raises
mid-sweep; `limit > 1` is the bounded pool on `parallel.py` beside this one,
which materializes because its executor has to be sized. Both wrap each issue
in its own try/except, so one raising handler never stops the rest.

Every collaborator is named on the owner that defines it, the three passes
above included: `_refresh_base_and_worktrees` on `git/base_sync/refresh.py`,
the sweep on `community.py` beside this one, the catalog emission on
`orchestrator/skills/catalog.py`, and the bounded-pool execution on
`parallel.py`. A mock aimed at one of them lands on that owner; one left
anywhere else would let the real pass run. The line an isolated per-issue
failure reports on comes from `dispatch.py` for the same reason: the isolation
points here and on the parallel owner would otherwise spell it four ways.
"""
from __future__ import annotations

import contextlib
import logging
import threading

from orchestrator.config import models as _config_models
from orchestrator.git.base_sync import refresh as _base_refresh
from orchestrator.github.client import GitHubClient
from orchestrator.scheduler.service import IssueScheduler
from orchestrator.skills import catalog as _catalog
from orchestrator.workflow.engine import (
    community as _community,
    dispatch as _dispatch,
    dispatch_workers as _dispatch_workers,
    observations as _observations,
    parallel as _parallel,
    scheduled_dispatch as _scheduled_dispatch,
)

log = logging.getLogger("orchestrator.workflow")


def _run_sequential_tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    semaphore_cm: contextlib.AbstractContextManager,
) -> None:
    """Process this tick's pollable issues one at a time on the caller thread.

    `parallel_limit == 1` (the legacy default) streams directly over
    `gh.list_pollable_issues()` rather than materializing the list first.
    Materializing would change observable behavior on a partial enumeration
    failure (e.g. a PyGithub pagination error mid-sweep): the sequential loop
    processes everything yielded BEFORE the failure, but a `list(...)` upfront
    would lose every already-yielded issue when the generator raises. Each
    dispatch is wrapped in its own try/except so one raising issue cannot stop
    the rest.

    Handed to `_process_polled_issue` rather than straight to `_process_issue`,
    because the object this loop holds is the enumeration's own reading and one
    route may not be taken on a stale one: the cleanup sweep settles a closed
    owner's ledger, and an owner reopened after this tick listed it has to be
    seen as reopened. The other two paths get that from the refetch their
    worker hand-off already makes; this one has no hand-off, so it takes the
    same classification and the same fresh read itself.
    """
    yielded: set[int] = set()
    for issue in gh.list_pollable_issues():
        yielded.add(int(issue.number))
        try:
            with semaphore_cm:
                _dispatch._process_polled_issue(gh, spec, issue)
        except Exception:
            log.exception(
                _scheduled_dispatch._PROCESSING_FAILED_LOG,
                spec.slug, issue.number,
            )
    _swept_unyielded(gh, spec, yielded, semaphore_cm)


def _swept_unyielded(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    yielded: set[int],
    semaphore_cm: contextlib.AbstractContextManager,
) -> None:
    """Sweep the held close observations this enumeration never reached.

    A held observation is not a reading of this tick's: an earlier poll found
    the issue closed and could hand that to nobody. What the enumeration
    yields is decided by the labels the closed sweep queries, so a human who
    moves the label off one of them -- or closes the issue on a label the
    sweep does not query at all -- makes the owner unreachable, and the
    reading would be lost with it. So it is swept by number instead, on the
    strength of the observation alone, and the pass holds it exactly as every
    other cleanup does.
    """
    for owed in sorted(
        _observations.observed_closes(spec.slug) - yielded,
    ):
        try:
            with semaphore_cm:
                _dispatch_workers._swept_for_cleanup(gh, spec, owed)
        except Exception:
            log.exception(
                _scheduled_dispatch._PROCESSING_FAILED_LOG, spec.slug, owed,
            )


def tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    *,
    global_semaphore: threading.BoundedSemaphore | None = None,
    scheduler: IssueScheduler | None = None,
) -> None:
    """Drive a single tick for one repo.

    `global_semaphore` is the cross-repo bound on concurrent per-issue
    handlers (`MAX_PARALLEL_ISSUES_GLOBAL`). It is acquired around every
    `_process_issue` call so workers from different repo ticks running
    concurrently contend on the same semaphore. None falls back to a
    no-op context manager so direct test invocations of `tick(gh, spec)`
    keep working unchanged. It bounds the in-tick path only:
    `runtime.ticks.run_tick` always supplies the shared scheduler
    instead, so on the production path the cross-repo cap is the
    scheduler's `global_cap`.

    `scheduler`, when supplied, takes over per-issue dispatch entirely.
    The polling pass still refreshes base/worktrees and enumerates
    pollable issues, but instead of running the handlers in-tick (legacy
    in-thread loop or per-tick ThreadPoolExecutor) each accepted
    per-issue callable is submitted to the scheduler and the tick
    returns without waiting for completion. The scheduler owns the
    cross-repo in-flight cap, the per-repo cap (`spec.parallel_limit`
    is threaded in as the per-call override), the "duplicate active
    issue" skip, and the family-aware mutex. `global_semaphore` is
    ignored on this path -- the scheduler's `global_cap` is the
    authoritative cross-repo bound. None preserves the legacy in-tick
    behavior so existing direct invocations are unchanged.
    """
    try:
        # Threading the scheduler in here is what keeps an "active
        # issue" actually inert across the whole tick. The dispatch
        # path skips a duplicate submit at `scheduler.submit`, but the
        # base refresh would otherwise rebase the pre-PR worktree
        # under a still-running agent or relabel/state-mutate a
        # PR-having worktree while its handler is mid-write. The
        # refresh helper consults `scheduler.is_active` per worktree
        # so an in-flight issue's worktree and pinned state are left
        # alone until the worker exits.
        _base_refresh._refresh_base_and_worktrees(gh, spec, scheduler=scheduler)
    except Exception:
        log.exception(
            "repo=%s pre-tick base refresh failed; continuing", spec.slug,
        )
    # Per-tick: label any open PR from an outsider author and ping HITL once.
    # Independent from the per-issue dispatch (PRs not driven by the
    # orchestrator have no pinned state to consult), so failures inside the
    # sweep are swallowed by its owner and cannot stop the tick.
    _community._sweep_community_contribution_prs(gh, spec)
    # Per-tick: snapshot the target repo's skill catalog into analytics.
    # Runs after the base refresh above has fetched
    # `<remote_name>/<base_branch>` so the ls-tree reads the current base
    # ref. Producer-side observability only and internally fail-open, so a
    # missing clone / git error never stops the tick; placed before the
    # scheduler/legacy split so it fires once per tick on both paths.
    _catalog._emit_repo_skill_catalog(spec)
    if scheduler is not None:
        _dispatch._dispatch_via_scheduler(gh, spec, scheduler)
        return
    # `parallel_limit` is the local cap on worker threads this tick spins up.
    # The host-wide `MAX_PARALLEL_ISSUES_GLOBAL` cap is enforced by
    # `global_semaphore` around each `_process_issue` call, not by shrinking
    # the worker pool: with multiple repos ticking in parallel, workers from
    # different repos may queue on the semaphore until a global slot frees up,
    # which is the whole point of a cross-repo cap. None falls back to a no-op
    # context manager so a direct test invocation of `tick(gh, spec)` keeps
    # working unchanged. `limit == 1` (the legacy default) stays sequential
    # and in-thread; `limit > 1` fans out across a bounded pool.
    limit = max(1, int(getattr(spec, "parallel_limit", 1) or 1))
    semaphore_cm = (
        contextlib.nullcontext() if global_semaphore is None else global_semaphore
    )
    if limit == 1:
        _run_sequential_tick(gh, spec, semaphore_cm)
    else:
        _parallel._run_parallel_tick(gh, spec, limit, semaphore_cm)
