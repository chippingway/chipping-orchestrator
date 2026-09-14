# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Agent run options and result models."""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple, TypedDict

from orchestrator import config
from orchestrator.observability.usage.metrics import UsageMetrics


@dataclass
class AgentResult:
    """Normalized outcome returned by either supported agent backend."""

    session_id: str | None
    last_message: str
    exit_code: int
    timed_out: bool
    stdout: str
    stderr: str
    interrupted: bool = False
    usage: UsageMetrics | None = None
    # Whether a process was invoked for this result at all. True for every
    # run either backend produced, including the ones a shutdown kill or a
    # timeout cut short -- those reached a CLI, and what they left behind on
    # disk is theirs. False only for a launch turned away before the spawn,
    # which the stages have to be able to tell apart: a worktree they would
    # otherwise read a killed run's leavings out of carries nothing this
    # result put there.
    invoked: bool = True


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
