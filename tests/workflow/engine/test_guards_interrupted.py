# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Distinguishing process-signal interruptions from backend cancellation."""

from __future__ import annotations

import signal
import unittest
from unittest.mock import MagicMock

from orchestrator.agents.models import (
    ToolLifecycle,
    is_shutdown_sweep_interrupted,
    is_signal_interrupted,
)
from orchestrator.workflow.engine import guards as _guards
from tests.support.fakes import make_issue
from tests.workflow.fixtures import _agent

_ACTIVE_STEP = ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE")
_SHELL_BASE = 128
_SHELL_SIGTERM = _SHELL_BASE + signal.SIGTERM
_SHELL_SIGINT = _SHELL_BASE + signal.SIGINT
_NON_INTERRUPTED_CODES = (0, 1, 3, -1, -signal.SIGINT, _SHELL_SIGINT)
_SESSION = "sess-1"
_ISSUE_NUMBER = 42


class InterruptedGuardsTest(unittest.TestCase):
    """How shutdown-sweep signal kills and backend cancellation differ."""

    def test_signal_interrupted(self) -> None:
        uninterrupted_run = _agent(
            session_id=_SESSION,
            exit_code=-signal.SIGTERM,
            interrupted=False,
        )
        self.assertFalse(is_signal_interrupted(uninterrupted_run))

        for code in (-signal.SIGTERM, -signal.SIGKILL, _SHELL_SIGTERM):
            with self.subTest(code=code):
                signaled_run = _agent(
                    session_id=_SESSION,
                    exit_code=code,
                    interrupted=True,
                )
                self.assertTrue(is_signal_interrupted(signaled_run))

        for code in _NON_INTERRUPTED_CODES:
            with self.subTest(code=code):
                normal_exit_run = _agent(
                    session_id=_SESSION,
                    exit_code=code,
                    interrupted=True,
                )
                self.assertFalse(is_signal_interrupted(normal_exit_run))

        self.assertFalse(is_signal_interrupted(_agent(
            session_id=_SESSION,
            exit_code=-signal.SIGTERM,
            interrupted=True,
            timed_out=True,
        )))

        mock_run = MagicMock()
        mock_run.interrupted = True
        mock_run.exit_code = MagicMock()
        self.assertFalse(is_signal_interrupted(mock_run))

    def test_shutdown_sweep_interrupted(self) -> None:
        signal_with_steps = _agent(
            session_id=_SESSION,
            last_message="partial output",
            exit_code=-signal.SIGTERM,
            interrupted=True,
            unfinished_steps=(_ACTIVE_STEP,),
        )
        self.assertTrue(is_shutdown_sweep_interrupted(signal_with_steps))

        for code in (1, _SHELL_BASE + signal.SIGINT):
            with self.subTest(code=code):
                backend_canceled_with_steps = _agent(
                    session_id=_SESSION,
                    last_message="quota exhausted",
                    exit_code=code,
                    interrupted=True,
                    unfinished_steps=(_ACTIVE_STEP,),
                )
                self.assertFalse(is_shutdown_sweep_interrupted(backend_canceled_with_steps))

        backend_canceled_no_steps = _agent(
            session_id=_SESSION,
            exit_code=1,
            interrupted=True,
            unfinished_steps=(),
        )
        self.assertTrue(is_shutdown_sweep_interrupted(backend_canceled_no_steps))

        timed_out_with_steps = _agent(
            session_id=_SESSION,
            exit_code=-1,
            interrupted=True,
            timed_out=True,
            unfinished_steps=(_ACTIVE_STEP,),
        )
        self.assertFalse(is_shutdown_sweep_interrupted(timed_out_with_steps))

    def test_ignore_if_interrupted(self) -> None:
        issue = make_issue(_ISSUE_NUMBER)
        with self.assertLogs("orchestrator.workflow", level="INFO") as captured:
            self.assertTrue(_guards._ignore_if_interrupted(
                issue,
                _agent(
                    session_id=_SESSION,
                    last_message="killed by sigterm",
                    exit_code=-signal.SIGTERM,
                    interrupted=True,
                    unfinished_steps=(_ACTIVE_STEP,),
                ),
            ))
            messages = list(captured.output)
        self.assertTrue(any("interrupted by shutdown sweep" in entry for entry in messages))

        for code in (1, _SHELL_BASE + signal.SIGINT):
            with self.subTest(code=code):
                self.assertFalse(_guards._ignore_if_interrupted(
                    issue,
                    _agent(
                        session_id=_SESSION,
                        last_message="backend canceled",
                        exit_code=code,
                        interrupted=True,
                        unfinished_steps=(_ACTIVE_STEP,),
                    ),
                ))

        self.assertFalse(_guards._ignore_if_interrupted(
            issue,
            _agent(
                session_id=_SESSION,
                last_message="timed out",
                exit_code=-1,
                interrupted=True,
                timed_out=True,
                unfinished_steps=(_ACTIVE_STEP,),
            ),
        ))
