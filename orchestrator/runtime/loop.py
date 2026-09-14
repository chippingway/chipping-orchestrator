# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How many polling passes a run makes, and the drain it always ends with.

`--once` is a single pass; otherwise the run keeps polling until a signal stops
it or the checkout it runs from moves under it, which exits 0 so the wrapper
relaunches the new code. Either way the body runs inside `scheduler_drained`,
so the workers a pass submitted are waited on even when the pass raised, and
the drain sets the event the shutdown watchdog is waiting on.

The recurring form is also where the host-wide artifact maintenance is fitted
in: at the END of the wait between two passes, behind a due gate this loop
holds for the run. There, because the pass needs the scheduler quiet and a tick
is what makes it busy -- the far end of the interval is the quietest moment
this loop has, where the short handlers the last pass submitted have had the
whole wait to finish. Behind a gate, because the pass is owed once an interval
and this loop comes round once a poll. `--once` is a single tick and nothing
besides -- an operator asking for one pass gets one pass, and the
maintenance-only launch mode is where a host asks for the reclamation on its
own.
"""
from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator

from orchestrator.agents import processes as _agent_processes
from orchestrator.config import settings as config
from orchestrator.runtime import artifacts, self_update, ticks
from orchestrator.runtime.startup import PollingOptions, RepoClients
from orchestrator.runtime.state import RuntimeState
from orchestrator.scheduler.service import IssueScheduler

log = logging.getLogger("orchestrator")

_TICK_WAIT_STEP_SECONDS = 1


def wait_for_next_tick(state: RuntimeState) -> None:
    """Sleep interruptibly until the next configured polling interval."""
    for _ in range(config.POLL_INTERVAL):
        if not state.running:
            return
        time.sleep(_TICK_WAIT_STEP_SECONDS)


def run_polling_loop(
    state: RuntimeState,
    clients: RepoClients,
    scheduler: IssueScheduler,
) -> int | None:
    """Poll until signaled or a self-modifying merge requests restart."""
    own_sha = self_update.own_head_sha()
    log.info("own HEAD=%s", own_sha)
    due_gate = artifacts.DueGate()
    while state.running:
        if own_sha and self_update.self_modifying_merge_happened(own_sha):
            log.info(
                "self-modifying merge detected; exiting for restart",
            )
            return 0
        ticks.run_tick(state, clients, scheduler)
        wait_for_next_tick(state)
        artifacts.run_maintenance_when_due(state, clients, scheduler, due_gate)
    return None


def drive_polling(
    state: RuntimeState,
    options: PollingOptions,
    clients: RepoClients,
    scheduler: IssueScheduler,
) -> int | None:
    """Choose one-shot or recurring polling from parsed options."""
    if options.once:
        ticks.run_tick(state, clients, scheduler)
        return None
    return run_polling_loop(state, clients, scheduler)


def drain_scheduler(state: RuntimeState, scheduler: IssueScheduler) -> None:
    """Stop child groups when signaled, then wait for every worker."""
    if state.received_signal is not None:
        _agent_processes.terminate_all_running()
    scheduler.shutdown(wait=True)
    state.active_scheduler = None
    state.shutdown_complete.set()


@contextlib.contextmanager
def scheduler_drained(
    state: RuntimeState,
    scheduler: IssueScheduler,
) -> Iterator[None]:
    """Guarantee scheduler drain after the wrapped polling body."""
    try:
        yield
    finally:
        drain_scheduler(state, scheduler)
