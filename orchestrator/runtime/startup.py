# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one polling run is built from before its first tick.

The options an operator started it with, one authenticated client per
configured repository, and the single scheduler every tick hands work to. Each
of them reads the configuration inside its own call, so a run reflects the
environment it was started in rather than the one this module was imported in.

`RepoClients` is what both connects hand back and what every pass over the
repositories is typed by: the spec stays paired with the client built for it,
because the pairing is what a tick would otherwise have to reconstruct.

There are two connects because there are two things a run can be started for.
The polling one bootstraps each repository's labels, since a tick is about to
write them; the read-only one writes nothing at all, which is what makes it
usable by a launch mode whose whole contract is that it touches no workflow
state on GitHub.
"""
from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.scheduler.service import IssueScheduler

log = logging.getLogger("orchestrator")

RepoClients = list[tuple[config.RepoSpec, GitHubClient]]

_ISSUE_THREAD_PREFIX = "orch-issue"


@dataclass(frozen=True)
class PollingOptions:
    """Parsed command-line options: which mode a run is, and how loud."""

    once: bool
    cleanup_terminal_artifacts: bool
    log_level: str


def parse_options(argv: list[str] | None) -> PollingOptions:
    """Parse the launch mode and log level a run was started with."""
    parser = argparse.ArgumentParser(
        description="chipping-orchestrator polling loop.",
    )
    # Exclusive rather than ordered: each flag names a whole run that ends on
    # its own, so a command line asking for both is a mistake worth reporting
    # instead of one whose meaning an operator has to look up.
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--once",
        action="store_true",
        help="Run a single tick and exit.",
    )
    modes.add_argument(
        "--cleanup-terminal-artifacts",
        action="store_true",
        help=(
            "Reclaim the worktrees and branches of finished issues, then "
            "exit. Polls no issue and writes no workflow state: no label, no "
            "pinned state, no comment. It does delete the orchestrator-owned "
            "branches it proved reclaimable, in the local clone and on the "
            "remote. Defers entirely while another orchestrator process is "
            "live on this host."
        ),
    )
    parser.add_argument("--log-level", default="INFO")
    parsed_options = parser.parse_args(argv)
    return PollingOptions(
        once=parsed_options.once,
        cleanup_terminal_artifacts=parsed_options.cleanup_terminal_artifacts,
        log_level=parsed_options.log_level,
    )


def connect_clients() -> RepoClients:
    """Connect once per configured repository and ensure its labels."""
    return _connected(ensure_labels=True)


def connect_read_only_clients() -> RepoClients:
    """Connect once per configured repository without writing to any of them.

    The label bootstrap is the one write a connect makes -- it creates or
    renames the workflow labels the tick loop is about to use -- and a run that
    will not tick has no business making it. A maintenance-only launch is asked
    about issue endings and pull requests and nothing else, so the repository
    it is pointed at comes back exactly as it was even where the labels are
    missing entirely.
    """
    return _connected(ensure_labels=False)


def _connected(*, ensure_labels: bool) -> RepoClients:
    """Build one client per configured repository, bootstrapped or not."""
    clients: RepoClients = []
    for repo_spec in config.default_repo_specs():
        github_client = GitHubClient(repo_spec=repo_spec)
        log.info("connected: repo=%s", repo_spec.slug)
        if ensure_labels:
            github_client.ensure_workflow_labels()
        clients.append((repo_spec, github_client))
    return clients


def create_scheduler() -> IssueScheduler:
    """Build the process-wide scheduler shared by every polling tick."""
    return IssueScheduler(
        global_cap=config.MAX_PARALLEL_ISSUES_GLOBAL,
        per_repo_cap=config.MAX_PARALLEL_ISSUES_PER_REPO,
        thread_name_prefix=_ISSUE_THREAD_PREFIX,
    )
