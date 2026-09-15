# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How many polling passes a run makes, and the drain it always ends with."""

from __future__ import annotations

import signal
import time
import unittest
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.agents import processes as _agent_processes
from orchestrator.runtime import artifact_schedule, artifacts, loop, self_update, ticks
from orchestrator.runtime.startup import PollingOptions
from orchestrator.runtime.state import RuntimeState

_RUN_TICK_ATTR = "run_tick"
_WHEN_DUE_ATTR = "run_maintenance_when_due"
_POLLING_LOOP_ATTR = "run_polling_loop"
_HEAD_SHA_ATTR = "own_head_sha"
_MERGE_PROBE_ATTR = "self_modifying_merge_happened"
_WAIT_ATTR = "wait_for_next_tick"
_TERMINATE_ATTR = "terminate_all_running"
_POLL_INTERVAL_ATTR = "POLL_INTERVAL"
_SLEEP_ATTR = "sleep"
_OWN_SHA = "9e7a1c0"
_POLL_INTERVAL = 3
_BODY_FAILURE = "polling body failed"
_TICK_STEP = "tick"
_WAIT_STEP = "wait"
_MAINTENANCE_STEP = "maintenance"


def _options(once: bool) -> PollingOptions:
    return PollingOptions(
        once=once, cleanup_terminal_artifacts=False, log_level="INFO",
    )


class StopAfterPasses:
    """`run_tick` stand-in that stops the run after a bounded pass count.

    Records each pass on `driven` where it was handed one, which is how a test
    that cares about the ORDER of a pass's steps sees where the tick landed
    among them.
    """

    def __init__(
        self,
        state: RuntimeState,
        passes: int,
        driven: list | None = None,
    ) -> None:
        self._state = state
        self._passes = passes
        self._driven = driven
        self.completed = 0

    def __call__(self, *_call) -> None:
        if self._driven is not None:
            self._driven.append(_TICK_STEP)
        self.completed += 1
        self._state.running = self.completed < self._passes


class DrivePollingTest(unittest.TestCase):
    """`--once` is a single pass; anything else is the recurring loop."""

    def test_once_runs_a_single_pass(self) -> None:
        state = RuntimeState()
        with (
            patch.object(ticks, _RUN_TICK_ATTR) as run_tick,
            patch.object(loop, _POLLING_LOOP_ATTR) as polling,
        ):
            exit_code = loop.drive_polling(state, _options(True), [], None)

            self.assertIsNone(exit_code)
            run_tick.assert_called_once_with(state, [], None)
            polling.assert_not_called()

    def test_recurring_run_returns_the_loop_answer(self) -> None:
        state = RuntimeState()
        with patch.object(loop, _POLLING_LOOP_ATTR, return_value=0) as polling:
            exit_code = loop.drive_polling(state, _options(False), [], None)

            self.assertEqual(exit_code, 0)
            polling.assert_called_once_with(state, [], None)


class PollingLoopTest(unittest.TestCase):
    """The loop polls until the run is stopped, and exits 0 the moment the
    checkout it runs from moves under it so the wrapper relaunches the new
    code rather than polling on with stale handlers.
    """

    def test_polls_until_the_run_stops(self) -> None:
        state = RuntimeState()
        passes = StopAfterPasses(state, 2)
        with (
            patch.object(self_update, _HEAD_SHA_ATTR, return_value=None),
            patch.object(ticks, _RUN_TICK_ATTR, side_effect=passes),
            patch.object(loop, _WAIT_ATTR),
        ):
            exit_code = loop.run_polling_loop(state, [], None)

        self.assertIsNone(exit_code)
        self.assertEqual(passes.completed, 2)

    def test_self_modifying_merge_exits_for_restart(self) -> None:
        with (
            patch.object(self_update, _HEAD_SHA_ATTR, return_value=_OWN_SHA),
            patch.object(
                self_update,
                _MERGE_PROBE_ATTR,
                return_value=True,
            ) as probe,
            patch.object(ticks, _RUN_TICK_ATTR) as run_tick,
        ):
            exit_code = loop.run_polling_loop(RuntimeState(), [], None)

            # Exit 0 is what `run.sh` restarts on, and the restart is decided
            # before the tick so the new code runs the next pass.
            self.assertEqual(exit_code, 0)
            probe.assert_called_once_with(_OWN_SHA)
            run_tick.assert_not_called()

    def test_unresolvable_head_keeps_polling(self) -> None:
        # A checkout whose HEAD does not resolve (no `.git`, a detached
        # worktree) has no baseline to compare against, so the restart probe
        # must not run at all rather than compare against nothing.
        state = RuntimeState()
        with (
            patch.object(self_update, _HEAD_SHA_ATTR, return_value=None),
            patch.object(self_update, _MERGE_PROBE_ATTR) as probe,
            patch.object(
                ticks,
                _RUN_TICK_ATTR,
                side_effect=StopAfterPasses(state, 1),
            ),
            patch.object(loop, _WAIT_ATTR),
        ):
            loop.run_polling_loop(state, [], None)

            probe.assert_not_called()


class MaintenanceBetweenPassesTest(unittest.TestCase):
    """The artifact pass is fitted at the end of the wait between two passes,
    behind one gate the run holds for its whole life.

    At the end of the wait rather than beside the tick, because the pass wants
    the scheduler quiet and the tick is what fills it -- the far end of the
    interval is where the short handlers of the last pass have already
    finished. Through the gate rather than directly, because it is owed once an
    interval or once a window and this loop comes round once a poll. A single-tick run asks for
    none of it: an operator who asked for one tick gets one tick, and the
    maintenance-only launch mode is where a host asks for the reclamation on
    its own.
    """

    def test_every_pass_ends_at_the_run_gate(self) -> None:
        state = RuntimeState()
        driven: list[str] = []
        with (
            patch.object(self_update, _HEAD_SHA_ATTR, return_value=None),
            patch.object(
                ticks,
                _RUN_TICK_ATTR,
                side_effect=StopAfterPasses(state, 2, driven),
            ),
            patch.object(
                loop,
                _WAIT_ATTR,
                side_effect=lambda *call: driven.append(_WAIT_STEP),
            ),
            patch.object(
                artifacts,
                _WHEN_DUE_ATTR,
                side_effect=lambda *call: driven.append(_MAINTENANCE_STEP),
            ) as when_due,
        ):
            loop.run_polling_loop(state, [], None)

            self.assertEqual(driven, [
                _TICK_STEP, _WAIT_STEP, _MAINTENANCE_STEP,
                _TICK_STEP, _WAIT_STEP, _MAINTENANCE_STEP,
            ])
            gates = {id(call.args[-1]) for call in when_due.call_args_list}
            self.assertEqual(len(gates), 1)
            self.assertIsInstance(
                when_due.call_args.args[-1], artifact_schedule.DueGate,
            )

    def test_one_tick_asks_for_no_maintenance(self) -> None:
        with (
            patch.object(ticks, _RUN_TICK_ATTR),
            patch.object(artifacts, _WHEN_DUE_ATTR) as when_due,
        ):
            loop.drive_polling(RuntimeState(), _options(True), [], None)

            when_due.assert_not_called()


class WaitForNextTickTest(unittest.TestCase):
    """The wait is one second at a time so a signal is honoured inside the
    interval instead of at the end of it.
    """

    def test_sleeps_once_per_configured_second(self) -> None:
        with (
            patch.object(config, _POLL_INTERVAL_ATTR, _POLL_INTERVAL),
            patch.object(time, _SLEEP_ATTR) as slept,
        ):
            loop.wait_for_next_tick(RuntimeState())

            self.assertEqual(slept.call_count, _POLL_INTERVAL)

    def test_stops_early_once_the_run_stops(self) -> None:
        state = RuntimeState()
        with (
            patch.object(config, _POLL_INTERVAL_ATTR, _POLL_INTERVAL),
            patch.object(
                time,
                _SLEEP_ATTR,
                side_effect=StopAfterPasses(state, 1),
            ) as slept,
        ):
            loop.wait_for_next_tick(state)

            self.assertEqual(slept.call_count, 1)


class SchedulerDrainTest(unittest.TestCase):
    """Every exit drains the scheduler so in-flight workers finish cleanly.

    A signal stop is the one that cannot wait: it terminates in-flight agent
    and verify groups up front, because a worker parked in a long agent run
    would otherwise hold the process past the systemd stop deadline.
    """

    def test_clean_exit_waits_for_the_workers(self) -> None:
        state = RuntimeState()
        scheduler = MagicMock()
        state.active_scheduler = scheduler

        with patch.object(_agent_processes, _TERMINATE_ATTR) as terminated:
            loop.drain_scheduler(state, scheduler)

            terminated.assert_not_called()

        scheduler.shutdown.assert_called_once_with(wait=True)
        self.assertIsNone(state.active_scheduler)
        self.assertTrue(state.shutdown_complete.is_set())

    def test_signal_stop_terminates_groups_first(self) -> None:
        state = RuntimeState(received_signal=signal.SIGTERM)
        scheduler = MagicMock()

        with patch.object(_agent_processes, _TERMINATE_ATTR) as terminated:
            loop.drain_scheduler(state, scheduler)

            terminated.assert_called_once_with()

        scheduler.shutdown.assert_called_once_with(wait=True)

    def test_drain_runs_even_when_the_body_raises(self) -> None:
        state = RuntimeState()
        scheduler = MagicMock()

        with self.assertRaises(RuntimeError), loop.scheduler_drained(state, scheduler):
            raise RuntimeError(_BODY_FAILURE)

        scheduler.shutdown.assert_called_once_with(wait=True)
        self.assertTrue(state.shutdown_complete.is_set())


if __name__ == "__main__":
    unittest.main()
