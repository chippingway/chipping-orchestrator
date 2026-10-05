# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Composition point for the orchestrator polling loop.

`main` is what the `chipping-orchestrator` console script and the
`python -m orchestrator` launch form both call. It reads the options, refuses a
launch whose author allowlist names nobody, settles logging, creates the state
one run carries, and hands that state to each owner under
`orchestrator/runtime/` in turn; the order below is the startup contract and
lives nowhere else.

The options owner is the only one this module imports with itself. Every other
owner resolves and validates the configuration as it is imported, so each is
named inside the function that composes it, once the command line has been
read: `--help`, and a command line the parser refuses, answer on a host with
no configuration or a malformed one, while a launch that goes on to run meets
that validation before anything it composes.

The signal handler is installed before the first GitHub call, so a stop that
arrives during a slow connect is honoured rather than swallowed, and the
scheduler is published on the state as soon as it exists so the same handler
can close the submit path mid-tick. The exit code is whichever answer came
first: a restart the loop asked for, or the signal that stopped the run.

There are two runs a launch can be, and they differ in the first step rather
than the last: a polling run connects clients that bootstrap each repository's
labels, and the maintenance-only run connects clients that write no workflow
state and never reaches a tick. Everything after that is shared -- the same
state, the same handler, the same scheduler, and the same guaranteed drain --
because a run that reclaims artifacts is stopped by a signal exactly as a
polling one is.

Both also claim this host, and that claim is the outermost thing either run
takes: a polling run announces its presence for its whole life, and a
maintenance-only run takes the host exclusively or does nothing at all. It is
outermost because it is what makes everything inside it mean something -- the
scheduler's caps, its claims, and the barrier over them are one process's, and
the artifacts are the host's. Whichever claim a run took travels on the state
beside the scheduler, because the pass deep inside the loop is what has to
turn a presence into exclusive ownership before it may act.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from orchestrator.runtime import options as _options

if TYPE_CHECKING:
    from orchestrator.runtime.state import RuntimeState


def main(argv: list[str] | None = None) -> int:
    """Run the launch mode the options name and return its exit code."""
    launch_options = _options.parse_options(argv)
    from orchestrator.runtime import logs, shutdown, startup, state as _runtime_state

    startup.require_issue_authors()
    logs.configure_logging(launch_options.log_level)
    state = _runtime_state.RuntimeState()
    shutdown.install_signal_handlers(state)
    if launch_options.cleanup_terminal_artifacts:
        return _maintenance_run(state)
    return _polling_run(state, launch_options)


def _polling_run(
    state: RuntimeState,
    launch_options: _options.PollingOptions,
) -> int:
    """Drive the polling loop and answer with the code it ended on.

    The host claim wraps the connect as well as the loop, because a tick can
    start on the pass right after it: a maintenance process may not be part way
    through this host's checkouts while this run is building the clients that
    are about to be handed them.
    """
    from orchestrator.runtime import exclusion, loop, startup

    with exclusion.polling_presence() as host_claim:
        state.host_claim = host_claim
        clients = startup.connect_clients()
        scheduler = startup.create_scheduler()
        state.active_scheduler = scheduler
        with loop.scheduler_drained(state, scheduler):
            restart_exit_code = loop.drive_polling(
                state,
                launch_options,
                clients,
                scheduler,
            )
    if restart_exit_code is not None:
        return restart_exit_code
    return state.signal_exit_code()


def _maintenance_run(state: RuntimeState) -> int:
    """Run one artifact maintenance pass, and poll nothing.

    The scheduler is built for a run that submits nothing to it, because the
    pass is entitled to the same barrier it runs under inside the polling
    process: one code path decides when artifacts may be touched, and a
    one-shot launch that skipped it would be the one caller allowed to act on a
    host it never proved quiet. On this run the hold is granted immediately --
    nothing was ever admitted -- and the executor behind it costs no thread
    until something is submitted, which here never happens.

    A signal is honoured the same way it is in a polling run: the handler stops
    the run, the pass leaves whatever it had not reached where it was, and the
    drain the wrapper guarantees sets the event the watchdog waits on.

    None of it acts on a host another orchestrator process is live on. The
    scheduler this run builds is its own, so its barrier would grant the quiet
    of an empty process and its claim guard would report nothing running
    however busy the other process is -- so the host decides, and a refusal
    exits as successfully as a pass that found nothing to reclaim, because
    deferring is what this mode was asked to do in that case.

    The clients are connected BEFORE the host is claimed, and that order is the
    point: connecting is the one step here whose duration nothing bounds -- a
    GitHub client that lands in a rate-limit backoff sleeps for as long as the
    reset takes -- and every second of it inside the claim is a second some
    other process waits for this host with its own admission closed. Connecting
    reads no artifact and writes nothing anywhere, so it is safe outside; what
    it costs a deferred run is a client it never asks anything.

    The claim goes on the state rather than being spent here, since the pass
    is where the ownership has to be established: this mode already holds the
    host, a polling run's pass has to take it, and the pass is written against
    whichever of the two it was handed.
    """
    from orchestrator.runtime import artifacts, exclusion, loop, startup

    clients = startup.connect_read_only_clients()
    with exclusion.artifact_exclusivity() as host_claim:
        if not host_claim.taken:
            return state.signal_exit_code()
        state.host_claim = host_claim
        scheduler = startup.create_scheduler()
        state.active_scheduler = scheduler
        with loop.scheduler_drained(state, scheduler):
            artifacts.run_maintenance_pass(state, clients, scheduler)
    return state.signal_exit_code()
