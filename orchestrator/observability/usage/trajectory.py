# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Provider trajectory parser entry points over the shared records."""

from __future__ import annotations

from orchestrator.observability.usage import (
    event_stream,
    protocol,
    trajectory_agy,
    trajectory_claude_stream,
    trajectory_claude_turns,
    trajectory_codex,
)
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
