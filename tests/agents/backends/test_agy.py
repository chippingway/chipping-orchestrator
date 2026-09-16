# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity command, conversation identity, and terminal-result handling."""

import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import models, runner
from orchestrator.agents.backends import agy
from tests.agents import agent_test_support as support, agent_test_values as cases
from tests.support import agy_stream as stream

_TIMEOUT = 7200
_BINARY = "/opt/antigravity/agy"
_TIMEOUT_FLAG = "--print-timeout"
_NOISE = '\nwarning\n[]\nnull\n{"event":"result","result":[]}\n'


class AntigravityCommandTest(unittest.TestCase):
    def test_command_preserves_args_and_timeout(self) -> None:
        for session_id in (None, stream.SESSION_ID):
            with self.subTest(session_id=session_id), patch.object(config, "AGY_BIN", _BINARY):
                command = agy.agy_command(cases._PROMPT, models.AgentRunOptions(
                    extra_args=stream.ARGS, timeout=_TIMEOUT, resume_session_id=session_id,
                ))
                expected = [
                    _BINARY, *stream.ARGS,
                    "--dangerously-skip-permissions", "--output-format", "stream-json",
                    "--input-format", "text", _TIMEOUT_FLAG, f"{_TIMEOUT}s",
                ]
                if session_id:
                    expected += ["--conversation", session_id]
                self.assertEqual(command, [*expected, "--print", cases._PROMPT])

    def test_default_timeout_comes_from_orchestrator(self) -> None:
        with patch.object(config, "AGENT_TIMEOUT", _TIMEOUT):
            command = agy.agy_command(cases._PROMPT, models.AgentRunOptions())
        self.assertEqual(command[command.index(_TIMEOUT_FLAG) + 1], f"{_TIMEOUT}s")

    def test_dispatch_reads_session_and_final_message(self) -> None:
        with patch(cases._POPEN_TARGET, return_value=support.completed(stdout=stream.resumed_stream())) as process:
            agent_result = runner.run_agent(stream.BACKEND, cases._PROMPT, cases._CWD, extra_args=stream.ARGS)
            self.assertEqual(process.call_args.kwargs["cwd"], str(cases._CWD))
        self.assertEqual(agent_result.session_id, stream.SESSION_ID)
        self.assertEqual(agent_result.last_message, stream.ANSWER)
        self.assertEqual(agent_result.exit_code, 0)


class AntigravityResultTest(unittest.TestCase):
    def test_failures_do_not_publish_partial_answers(self) -> None:
        for terminal_status in (stream.FAILURE, "WAITING", "RUNNING", "INVALID", "INTERRUPTED", "CANCELED", None):
            with self.subTest(status=terminal_status):
                stdout = stream.step(1, text_delta="partial report")
                if terminal_status:
                    stdout = "\n".join((stdout, stream.terminal(terminal_status, error="provider diagnostic")))
                agent_result = agy.agy_result(
                    models.AgentRunOptions(), models.SubprocessResult(stdout, "", 0, False, False),
                )
                self.assertEqual(agent_result.last_message, "")
                self.assertNotEqual(agent_result.exit_code, 0)
                self.assertTrue(agent_result.stderr)
                self.assertEqual(agent_result.interrupted, terminal_status in {"INTERRUPTED", "CANCELED"})

    def test_process_termination_is_preserved(self) -> None:
        terminations = (
            (1, False, False),
            (-9, True, False),
            (-15, False, True),
        )
        for exit_code, timed_out, interrupted in terminations:
            with self.subTest(exit_code=exit_code):
                agent_result = agy.agy_result(
                    models.AgentRunOptions(resume_session_id=stream.SESSION_ID),
                    models.SubprocessResult("", "stderr diagnostic", exit_code, timed_out, interrupted),
                )
                self.assertEqual((agent_result.exit_code, agent_result.timed_out, agent_result.interrupted),
                                 (exit_code, timed_out, interrupted))
                self.assertEqual(agent_result.session_id, stream.SESSION_ID)
                self.assertIn("stderr diagnostic", agent_result.stderr)

    def test_malformed_output_is_tolerated(self) -> None:
        terminals = (
            (stream.terminal(), stream.ANSWER, 0),
            (stream.event("result", status=stream.SUCCESS, response=None), "", 1),
            (stream.event("result", status=[], response=stream.ANSWER), "", 1),
        )
        for terminal, answer, exit_code in terminals:
            with self.subTest(terminal=terminal):
                agent_result = agy.agy_result(
                    models.AgentRunOptions(), models.SubprocessResult(_NOISE + terminal, "", 0, False, False),
                )
                self.assertEqual(agent_result.last_message, answer)
                self.assertEqual(agent_result.exit_code, exit_code)
