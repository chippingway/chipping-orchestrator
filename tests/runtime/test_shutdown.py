# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Signal handling, the watchdog behind it, and the forced exit it ends at."""

from __future__ import annotations

import os
import signal
import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents import processes as _agent_processes
from orchestrator.runtime import shutdown
from orchestrator.runtime.state import RuntimeState
from tests.runtime import polling_signal_probes as _signal_probes, polling_test_support as _support

_TERMINATE_ATTR = "terminate_all_running"
_FORCE_EXIT_ATTR = "force_exit"
_GRACE_ATTR = "SHUTDOWN_GRACE_SECONDS"
_SCHEDULER_FAILURE = "scheduler already closed"


class ShutdownRequestTest(unittest.TestCase):
    """The first signal stops the run, closes the submit path synchronously,
    and arms the bounded shutdown. `running=False` alone would only stop at
    the next tick boundary, so the submit close is what keeps a tick still
    iterating its issue list from queueing more work.
    """

    def test_first_signal_stops_and_closes_submits(self) -> None:
        state = RuntimeState()
        scheduler = MagicMock()
        state.active_scheduler = scheduler

        with _signal_probes.isolated_shutdown() as armed:
            shutdown.request_shutdown(state, signal.SIGTERM, None)

            armed.assert_called_once_with(state, signal.SIGTERM)

        self.assertEqual(state.received_signal, signal.SIGTERM)
        self.assertFalse(state.running)
        scheduler.shutdown.assert_called_once_with(wait=False)

    def test_repeat_signal_is_left_to_the_kernel(self) -> None:
        # The first signal re-arms SIG_DFL, so a second Ctrl+C kills
        # immediately; a repeat that still reached this handler must not
        # re-close the scheduler or arm a second watchdog.
        state = RuntimeState(received_signal=signal.SIGINT, running=False)
        state.active_scheduler = MagicMock()

        with _signal_probes.isolated_shutdown() as armed:
            shutdown.request_shutdown(state, signal.SIGTERM, None)

            armed.assert_not_called()

        self.assertEqual(state.received_signal, signal.SIGINT)
        state.active_scheduler.shutdown.assert_not_called()

    def test_failing_close_still_arms_the_watchdog(self) -> None:
        # The stop is what the operator asked for; a scheduler that refuses
        # the early close must not cost them the bounded exit behind it.
        state = RuntimeState()
        state.active_scheduler = MagicMock()
        state.active_scheduler.shutdown.side_effect = RuntimeError(
            _SCHEDULER_FAILURE,
        )

        with _signal_probes.isolated_shutdown() as armed:
            shutdown.request_shutdown(state, signal.SIGINT, None)

            armed.assert_called_once_with(state, signal.SIGINT)

        self.assertFalse(state.running)


class SignalHandlerInstallationTest(unittest.TestCase):
    """Both stop signals route into the run's own state."""

    def test_one_bound_handler_answers_both_signals(self) -> None:
        state = RuntimeState()
        with patch.object(signal, "signal") as registered:
            shutdown.install_signal_handlers(state)

            registrations = registered.call_args_list

        registered_signals = [
            registration.args[0] for registration in registrations
        ]
        handlers = {
            registration.args[1] for registration in registrations
        }
        self.assertEqual(
            registered_signals,
            [signal.SIGTERM, signal.SIGINT],
        )
        self.assertEqual(len(handlers), 1)

        # The handler carries the state it was installed for, which is what
        # the signal delivery has no way to pass in.
        with _signal_probes.isolated_shutdown():
            handlers.pop()(signal.SIGTERM, None)
        self.assertEqual(state.received_signal, signal.SIGTERM)


class ShutdownWatchdogTest(unittest.TestCase):
    """A signal-initiated stop must exit within `SHUTDOWN_GRACE_SECONDS`
    regardless of what an in-flight worker is blocked on. The cooperative
    drain only advances at tick boundaries and then waits on
    `scheduler.shutdown`, so without a bound a tick wedged in a GitHub retry
    loop -- or a worker parked in a 30-minute agent subprocess -- held the
    process past systemd's `TimeoutStopSec` and earned a SIGKILL.
    """

    def test_watchdog_force_exits_when_drain_overruns(self) -> None:
        forced: list[int] = []
        with (
            patch.object(
                shutdown,
                _FORCE_EXIT_ATTR,
                side_effect=forced.append,
            ),
            patch.object(
                config,
                _GRACE_ATTR,
                _support.SHORT_SHUTDOWN_GRACE_SECONDS,
            ),
        ):
            shutdown.run_shutdown_watchdog(RuntimeState(), signal.SIGTERM)

        self.assertEqual(forced, [signal.SIGTERM])

    def test_clean_return_after_drain_completes(self) -> None:
        # Drain already finished: the watchdog must return without ever
        # touching the process even though grace has not elapsed.
        drained = RuntimeState()
        drained.shutdown_complete.set()
        forced: list[int] = []
        with (
            patch.object(
                shutdown,
                _FORCE_EXIT_ATTR,
                side_effect=forced.append,
            ),
            patch.object(
                config,
                _GRACE_ATTR,
                _support.WORKER_WAIT_SECONDS,
            ),
        ):
            shutdown.run_shutdown_watchdog(drained, signal.SIGTERM)

        self.assertEqual(forced, [])

    def test_force_exit_terminates_then_hard_exits(self) -> None:
        with (
            patch.object(_agent_processes, _TERMINATE_ATTR) as terminated,
            patch.object(
                os,
                "_exit",
                side_effect=RuntimeError("exit"),
            ) as hard_exit,
        ):
            with self.assertRaises(RuntimeError):
                shutdown.force_exit(signal.SIGTERM)

            # The sweep is bounded by the reserved terminate grace -- NOT the
            # default 5s -- so the watchdog path stays within budget.
            terminated.assert_called_once_with(
                grace=shutdown.shutdown_terminate_grace(),
            )
            hard_exit.assert_called_once_with(
                _support.SIGNAL_EXIT_BASE + signal.SIGTERM,
            )


if __name__ == "__main__":
    unittest.main()
