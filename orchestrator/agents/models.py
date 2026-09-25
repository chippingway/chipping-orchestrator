# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Agent run options, result models, and unfinished tool step diagnostics."""
from __future__ import annotations

import signal
from dataclasses import dataclass
from typing import NamedTuple, TypedDict

from orchestrator import config
from orchestrator.observability.usage.agy_events import ToolLifecycle
from orchestrator.observability.usage.metrics import UsageMetrics


@dataclass
class AgentResult:
    """Normalized outcome returned by any supported agent backend."""

    session_id: str | None
    last_message: str
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str
    interrupted: bool = False
    usage: UsageMetrics | None = None
    # Whether a process was invoked for this result at all. True for every
    # run any backend produced, including the ones a shutdown kill or a
    # timeout cut short -- those reached a CLI, and what they left behind on
    # disk is theirs. False for every result no process produced: a launch
    # turned away before the spawn, and the ones a stage SYNTHESIZES when it
    # publishes committed work an earlier run left behind. The stages have to
    # be able to tell those apart from a run's own output -- a worktree they
    # would otherwise read a killed run's leavings out of carries nothing this
    # result put there, and a developer-report contract answered by a sentence
    # the orchestrator wrote itself is no report at all.
    invoked: bool = True
    # Unfinished tool steps reported by a backend's lifecycle reducer (such
    # as Antigravity tool lifecycles where active commands remained when a
    # terminal envelope was emitted). Empty for completed or non-AGY runs.
    unfinished_steps: tuple[ToolLifecycle, ...] = ()


CodexResult = AgentResult


@dataclass(frozen=True)
class AgentRunOptions:
    """Optional controls shared by fresh agent runs and session resumes."""

    resume_session_id: str | None = None
    extra_env: dict[str, str] | None = None
    timeout: int | None = None
    extra_args: tuple[str, ...] = ()

    @property
    def timeout_seconds(self) -> int:
        return self.timeout or config.AGENT_TIMEOUT


class AgentRunOptionFields(TypedDict, total=False):
    """Legacy keyword controls accepted beside ``AgentRunOptions``."""

    resume_session_id: str | None
    extra_env: dict[str, str] | None
    timeout: int | None
    extra_args: tuple[str, ...]


class SubprocessResult(NamedTuple):
    """Captured process streams and termination classification."""

    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    interrupted: bool


_SHELL_SIGNAL_EXIT_BASE = 128
_INTERRUPTED_EXIT_CODES = frozenset((
    -signal.SIGTERM,
    -signal.SIGKILL,
    _SHELL_SIGNAL_EXIT_BASE + signal.SIGTERM,
    _SHELL_SIGNAL_EXIT_BASE + signal.SIGKILL,
))


def is_signal_interrupted(agent_result: AgentResult) -> bool:
    """True when `agent_result` was terminated by an operating system signal
    (such as SIGTERM/SIGKILL from the shutdown sweep), as opposed to a backend
    cancellation or error exit."""
    if getattr(agent_result, "timed_out", None) is True:
        return False
    if not getattr(agent_result, "interrupted", False):
        return False
    exit_code = getattr(agent_result, "exit_code", None)
    if not isinstance(exit_code, int):
        return False
    return exit_code in _INTERRUPTED_EXIT_CODES


def is_shutdown_sweep_interrupted(agent_result: AgentResult) -> bool:
    """True when `agent_result` represents a genuine shutdown interruption.

    A process-signal interruption (SIGTERM/SIGKILL or shell-signal return code)
    is ALWAYS a shutdown sweep kill regardless of whether partial output
    happened to contain active tool steps. For backend cancellations (e.g. AGY
    CANCELED/INTERRUPTED statuses with normal process exit codes), only runs
    without structured unfinished tool steps are ignored as interruptions; runs
    carrying structured unfinished steps are execution failures that must
    proceed to disposition. Timed-out runs are never shutdown interruptions.
    """
    if getattr(agent_result, "timed_out", None) is True:
        return False
    if not getattr(agent_result, "interrupted", False):
        return False
    if is_signal_interrupted(agent_result):
        return True
    unfinished = getattr(agent_result, "unfinished_steps", ())
    return not (isinstance(unfinished, (tuple, list)) and bool(unfinished))
