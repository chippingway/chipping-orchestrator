# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One polling pass over the configured repositories.

A pass is where the run's own stop flag is honoured: a repository whose turn
comes after a signal is skipped rather than started, and a repository whose
tick raises is logged and left behind so the others still advance. The
completion drain and the analytics prune run once at the end of the pass,
never once per repository -- both are process-wide.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

from orchestrator import workflow
from orchestrator.config import RepoSpec
from orchestrator.github.client import GitHubClient
from orchestrator.runtime.startup import RepoClients
from orchestrator.runtime.state import RuntimeState
from orchestrator.scheduler.service import IssueScheduler

log = logging.getLogger("orchestrator")

_REPO_THREAD_PREFIX = "orch-repo"


def tick_one_repo(
    state: RuntimeState,
    spec: RepoSpec,
    github_client: GitHubClient,
    scheduler: IssueScheduler,
) -> None:
    """Drive one repository tick while isolating shutdown and failures."""
    if not state.running:
        log.info(
            "repo=%s shutdown requested before tick start; skipping",
            spec.slug,
        )
        return
    log.info("tick: repo=%s", spec.slug)
    try:
        workflow.tick(
            github_client,
            spec,
            scheduler=scheduler,
        )
    except Exception:
        log.exception(
            "tick failed for repo=%s; continuing",
            spec.slug,
        )


def fan_out_repo_ticks(
    state: RuntimeState,
    clients: RepoClients,
    scheduler: IssueScheduler,
) -> None:
    """Run configured repository ticks concurrently."""
    with ThreadPoolExecutor(
        max_workers=len(clients),
        thread_name_prefix=_REPO_THREAD_PREFIX,
    ) as executor:
        future_repos = {
            executor.submit(tick_one_repo, state, spec, client, scheduler): spec.slug
            for spec, client in clients
        }
        for future in as_completed(future_repos):
            try:
                future.result()
            except Exception:
                log.exception(
                    "repo=%s tick worker raised unexpectedly",
                    future_repos[future],
                )


def run_tick(
    state: RuntimeState,
    clients: RepoClients,
    scheduler: IssueScheduler,
) -> None:
    """Drive one polling pass and its completion/retention drains."""
    if not clients:
        return
    if len(clients) == 1:
        spec, github_client = clients[0]
        tick_one_repo(state, spec, github_client, scheduler)
    else:
        fan_out_repo_ticks(state, clients, scheduler)
    scheduler.reap()
    # The one collaborator named inside the call rather than at module scope,
    # so a tick's own import never pays for the prune graph. The prune reads
    # both sink knobs off the analytics settings holder inside its own call, so
    # nothing about the timing of this import decides which files it rewrites.
    from orchestrator.observability.analytics import retention

    retention.prune_with_retention_logging()
