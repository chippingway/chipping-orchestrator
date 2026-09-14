# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Signal handling, watchdog timing, and forced-exit cleanup.

The cooperative half only advances at tick boundaries, so every stop is also
armed with a daemon watchdog: if the drain overruns, in-flight process groups
are terminated and the process hard-exits, which keeps signal-to-exit inside
`SHUTDOWN_GRACE_SECONDS` no matter what a worker is blocked on. The sweep the
watchdog ends with takes time of its own, so it is reserved out of that budget
rather than added on top of it.

The handler is bound to the run's state, and the first signal re-arms the
kernel default, so a second Ctrl+C kills immediately instead of queueing
behind the drain.
"""
from __future__ import annotations

import contextlib
import functools
import logging
import os
import signal
import threading
from typing import Self

from orchestrator.agents import processes as _agent_processes
from orchestrator.config import settings as config
from orchestrator.runtime.state import SIGNAL_EXIT_BASE, RuntimeState

log = logging.getLogger("orchestrator")

# The ceiling on what the sweep reserves out of the shutdown budget. Half the
# grace is its share while the budget is small; past this cap the reserve would
# only starve the cooperative drain that usually makes the sweep unnecessary.
_TERMINATE_SWEEP_RESERVE_CAP_SECONDS = 5.0


class ForcedExit:
    """Ensure the watchdog exits even when process-group cleanup raises."""

    def __init__(self, exit_code: int) -> None:
        self._exit_code = exit_code

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *error_details: object) -> bool:
        os._exit(self._exit_code)
        return False


def install_signal_handlers(state: RuntimeState) -> None:
    """Route SIGTERM and SIGINT into this run's bounded shutdown."""
    signal_handler = functools.partial(request_shutdown, state)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


def request_shutdown(state: RuntimeState, signum: int, _frame: object) -> None:
    """Close submission on the first signal and arm bounded shutdown."""
    if state.received_signal is not None:
        return
    state.received_signal = signum
    log.info(
        "signal %s received; will stop after this tick",
        signum,
    )
    state.running = False
    scheduler = state.active_scheduler
    if scheduler is not None:
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            log.exception(
                "signal handler scheduler.shutdown(wait=False) failed",
            )
    arm_shutdown_watchdog(state, signum)
    with contextlib.suppress(OSError, ValueError):
        signal.signal(signum, signal.SIG_DFL)


def arm_shutdown_watchdog(state: RuntimeState, signum: int) -> None:
    """Start the daemon watchdog that force-exits an overlong drain."""
    threading.Thread(
        target=run_shutdown_watchdog,
        args=(state, signum),
        name="shutdown-watchdog",
        daemon=True,
    ).start()


def shutdown_terminate_grace() -> float:
    """Return the shutdown budget reserved for process-group termination."""
    return min(
        _TERMINATE_SWEEP_RESERVE_CAP_SECONDS,
        config.SHUTDOWN_GRACE_SECONDS / 2,
    )


def run_shutdown_watchdog(state: RuntimeState, signum: int) -> None:
    """Wait for cooperative drain, then invoke the forced-exit path."""
    drain_budget = max(
        0,
        config.SHUTDOWN_GRACE_SECONDS - shutdown_terminate_grace(),
    )
    if state.shutdown_complete.wait(timeout=drain_budget):
        return
    force_exit(signum)


def force_exit(signum: int) -> None:
    """Terminate live child groups and hard-exit with the signal code."""
    log.warning(
        "shutdown grace (%ss) expired; terminating agents and forcing exit",
        config.SHUTDOWN_GRACE_SECONDS,
    )
    with ForcedExit(SIGNAL_EXIT_BASE + signum):
        _agent_processes.terminate_all_running(
            grace=shutdown_terminate_grace(),
        )
