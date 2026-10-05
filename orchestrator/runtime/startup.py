# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one polling run is built from before its first tick.

The author allowlist it may not start without, one authenticated client per
configured repository, and the single scheduler every tick hands work to. Each
of them reads the configuration inside its own call, so a run reflects the
environment it was started in rather than the one this module was imported in.
The options it was started with are read by `options` before this module is
imported at all, since importing it resolves the configuration.

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

import logging
import sys

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.scheduler.service import IssueScheduler

log = logging.getLogger("orchestrator")

RepoClients = list[tuple[_config_models.RepoSpec, GitHubClient]]

_ISSUE_THREAD_PREFIX = "orch-issue"

_MISSING_ISSUE_AUTHORS = (
    "ALLOWED_ISSUE_AUTHORS must contain at least one GitHub login. "
    "Configure it before starting the orchestrator, for example: "
    "ALLOWED_ISSUE_AUTHORS=alice,bob"
)


def require_issue_authors() -> None:
    """Stop the launch unless `ALLOWED_ISSUE_AUTHORS` names somebody.

    An allowlist that names nobody -- unset, or left empty once blanks,
    commas, and leading `@` are stripped -- trusts every author: anyone on a
    public repository could file work an agent is paid to do and steer it
    through comments. So no launch mode starts without one, and the stop comes
    before anything connects, claims the host, or builds a scheduler. The
    options are read before this module is even imported, so `--help` still
    answers on a host nobody has configured yet. `sys.exit` with the message is
    the stop an invalid setting makes at import: the text on stderr and exit
    status 1.
    """
    if not config.ALLOWED_ISSUE_AUTHORS:
        sys.exit(_MISSING_ISSUE_AUTHORS)


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
