# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity command construction, conversation resumes, and execution."""

from __future__ import annotations

from pathlib import Path
from typing import Unpack

from orchestrator import config
from orchestrator.agents import (
    environment as _agent_environment,
    models as _agent_models,
    processes as _agent_processes,
    runner as _agent_runner,
)
from orchestrator.observability.usage import agy_events, event_stream


def agy_command(prompt: str, options: _agent_models.AgentRunOptions) -> list[str]:
    """Pin headless output and match the CLI deadline to the process budget."""
    command = [
        config.AGY_BIN,
        *options.extra_args,
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "--input-format",
        "text",
        "--print-timeout",
        f"{options.timeout_seconds}s",
    ]
    if options.resume_session_id:
        command += ["--conversation", options.resume_session_id]
    command += ["--print", prompt]
    return command


def agy_result(
    options: _agent_models.AgentRunOptions,
    process_result: _agent_models.SubprocessResult,
) -> _agent_models.AgentResult:
    """Keep partial output and CLI errors out of the final-message channel."""
    events = event_stream.iter_events(process_result.stdout)
    terminal = agy_events.terminal_result(events)
    final_message = agy_events.final_output(events)
    agent_result = _agent_runner.build_agent_result(
        options, process_result, final_message or "",
    )
    if final_message is None:
        agent_result.exit_code = process_result.exit_code or 1
        error = terminal.get("error") or "Antigravity ended without a successful terminal result."
        agent_result.stderr = f"{process_result.stderr}\n{error}".strip()
        agent_result.interrupted |= terminal.get("status") in ("INTERRUPTED", "CANCELED")
    return agent_result


def run_agy(
    prompt: str,
    cwd: Path,
    *,
    options: _agent_models.AgentRunOptions | None = None,
    **option_fields: Unpack[_agent_models.AgentRunOptionFields],
) -> _agent_models.AgentResult:
    """Run Antigravity through the shared process and credential boundary."""
    run_options = _agent_runner.resolve_agent_run_options(options, option_fields)
    _agent_runner.log_agent_spawn("agy", cwd, run_options)
    process_result = _agent_processes.run_subprocess(
        agy_command(prompt, run_options),
        cwd,
        _agent_environment.agent_env(run_options.extra_env),
        run_options.timeout_seconds,
    )
    return agy_result(run_options, process_result)
