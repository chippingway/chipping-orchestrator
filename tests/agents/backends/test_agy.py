# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity command, conversation identity, and terminal-result handling."""

import os
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.agents import agy_failures, models, runner
from orchestrator.agents.backends import agy
from tests.agents import agent_test_support as support, agent_test_values as cases
from tests.support import agy_stream as stream

_TIMEOUT = 7200
_BINARY = "/opt/antigravity/agy"
_TIMEOUT_FLAG = "--print-timeout"
_NOISE = '\nwarning\n[]\nnull\n{"event":"result","result":[]}\n'
_NO_CHANGE = "Documentation is already covered.\nDOCS: NO_CHANGE\n"
_QUOTA_TERMINAL = stream.terminal(stream.FAILURE, response=_NO_CHANGE, error=stream.QUOTA_MESSAGE)
_ANSWER_STEP = stream.step(4, text_delta=_NO_CHANGE)
_WRAPPED_QUOTA = stream.QUOTA_MESSAGE.replace(" Resets in ", "\nResets in ")

# Explicitly synthetic runs, one per quota diagnostic shape and subprocess
# return. A response step on either side of the error terminal repairs nothing,
# and a message wrapped before its reset keeps the reset.
_QUOTA_RUNS = (
    ("structured stderr, exit 3", models.SubprocessResult(
        stream.init_event(), stream.quota_structured_stderr(), 3, False, False,
    )),
    ("plain stderr, exit 1", models.SubprocessResult(
        _QUOTA_TERMINAL, stream.QUOTA_PLAIN_STDERR, 1, False, False,
    )),
    ("response before the error terminal, exit 0", models.SubprocessResult(
        f"{_ANSWER_STEP}\n{_QUOTA_TERMINAL}", "", 0, False, False,
    )),
    ("response after the error terminal, exit 0", models.SubprocessResult(
        f"{_QUOTA_TERMINAL}\n{_ANSWER_STEP}", "", 0, False, False,
    )),
    ("wrapped terminal error, exit 0", models.SubprocessResult(
        stream.terminal(stream.FAILURE, response=None, error=_WRAPPED_QUOTA), "", 0, False, False,
    )),
    ("wrapped structured stderr, exit 3", models.SubprocessResult(
        stream.init_event(), stream.quota_structured_stderr(f"RESOURCE_EXHAUSTED (code 429): {_WRAPPED_QUOTA}"),
        3, False, False,
    )),
    ("wrapped plain stderr, exit 1", models.SubprocessResult(
        stream.init_event(), f"error: {_WRAPPED_QUOTA} (response may be truncated)\n", 1, False, False,
    )),
)

# Explicitly synthetic failures that are not the account quota: other or
# near-miss structured diagnostics, and quota wording outside the failure
# channels -- in a step, a tool's output, the terminal response, and a stderr
# line the CLI did not open a diagnostic with, even one right below one.
_QUOTA_PROSE = f"The log says: {stream.QUOTA_MESSAGE}"
_UNAVAILABLE = 503
_UNRELATED_RUNS = (
    ("unavailable backend", models.SubprocessResult(
        stream.terminal(stream.FAILURE, response=None, error="UNAVAILABLE: backend unavailable"),
        stream.quota_structured_stderr(
            "UNAVAILABLE (code 503): backend unavailable", status="UNAVAILABLE", error_code=_UNAVAILABLE,
        ),
        3, False, False,
    )),
    ("not retryable", models.SubprocessResult("", stream.quota_structured_stderr(retryable=False), 3, False, False)),
    ("string code", models.SubprocessResult("", stream.quota_structured_stderr(error_code="429"), 3, False, False)),
    ("numeric retryable", models.SubprocessResult("", stream.quota_structured_stderr(retryable=1), 3, False, False)),
    ("quota prose", models.SubprocessResult(
        "\n".join((
            stream.step(1, text_delta=_QUOTA_PROSE),
            stream.ToolStream.tool_step(2, out=_QUOTA_PROSE),
            stream.terminal(stream.FAILURE, response=_QUOTA_PROSE, error="model output was malformed"),
        )),
        f"error: model output was malformed\nnote: {_QUOTA_PROSE}",
        0, False, False,
    )),
)


def _agy_result(process_result: models.SubprocessResult) -> models.AgentResult:
    return agy.agy_result(models.AgentRunOptions(), process_result)


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
            agent_result = runner.run_agent(
                stream.BACKEND, cases._PROMPT, cases._CWD, options=models.AgentRunOptions(extra_args=stream.ARGS),
            )
            self.assertEqual(process.call_args.kwargs["cwd"], str(cases._CWD))
        self.assertEqual(agent_result.session_id, stream.SESSION_ID)
        self.assertEqual(agent_result.last_message, stream.ANSWER)
        self.assertEqual(agent_result.exit_code, 0)


class AntigravityResultTest(unittest.TestCase):
    def test_failures_do_not_publish_partial_answers(self) -> None:
        # Neither a completed response step nor a terminal response carrying
        # DOCS: NO_CHANGE overrides an error, interrupted, or missing terminal.
        for terminal_status in (stream.FAILURE, "WAITING", "RUNNING", "INVALID", "INTERRUPTED", "CANCELED", None):
            with self.subTest(status=terminal_status):
                stdout = _ANSWER_STEP
                error = "provider diagnostic" if terminal_status else ""
                if terminal_status:
                    terminal = stream.terminal(terminal_status, response=_NO_CHANGE, error=error)
                    stdout = f"{stdout}\n{terminal}"
                agent_result = _agy_result(models.SubprocessResult(stdout, "", 0, False, False))
                self.assertEqual(agent_result.last_message, "")
                self.assertEqual(agent_result.exit_code, 1)
                self.assertTrue(agent_result.stderr)
                self.assertEqual(agent_result.interrupted, terminal_status in {"INTERRUPTED", "CANCELED"})
                self.assertEqual(agent_result.terminal_failure, models.TerminalFailure(0, terminal_status, error))

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
                # A timed-out run's exit code is the runner's sentinel for a
                # process it killed, so the record keeps no captured return.
                self.assertEqual(
                    agent_result.terminal_failure, models.TerminalFailure(None if timed_out else exit_code),
                )

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

    def test_active_command_streams_rejected(self) -> None:
        # Both regression streams cannot become successful results: an active command
        # suppresses the terminal message, forces a non-zero exit, retains session_id
        # and stdout, and provides structured diagnostics on unfinished_steps.
        for name, stream_stdout in (
            ("active_command", stream.ToolStream.active_command()),
            ("active_with_checks", stream.ToolStream.active_with_checks()),
        ):
            with self.subTest(stream=name):
                agent_result = agy.agy_result(
                    models.AgentRunOptions(),
                    models.SubprocessResult(stream_stdout, "", 0, False, False),
                )
                self.assertNotEqual(agent_result.exit_code, 0)
                self.assertEqual(agent_result.last_message, "")
                self.assertEqual(agent_result.session_id, stream.SESSION_ID)
                self.assertEqual(agent_result.stdout, stream_stdout)
                self.assertEqual(
                    agent_result.unfinished_steps,
                    (agy.agy_events.ToolLifecycle(step_index=1, tool_name=stream.TOOL_NAME, state="ACTIVE"),),
                )
                self.assertIn("unfinished tool steps", agent_result.stderr)
                self.assertIn("run_command", agent_result.stderr)

    def test_completed_command_retains_success(self) -> None:
        # An eventually completed command retains the ordinary zero-exit final message.
        stdout = stream.ToolStream.completed_command()
        agent_result = agy.agy_result(
            models.AgentRunOptions(),
            models.SubprocessResult(stdout, "", 0, False, False),
        )
        self.assertEqual(agent_result.exit_code, 0)
        self.assertEqual(agent_result.last_message, "Tests completed successfully.")
        self.assertEqual(agent_result.unfinished_steps, ())
        self.assertIsNone(agent_result.terminal_failure)

    def test_repeated_frames_do_not_create_duplicates(self) -> None:
        stdout = stream.ToolStream.repeated_updates()
        agent_result = agy.agy_result(
            models.AgentRunOptions(),
            models.SubprocessResult(stdout, "", 0, False, False),
        )
        self.assertNotEqual(agent_result.exit_code, 0)
        self.assertEqual(agent_result.last_message, "")
        self.assertEqual(len(agent_result.unfinished_steps), 1)
        self.assertEqual(agent_result.unfinished_steps[0].step_index, 1)

    def test_prose_phrases_ignored_in_verdict(self) -> None:
        # No phrase such as "I will wait" participates in classification.
        # Even when earlier text claims it will wait, terminal success is preserved
        # when every command reached DONE.
        stdout = "\n".join((
            stream.init_event(),
            stream.step(1, kind="agent_response", state="DONE", text_delta="I will wait for pytest to finish."),
            stream.ToolStream.tool_step(2, name=stream.TOOL_NAME, state="ACTIVE"),
            stream.ToolStream.tool_step(2, name=stream.TOOL_NAME, state="DONE", out="passed"),
            stream.terminal(status=stream.SUCCESS, response="All done."),
        ))
        agent_result = agy.agy_result(
            models.AgentRunOptions(),
            models.SubprocessResult(stdout, "", 0, False, False),
        )
        self.assertEqual(agent_result.exit_code, 0)
        self.assertEqual(agent_result.last_message, "All done.")
        self.assertEqual(agent_result.unfinished_steps, ())


class AntigravityQuotaTest(unittest.TestCase):
    """The failure record's quota verdict and diagnostics, over synthetic streams."""

    def test_quota_is_read_across_process_exits(self) -> None:
        for name, process_result in _QUOTA_RUNS:
            with self.subTest(run=name):
                agent_result = _agy_result(process_result)
                failure = agent_result.terminal_failure
                self.assertEqual(agent_result.last_message, "")
                self.assertEqual(agent_result.exit_code, process_result.exit_code or 1)
                self.assertEqual(
                    (failure.process_exit_code, failure.quota_exhausted, failure.quota_reset),
                    (process_result.exit_code, True, stream.QUOTA_RESET),
                )

    def test_other_failures_are_not_quota(self) -> None:
        for name, process_result in _UNRELATED_RUNS:
            with self.subTest(run=name):
                agent_result = _agy_result(process_result)
                failure = agent_result.terminal_failure
                self.assertEqual(agent_result.last_message, "")
                self.assertEqual(agent_result.exit_code, process_result.exit_code or 1)
                self.assertEqual(failure.process_exit_code, process_result.exit_code)
                self.assertEqual((failure.quota_exhausted, failure.quota_reset), (False, None))

    def test_successful_quota_prose_stays_an_answer(self) -> None:
        stdout = "\n".join((
            stream.step(1, text_delta=_QUOTA_PROSE),
            stream.terminal(stream.SUCCESS, response=_QUOTA_PROSE),
        ))
        agent_result = _agy_result(models.SubprocessResult(stdout, "", 0, False, False))
        self.assertEqual((agent_result.last_message, agent_result.exit_code), (_QUOTA_PROSE, 0))
        self.assertIsNone(agent_result.terminal_failure)

    def test_diagnostics_redacted_before_truncation(self) -> None:
        # The budget's cut lands inside the secret: truncating first would
        # leave its opening characters behind for the redactor to miss.
        secret = "synthetic-secret-value"
        padding = "x" * (agy_failures._DIAGNOSTIC_BUDGET - 4)
        terminal = stream.terminal(stream.FAILURE, response=None, error=f"{padding}{secret}tail")
        with patch.dict(os.environ, {"AGY_SYNTHETIC_TOKEN": secret}):
            agent_result = _agy_result(models.SubprocessResult(terminal, "", 0, False, False))
        self.assertEqual(agent_result.terminal_failure.error, f"{padding}***t…")
