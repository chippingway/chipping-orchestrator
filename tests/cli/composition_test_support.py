# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One composed `cli.main` run with only its process-wide seams intercepted.

What is stood in for is what a test process cannot afford to run for real: the
GitHub clients, the workflow engine behind `workflow.engine.tick.tick`, the analytics
prune, the logging configuration, and the signal registration. Everything the
composition itself decides -- the order the owners run in, the state they
share, the live scheduler every tick is handed, and the exit code the run ends
at -- is the real thing, because that is what these tests are about.

The checkout root is redirected for the same reason the analytics sinks are:
a composed run claims this host for its whole life, on a real `flock` under
`WORKTREES_DIR`. Left pointing at the operator's own root, these tests would
create a lock file in it and -- worse than the litter -- a real maintenance
pass holding that host would have every one of them waiting on it, which is
exactly what that claim is built to make a process do.
"""

from __future__ import annotations

from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from orchestrator import cli
from orchestrator.config import settings as config
from orchestrator.runtime import logs, shutdown, startup, state as _runtime_state
from orchestrator.scheduler.service import IssueScheduler
from orchestrator.workflow.engine import tick as _engine_tick
from tests.runtime import (
    polling_scheduler_probes as _probes,
    polling_signal_probes as _signal_probes,
    polling_test_support as _support,
    tick_test_support as _tick_support,
)

_DEFAULT_SPECS_ATTR = "default_repo_specs"
_GITHUB_CLIENT_ATTR = "GitHubClient"
_SCHEDULER_ATTR = "IssueScheduler"
_STATE_ATTR = "RuntimeState"
_CONFIGURE_LOGGING_ATTR = "configure_logging"
_INSTALL_HANDLERS_ATTR = "install_signal_handlers"
_WORKTREES_ATTR = "WORKTREES_DIR"


class StateFactory:
    """`RuntimeState` stand-in that keeps the state a run created."""

    def __init__(self) -> None:
        self.created: list[_runtime_state.RuntimeState] = []

    def __call__(self) -> _runtime_state.RuntimeState:
        state = _runtime_state.RuntimeState()
        self.created.append(state)
        return state


@dataclass
class StartupSeams:
    """The two startup steps a composed run only records: what the process
    logs through, and the handler registration a test process cannot keep.
    """

    configured_logging: object = None
    installed_handlers: object = None


class ComposedRun:
    """The recorders one composed run is asserted on.

    `on_tick` is the per-test hook every recorded tick calls, assigned after
    the run is set up so it can reach the state the run itself created.
    """

    def __init__(self) -> None:
        self.states = StateFactory()
        self.clients = _support.ClientFactory()
        self.schedulers = _probes.SchedulerFactory(IssueScheduler)
        self.recorder = _support.TickRecorder(on_tick=self._run_tick_hook)
        self.seams = StartupSeams()
        self.on_tick = None

    @property
    def state(self) -> _runtime_state.RuntimeState:
        return self.states.created[-1]

    @property
    def scheduler(self) -> IssueScheduler:
        return self.schedulers.built[-1]

    def main(self, argv=_support.ONCE_ARGS) -> int:
        """Drive `cli.main` the way a launch form does."""
        return cli.main(list(argv))

    def _run_tick_hook(self, github_client, spec) -> None:
        if self.on_tick is not None:
            self.on_tick(github_client, spec)


@contextmanager
def _own_worktrees_root():
    """A checkout root of this run's own, so no claim it takes is anybody's.

    A test that wants to contend for that claim takes its own from inside the
    composed run, which is where this redirection is in force.
    """
    with TemporaryDirectory() as root, patch.object(
        config, _WORKTREES_ATTR, Path(root),
    ):
        yield


def _recorded_startup(intercepted: ExitStack, run: ComposedRun) -> None:
    """Record the two collaborators `startup` builds rather than building them.

    One step because they are one idea: a composed run is asserted on the
    clients it paired with each spec and on the single scheduler it shared, and
    neither can be a real one in a test process.
    """
    intercepted.enter_context(patch.object(
        startup, _GITHUB_CLIENT_ATTR, side_effect=run.clients,
    ))
    intercepted.enter_context(patch.object(
        startup, _SCHEDULER_ATTR, run.schedulers,
    ))


@contextmanager
def composed_run(slugs: list[str]):
    """Compose one run over `slugs` and hand back its recorders."""
    run = ComposedRun()
    with ExitStack() as intercepted:
        intercepted.enter_context(_own_worktrees_root())
        intercepted.enter_context(patch.object(
            config, _DEFAULT_SPECS_ATTR, return_value=_support.repo_specs(slugs),
        ))
        _recorded_startup(intercepted, run)
        intercepted.enter_context(patch.object(cli, _STATE_ATTR, run.states))
        intercepted.enter_context(patch.object(
            _engine_tick, _support.TICK_ATTR, side_effect=run.recorder,
        ))
        intercepted.enter_context(_tick_support.patched_prune())
        # The run installs no handler of its own and arms no watchdog: both
        # outlive the test that started them, and what the composition owes
        # here is the call, which is asserted on the interception itself.
        run.seams.installed_handlers = intercepted.enter_context(
            patch.object(shutdown, _INSTALL_HANDLERS_ATTR),
        )
        intercepted.enter_context(_signal_probes.isolated_shutdown())
        run.seams.configured_logging = intercepted.enter_context(
            patch.object(logs, _CONFIGURE_LOGGING_ATTR),
        )
        yield run
