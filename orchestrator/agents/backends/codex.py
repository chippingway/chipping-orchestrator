# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex command construction, scratch output, and execution."""
from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from orchestrator import config
from orchestrator.agents import (
    environment as _agent_environment,
    models as _agent_models,
    processes as _agent_processes,
    runner as _agent_runner,
)


@contextmanager
def codex_last_message_file() -> Iterator[Path]:
    """Yield a per-spawn last-message path outside the worktree."""
    descriptor, path_string = tempfile.mkstemp(
        prefix="codex-last-",
        suffix=".txt",
    )
    os.close(descriptor)
    last_message_path = Path(path_string)
    try:
        yield last_message_path
    finally:
        last_message_path.unlink(missing_ok=True)


def read_last_message(last_message_path: Path) -> str:
    """Read Codex's last-message file, or empty text when unavailable."""
    if not last_message_path.exists():
        return ""
    try:
        return last_message_path.read_text(errors="replace")
    except OSError:
        return ""


def codex_command(
    prompt: str,
    cwd: Path,
    last_message_path: Path,
    options: _agent_models.AgentRunOptions,
) -> list[str]:
    """Build fresh or resumed Codex argv with fixed safety/output flags."""
    absolute_cwd = Path(cwd).resolve()
    common_args = [
        "--dangerously-bypass-approvals-and-sandbox",
        "--json",
        "-o",
        str(last_message_path),
    ]
    if options.resume_session_id:
        return [
            config.CODEX_BIN,
            *options.extra_args,
            "exec",
            "resume",
            *common_args,
            options.resume_session_id,
            prompt,
        ]
    return [
        config.CODEX_BIN,
        *options.extra_args,
        "exec",
        "-C",
        str(absolute_cwd),
        *common_args,
        prompt,
    ]


def run_codex(
    prompt: str,
    cwd: Path,
    *,
    options: _agent_models.AgentRunOptions,
) -> _agent_models.AgentResult:
    """Run Codex through the shared process owner."""
    with codex_last_message_file() as last_message_path:
        _agent_runner.log_agent_spawn("codex", cwd, options)
        process_result = _agent_processes.run_subprocess(
            codex_command(prompt, cwd, last_message_path, options),
            cwd,
            _agent_environment.agent_env(options.extra_env),
            options.timeout_seconds,
        )
        return _agent_runner.build_agent_result(
            options,
            process_result,
            read_last_message(last_message_path),
        )
