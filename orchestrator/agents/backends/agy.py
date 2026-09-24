# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity command construction, terminal-result gating, and conversation resumes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Unpack

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


def _unfinished_diagnostic(steps: tuple[_agent_models.ToolLifecycle, ...]) -> str:
    descriptions = ", ".join(
        f"step {step.step_index} ({step.tool_name})" if step.tool_name else f"step {step.step_index}"
        for step in steps
    )
    return f"Antigravity ended with unfinished tool steps: {descriptions}."


def _terminal_error(
    terminal: dict[str, Any],
    steps: tuple[_agent_models.ToolLifecycle, ...],
) -> str:
    if steps:
        diagnostic = _unfinished_diagnostic(steps)
        err = terminal.get("error")
        return f"{err}\n{diagnostic}".strip() if err else diagnostic
    return str(terminal.get("error") or "Antigravity ended without a successful terminal result.")


def _final_message(
    events: list[dict[str, Any]],
    steps: tuple[_agent_models.ToolLifecycle, ...],
) -> str | None:
    if steps:
        return None
    return agy_events.final_output(events)


def _apply_failure_outcome(
    agent_result: _agent_models.AgentResult,
    process_result: _agent_models.SubprocessResult,
    events: list[dict[str, Any]],
    unfinished_steps: tuple[_agent_models.ToolLifecycle, ...],
) -> None:
    terminal = agy_events.terminal_result(events)
    error = _terminal_error(terminal, unfinished_steps)
    agent_result.exit_code = process_result.exit_code or 1
    agent_result.stderr = f"{process_result.stderr}\n{error}".strip()
    agent_result.interrupted |= terminal.get("status") in ("INTERRUPTED", "CANCELED")


def agy_result(
    options: _agent_models.AgentRunOptions,
    process_result: _agent_models.SubprocessResult,
) -> _agent_models.AgentResult:
    """Gate terminal success on completed tool lifecycles and keep partial output out of the final message."""
    events = event_stream.iter_events(process_result.stdout)
    unfinished_steps = tuple(agy_events.incomplete_tool_steps(events))
    final_message = _final_message(events, unfinished_steps)
    agent_result = _agent_runner.build_agent_result(
        options,
        process_result,
        final_message or "",
        unfinished_steps=unfinished_steps,
    )
    if final_message is None:
        _apply_failure_outcome(agent_result, process_result, events, unfinished_steps)
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
