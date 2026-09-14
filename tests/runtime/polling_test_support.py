# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared fakes for the polling runtime and the composition point above it.

The recorders stand in for the two collaborators a polling pass calls out to --
the `GitHubClient` constructor `startup.connect_clients` names, and the
`workflow.engine.tick.tick` each repository's turn ends at -- so a test can drive a run and
then assert on what it dispatched. A pass fans out across worker threads, so
every recorder guards its own bookkeeping with a lock.
"""

from __future__ import annotations

import threading
from pathlib import Path
from unittest import mock

from orchestrator.config import RepoSpec

ALPHA_REPO = "alpha/one"
BETA_REPO = "beta/two"
GAMMA_REPO = "gamma/three"
REPO = "owner/repo"
TICK_ATTR = "tick"
ONCE_ARGS = ("--once",)
SIGNAL_EXIT_BASE = 128
WORKER_WAIT_SECONDS = 5.0
FAST_WAIT_SECONDS = 2.0
SHORT_SHUTDOWN_GRACE_SECONDS = 0.05
SHUTDOWN_GRACE_SECONDS = 30
UNUSED_ISSUE_NUMBER = 999

# A target root every spec here shares: nothing in these tests reaches the
# filesystem through it, so one path keeps the specs comparable.
_SPEC_TARGET_ROOT = Path("/tmp")

_SPEC_BASE_BRANCH = "main"


class ClientFactory:
    """`GitHubClient` side_effect for a composed run: builds one slug-tagged
    MagicMock per `RepoSpec` and records each by slug in `by_slug`, so a test
    can assert on the client the run paired with a given repo.
    """

    def __init__(self) -> None:
        self.by_slug: dict[str, mock.MagicMock] = {}

    def __call__(self, *, repo_spec):
        client = mock.MagicMock()
        client.slug = repo_spec.slug
        self.by_slug[repo_spec.slug] = client
        return client


class TickRecorder:
    """`workflow.engine.tick.tick` side_effect that thread-safely records every tick's
    `(spec.slug, gh.slug)` pairing, the scheduler it was handed, and the
    worker-thread id, then runs an optional `on_tick(gh, spec)` hook for
    per-test side effects (raise, barrier, shutdown).
    """

    def __init__(self, on_tick=None) -> None:
        self.calls: list[tuple[str, str]] = []
        self.schedulers: list[object] = []
        self.threads: list[int] = []
        self._on_tick = on_tick
        self._lock = threading.Lock()

    def __call__(self, gh, spec, *, scheduler=None):
        with self._lock:
            self.calls.append((spec.slug, gh.slug))
            self.schedulers.append(scheduler)
            self.threads.append(threading.get_ident())
        if self._on_tick is not None:
            self._on_tick(gh, spec)

    @property
    def slugs(self) -> list[str]:
        with self._lock:
            return [slug for slug, _ in self.calls]


def repo_specs(slugs) -> list[RepoSpec]:
    """Build the specs `config.default_repo_specs` would resolve for `slugs`."""
    return [
        RepoSpec(
            slug=slug,
            target_root=_SPEC_TARGET_ROOT,
            base_branch=_SPEC_BASE_BRANCH,
        )
        for slug in slugs
    ]


def build_clients(slugs):
    """Pair each spec with the client `connect_clients` would have built.

    The pass-level tests never call `ensure_workflow_labels`, so the mock
    surface is intentionally minimal.
    """
    clients = []
    for spec in repo_specs(slugs):
        github_client = mock.MagicMock()
        github_client.slug = spec.slug
        clients.append((spec, github_client))
    return clients


def raise_on_slug(spec, target_slug: str, message: str) -> None:
    """Tick hook: raise `RuntimeError(message)` when `spec` is `target_slug`,
    simulating one repo's tick failing while the others keep advancing.
    """
    if spec.slug == target_slug:
        raise RuntimeError(message)
