# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Agent result and run-option model tests."""

from __future__ import annotations

import unittest

from orchestrator.agents import models as _models


class AgentResultTest(unittest.TestCase):
    def test_interrupted_defaults_false(self) -> None:
        # `interrupted` is optional at construction, so a result built
        # without it reads as a clean, non-interrupted run.
        agent_result = _models.AgentResult(
            session_id=None,
            last_message="",
            exit_code=0,
            timed_out=False,
            stdout="",
            stderr="",
        )
        self.assertFalse(agent_result.interrupted)

    def test_unfinished_steps_defaults_empty(self) -> None:
        # Synthetic non-AGY results remain backward compatible without the field.
        agent_result = _models.AgentResult(
            session_id=None,
            last_message="",
            exit_code=0,
            timed_out=False,
            stdout="",
            stderr="",
        )
        self.assertEqual(agent_result.unfinished_steps, ())
        self.assertFalse(agent_result.unfinished_steps)

    def test_unfinished_steps_preserved(self) -> None:
        step = _models.ToolLifecycle(step_index=1, tool_name="run_command", state="ACTIVE")
        agent_result = _models.AgentResult(
            session_id=None,
            last_message="",
            exit_code=1,
            timed_out=False,
            stdout="",
            stderr="",
            unfinished_steps=(step,),
        )
        self.assertEqual(agent_result.unfinished_steps, (step,))
