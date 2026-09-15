# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Process registry, the runs spawned into it, and the shutdown sweep."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.agents import processes as _processes
from tests.agents import agent_test_support as _support, agent_test_values as _agent_cases


class RunSubprocessRegistrationTest(unittest.TestCase):
    """`run_subprocess` must register its child for the lifetime of the run
    so the shutdown sweep can reach it, and clear it afterward so the registry
    does not leak completed processes.
    """

    def test_registers_during_run_and_clears_after(self) -> None:
        proc = _support.completed(stdout="{}", returncode=0)
        registration_probe = _support.RegistrationProbe(proc)
        proc.communicate.side_effect = registration_probe
        with patch(_agent_cases._POPEN_TARGET, return_value=proc):
            _processes.run_subprocess([_agent_cases._AGENT_COMMAND], _agent_cases._CWD, {}, 10)

        self.assertTrue(registration_probe.seen, "child not registered during the run")
        with _processes._running_procs_lock:
            self.assertNotIn(proc, _processes._running_procs)


class TerminateAllRunningTest(unittest.TestCase):
    """`terminate_all_running` is the shutdown hook that kills in-flight agent
    process groups so a restart does not hang for up to `AGENT_TIMEOUT`. It
    must SIGTERM every registered group, SIGKILL anything still alive at the
    shared grace deadline, and be a clean no-op when nothing is in flight. The
    SIGTERM is its own and the probe plus SIGKILL are the group owner's, so the
    sweep is observed through the `killpg` both of them read off `os`.
    """

    def test_no_procs_is_noop(self) -> None:
        # Registry empty between tests (every spawn unregisters in a finally),
        # so this exercises the early return with no signals sent.
        with patch(_agent_cases._SHARED_KILLPG_TARGET) as killpg:
            self.assertEqual(_processes.terminate_all_running(), 0)
            killpg.assert_not_called()

    def test_no_sigkill_after_all_groups_exit(self) -> None:
        # Both leaders exit on SIGTERM and the signal-0 group probe reports the
        # group empty, so no SIGKILL is sent -- the clean-shutdown path.
        proc1, proc2 = MagicMock(), MagicMock()
        proc1.pid = 111
        proc2.pid = 222
        proc1.wait.return_value = 0
        proc2.wait.return_value = 0
        with _support.registered_procs(proc1, proc2), patch(
            _agent_cases._SHARED_KILLPG_TARGET,
            side_effect=_support.killpg_group_empty,
        ) as signal_mock:
            terminated_count = _processes.terminate_all_running(grace=0.5)
            sent = {call.args for call in signal_mock.call_args_list}
        self.assertEqual(terminated_count, 2)
        self.assertIn((111, signal.SIGTERM), sent)
        self.assertIn((222, signal.SIGTERM), sent)
        self.assertNotIn((111, signal.SIGKILL), sent)
        self.assertNotIn((222, signal.SIGKILL), sent)

    def test_sigkill_if_child_outlives_leader(self) -> None:
        # Regression: the leader exits on SIGTERM but a descendant in the same
        # group ignored it. `proc.wait()` returns, yet the signal-0 probe shows
        # the group still alive, so the group must be SIGKILLed -- otherwise the
        # grandchild keeps mutating the worktree after the orchestrator exits.
        proc = MagicMock()
        proc.pid = 555
        proc.wait.return_value = 0  # leader exits promptly on SIGTERM
        with _support.registered_procs(proc), patch(
            _agent_cases._SHARED_KILLPG_TARGET,
            side_effect=_support.killpg_group_alive,
        ) as signal_mock:
            _processes.terminate_all_running(grace=_agent_cases._TERMINATION_GRACE_SECONDS)
            sent = [call.args for call in signal_mock.call_args_list]
        self.assertIn((555, signal.SIGTERM), sent)
        self.assertIn((555, 0), sent)  # group liveness probed after leader exit
        self.assertIn((555, signal.SIGKILL), sent)

    def test_sigkills_straggler_past_deadline(self) -> None:
        # A group that never exits on SIGTERM must be SIGKILLed once the
        # shared grace deadline elapses.
        proc = MagicMock()
        proc.pid = 333
        proc.wait.side_effect = subprocess.TimeoutExpired(
            cmd=_agent_cases._AGENT_COMMAND,
            timeout=_agent_cases._TERMINATION_GRACE_SECONDS,
        )
        with _support.registered_procs(proc), patch(_agent_cases._SHARED_KILLPG_TARGET) as killpg:
            _processes.terminate_all_running(grace=_agent_cases._TERMINATION_GRACE_SECONDS)
            calls = [call.args for call in killpg.call_args_list]
        self.assertIn((333, signal.SIGTERM), calls)
        self.assertIn((333, signal.SIGKILL), calls)

    def test_missing_group_is_swallowed(self) -> None:
        # The leader can exit between the snapshot and the killpg; the
        # ProcessLookupError race must not propagate.
        proc = MagicMock()
        proc.pid = 444
        proc.wait.return_value = 0
        with _support.registered_procs(proc), patch(
            _agent_cases._SHARED_KILLPG_TARGET,
            side_effect=ProcessLookupError,
        ):
            self.assertEqual(
                _processes.terminate_all_running(
                    grace=_agent_cases._TERMINATION_GRACE_SECONDS,
                ),
                1,
            )


class InterruptedSubprocessClassificationTest(unittest.TestCase):
    """A run cut short by SIGTERM/SIGKILL -- the shape the orchestrator's
    shutdown sweep (`terminate_all_running`) produces when it kills an
    in-flight agent group -- must surface as `interrupted=True`, distinct from
    a normal completion and from the orchestrator's own `timed_out` path.
    That holds whether the child dies from the signal (negative returncode) or
    traps it and exits with the shell's 128+N, as `claude` does on SIGTERM.
    """

    def test_returncode_classification(self) -> None:
        # The raw returncode is kept as-is on the result either way; only the
        # `interrupted` flag reads the signal forms, and no other non-zero code.
        cases = (
            (_agent_cases._SHELL_SIGNAL_EXIT_BASE + signal.SIGTERM, True),
            (_agent_cases._SHELL_SIGNAL_EXIT_BASE + signal.SIGKILL, True),
            (-signal.SIGTERM, True),
            (-signal.SIGKILL, True),
            (0, False),
            (1, False),
        )
        for returncode, expected_interrupted in cases:
            with self.subTest(returncode=returncode):
                proc = _support.completed(returncode=returncode)
                with patch(_agent_cases._POPEN_TARGET, return_value=proc):
                    run_result = _processes.run_subprocess(
                        [_agent_cases._AGENT_COMMAND], _agent_cases._CWD, {}, 10,
                    )
                self.assertEqual(run_result.exit_code, returncode)
                self.assertFalse(run_result.timed_out)
                self.assertEqual(run_result.interrupted, expected_interrupted)

    def test_signal_exit_marked_interrupted(self) -> None:
        # Both shutdown-sweep signals produce a completed-but-interrupted run:
        # negative returncode, `interrupted=True`, and `timed_out=False`.
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=sig):
                *_, exit_code, timed_out, interrupted = self._kill_self(sig)
                self.assertEqual(exit_code, -sig)
                self.assertFalse(timed_out)
                self.assertTrue(interrupted)

    def test_clean_exit_not_interrupted(self) -> None:
        # A normal non-zero failure (exit 3) is a completed run, NOT an
        # interruption -- the two must stay distinguishable downstream.
        cmd = [sys.executable, _agent_cases._PYTHON_COMMAND_FLAG, "import sys; sys.exit(3)"]
        *_, exit_code, timed_out, interrupted = _processes.run_subprocess(
            cmd,
            _agent_cases._REAL_CWD,
            dict(os.environ),
            _agent_cases._SUBPROCESS_TIMEOUT_SECONDS,
        )
        self.assertEqual(exit_code, 3)
        self.assertFalse(timed_out)
        self.assertFalse(interrupted)

    def test_own_timeout_is_timed_out(self) -> None:
        # A child that outlives our own `timeout` drives the timeout branch:
        # `terminate_process_group` reaps the group and the run is classified
        # `timed_out=True`, `interrupted=False`, exit_code=-1 -- distinct from
        # the shutdown-sweep interruption above even though both signal the
        # group. Real child + 1s timeout so the whole flatten path is exercised.
        cmd = [sys.executable, _agent_cases._PYTHON_COMMAND_FLAG, "import time; time.sleep(30)"]
        *_, exit_code, timed_out, interrupted = _processes.run_subprocess(
            cmd, _agent_cases._REAL_CWD, dict(os.environ), 1
        )
        self.assertEqual(exit_code, -1)
        self.assertTrue(timed_out)
        self.assertFalse(interrupted)

    def _kill_self(self, sig: signal.Signals) -> tuple[str, str, int, bool, bool]:
        # Drive a REAL child that signals itself, so the negative returncode is
        # produced by the kernel + Popen exactly as it is when the shutdown
        # sweep SIGTERMs/SIGKILLs the group, not synthesized by a mock.
        cmd = [
            sys.executable,
            _agent_cases._PYTHON_COMMAND_FLAG,
            f"import os, signal; os.kill(os.getpid(), {int(sig)})",
        ]
        return _processes.run_subprocess(
            cmd,
            _agent_cases._REAL_CWD,
            dict(os.environ),
            _agent_cases._SUBPROCESS_TIMEOUT_SECONDS,
        )
