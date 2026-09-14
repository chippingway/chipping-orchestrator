# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reusable execution boundary for polling-pass tests.

Every pass here runs against a real `IssueScheduler` -- the caps and the
in-flight bookkeeping are half of what a pass is asserted on -- with the engine
behind `workflow.engine.tick.tick` and the analytics prune standing in for their owners.
The prune is intercepted on every path, not only where a test asserts on it,
so a pass never rewrites the operator's sink.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from importlib import import_module
from unittest import mock

from orchestrator.runtime import ticks
from orchestrator.runtime.state import RuntimeState
from orchestrator.scheduler.service import IssueScheduler
from orchestrator.workflow.engine import tick as _engine_tick
from tests.runtime import polling_test_support as _support
from tests.workflow.git_owners import seam_patch

_RETENTION_OWNER = "orchestrator.observability.analytics.retention"
_PRUNE_ATTR = "prune_with_retention_logging"
_REFRESH_BASE = "_refresh_base_and_worktrees"
_DISPATCH_CAP = 4


def patched_prune():
    """Intercept the prune on the owner the pass names inside its own call."""
    return mock.patch.object(import_module(_RETENTION_OWNER), _PRUNE_ATTR)


@dataclass(frozen=True)
class DispatchContext:
    state: RuntimeState
    scheduler: IssueScheduler
    clients: list

    def run(self, tick_effect) -> None:
        with (
            mock.patch.object(
                _engine_tick,
                _support.TICK_ATTR,
                side_effect=tick_effect,
            ),
            patched_prune(),
        ):
            ticks.run_tick(self.state, self.clients, self.scheduler)

    def run_and_capture_drains(self, tick_effect=None):
        """Run one pass and hand back its completion drain and its prune."""
        with (
            mock.patch.object(
                _engine_tick,
                _support.TICK_ATTR,
                side_effect=tick_effect,
            ),
            patched_prune() as prune,
            mock.patch.object(self.scheduler, "reap") as reap,
        ):
            ticks.run_tick(self.state, self.clients, self.scheduler)
            return reap, prune

    def run_real_and_capture_reap(self):
        """Run one pass through the real engine over empty issue lists."""
        for _repo_spec, github_client in self.clients:
            github_client.list_pollable_issues.return_value = iter([])
        with (
            seam_patch(_REFRESH_BASE),
            patched_prune(),
            mock.patch.object(self.scheduler, "reap") as reap,
        ):
            ticks.run_tick(self.state, self.clients, self.scheduler)
            return reap


@contextmanager
def dispatch_context(slugs: list[str], state: RuntimeState | None = None):
    """Pair a live scheduler with one client per slug for a single pass."""
    scheduler = IssueScheduler(
        global_cap=_DISPATCH_CAP,
        per_repo_cap=_DISPATCH_CAP,
    )
    driven_state = RuntimeState() if state is None else state
    # The composition publishes the scheduler on the state before the first
    # tick can hand it work, and a shutdown raised mid-pass closes the submit
    # path through exactly that reference.
    driven_state.active_scheduler = scheduler
    try:
        yield DispatchContext(
            driven_state,
            scheduler,
            _support.build_clients(slugs),
        )
    finally:
        scheduler.shutdown()
