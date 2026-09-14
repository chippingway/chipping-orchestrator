# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Agent invocation requests and the stable launch identity charged to an issue.

The fingerprint describes the requested logical round. The budget reservation
uses it to recognize a paid launch across a crash before process invocation."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from orchestrator.workflow.engine import (
    run_budget_models as _run_budget_models,
)


@dataclass(frozen=True)
class _AgentRunRequest:
    """Agent invocation plus the audit/analytics context that follows it."""

    agent_role: str
    stage: str
    backend: str
    prompt: str
    cwd: Path
    agent_spec: str | None = None
    resume_session_id: str | None = None
    timeout: int | None = None
    extra_args: tuple[str, ...] = ()
    review_round: int | None = None
    retry_count: int | None = None

    @property
    def fingerprint(self) -> str:
        """What identifies this launch to a charge taken across ticks.

        Stable is the whole requirement. A charge recorded by a tick that then
        died is only worth reusing if the launch coming back can be recognized
        as the one that took it, so the digest is taken over what a request IS
        -- the role, the stage, the backend and the spec behind it, the
        session it continues, the round and the attempt it stands at.

        The prompt is deliberately not among them, and neither is the worktree
        it runs in. A prompt is rebuilt every tick out of an issue body, a
        thread, and a repository catalog that all move underneath it, so a
        digest counting it would call every launch a new one and no crash
        window would ever be recognized. What is left is what a human reading
        the pinned state would name the launch by anyway.
        """
        named = (
            self.agent_role,
            self.stage,
            self.backend,
            self.agent_spec,
            self.resume_session_id,
            self.review_round,
            self.retry_count,
        )
        parts = ["" if part is None else str(part) for part in named]
        return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()

    @property
    def launch(self) -> _run_budget_models.AgentRunLaunch:
        """What the circuit charges this request under, and records it as.

        The fingerprint identifies the launch to a charge taken across ticks;
        the stage and the role are what the budget record is read BY, and they
        are the literals the `agent_spawn` pair below already carries, so the
        charge and the spawn cannot name different work.
        """
        return _run_budget_models.AgentRunLaunch(
            fingerprint=self.fingerprint,
            stage=self.stage,
            agent_role=self.agent_role,
        )


def _agent_run_kwargs(request: _AgentRunRequest) -> dict[str, Any]:
    """Forward only optional runner kwargs that the caller supplied."""
    kwargs: dict[str, Any] = {"extra_args": request.extra_args}
    if request.resume_session_id is not None:
        kwargs["resume_session_id"] = request.resume_session_id
    if request.timeout is not None:
        kwargs["timeout"] = request.timeout
    return kwargs
