# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The package API an agent run is driven through.

Result and option models live in the ``models`` owner, credential filtering /
injected git identity in the ``environment`` owner, the backend-agnostic
session-id walk in the ``session_ids`` owner, Claude final-message parsing in
the ``sessions`` owner, the transient-provider verdict read off that output in
the ``provider_failures`` owner, the shared process registry and the runs
spawned into it in the ``processes`` owner, the group drain, liveness probe,
and signal escalation those teardowns spend in the ``process_groups`` owner,
and shared dispatch -- backend selection, result assembly, and spawn logging --
in the ``runner`` owner; per-backend command construction and execution live in
the ``agents.backends`` subpackage (``codex`` and ``claude``). This initializer
re-exports the narrow public surface (``__all__``): the model types, the
``run_agent`` dispatch entry, and the ``terminate_all_running`` shutdown hook.

``run_agent`` reaches the backend owner modules directly at dispatch time, and
runners plus the verify runner reach the process, process-group, and
environment owners directly, so nothing private is published here.
"""
from __future__ import annotations

from orchestrator.agents import models as _agent_models, processes as _agent_processes, runner as _agent_runner

__all__ = (
    "AgentResult",
    "AgentRunOptions",
    "CodexResult",
    "run_agent",
    "terminate_all_running",
)

terminate_all_running = _agent_processes.terminate_all_running
run_agent = _agent_runner.run_agent

AgentResult = _agent_models.AgentResult
CodexResult = _agent_models.CodexResult
AgentRunOptions = _agent_models.AgentRunOptions
