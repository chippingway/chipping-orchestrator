# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Provider trajectory parser entry points over the shared records.

Two dispatches share this owner. `parse_agent_trajectory` reconstructs what a run did; `parse_agent_request_usage`
collects the per-request usage observations its stream reports, which a caller attaches as the trajectory's
`request_usage` under a failure boundary of its own, so a collector that fails costs the trajectory nothing. An
Antigravity and a Claude stream each have a request collector; a Codex run collects none, which a record states by
leaving the field out.
"""

from __future__ import annotations

from orchestrator.observability.usage import (
    event_stream,
    protocol,
    request_agy,
    request_claude,
    trajectory_agy,
    trajectory_claude_stream,
    trajectory_claude_turns,
    trajectory_codex,
)
from orchestrator.observability.usage.request_coverage import RequestUsage
from orchestrator.observability.usage.skills import (
    parse_claude_skills,
    parse_codex_skills,
)
from orchestrator.observability.usage.trajectory_models import AgentTrajectory


def parse_claude_trajectory(stdout: str) -> AgentTrajectory:
    """Classify a Claude stream-json run's trajectory."""
    events = event_stream.iter_events(stdout)
    return AgentTrajectory(
        backend=protocol.CLAUDE,
        tools=trajectory_claude_stream.offered_tools(events),
        skills=parse_claude_skills(stdout),
        steps=trajectory_claude_stream.trajectory_steps(events),
        final_output=trajectory_claude_stream.final_output(events),
        turns=trajectory_claude_turns.claude_turn_usage(events),
    )


def parse_codex_trajectory(stdout: str) -> AgentTrajectory:
    """Classify a Codex JSON run's trajectory."""
    events = event_stream.iter_events(stdout)
    # The steps and the accounting of the items behind them come off one fold
    # of the stream: which items reached a step is part of what that fold
    # decides, so asking for them separately would re-derive it.
    timeline = trajectory_codex.reconstruct(events)
    return AgentTrajectory(
        backend=protocol.CODEX,
        skills=parse_codex_skills(stdout),
        steps=timeline.steps,
        source_items=timeline.source_items,
        final_output=trajectory_codex.final_output(events),
    )


def parse_agent_trajectory(backend: str, stdout: str) -> AgentTrajectory:
    """Dispatch trajectory parsing by agent backend."""
    if backend == protocol.CLAUDE:
        return parse_claude_trajectory(stdout)
    if backend == protocol.CODEX:
        return parse_codex_trajectory(stdout)
    if backend == protocol.AGY:
        return trajectory_agy.reconstruct(event_stream.iter_events(stdout))
    raise ValueError(
        f"unknown agent backend {backend!r}; expected 'claude', 'codex', or 'agy'",
    )


def parse_agent_request_usage(
    backend: str,
    stdout: str,
    fallback_model: str | None = None,
) -> RequestUsage | None:
    """Dispatch request-usage collection by agent backend; None where the backend has no request collector.

    `fallback_model` is the configured model a request is attributed to where the stream names none.
    """
    if backend == protocol.AGY:
        return request_agy.collect(stdout, fallback_model)
    if backend == protocol.CLAUDE:
        return request_claude.collect(stdout, fallback_model)
    if backend == protocol.CODEX:
        return None
    raise ValueError(
        f"unknown agent backend {backend!r}; expected 'claude', 'codex', or 'agy'",
    )
