# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The record a parsed trajectory line becomes, and what it answers with.

Everything stored here is what the sink wrote: the identity of the run, the
text on both sides of it, the normalized steps, and the usage the provider
reported. Everything computed off it is a projection the two sibling owners
define, bound on as properties so a caller reads ``run.timeline`` or
``run.cost_evidence`` rather than calling a helper with the run in hand -- the
shape the page and the filters were written against.

Binding them here rather than defining them here is what keeps the record a
data class: the run is frozen, so a view that reads several fields cannot leave
a half-updated one behind it, and the turn index is cached because a page walks
a timeline entry at a time and each entry asks for its own turn's usage.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from orchestrator.observability.trajectory_viewer import timeline_views, usage_views
from orchestrator.observability.trajectory_viewer.models import (
    RunUsageView,
    TrajectoryStepView,
    TurnUsageView,
)


@dataclass(frozen=True)
class TrajectoryRun:
    """One parsed and normalized agent-trajectory record."""

    seq: int
    ts: str
    repo: str
    issue: int
    stage: str = ""
    agent_role: str = ""
    backend: str = ""
    session_id: str = ""
    review_round: int | None = None
    retry_count: int | None = None
    user_input: str = ""
    system_prompt: str = ""
    output: str = ""
    tools: tuple[str, ...] = ()
    skills_triggered: tuple[str, ...] = ()
    skills_available: tuple[str, ...] = ()
    steps: tuple[TrajectoryStepView, ...] = ()
    run_usage: RunUsageView | None = None
    turns: tuple[TurnUsageView, ...] = ()
    truncated: bool = False

    tool_calls = property(usage_views.tool_calls)
    step_count = property(usage_views.step_count)
    model = property(usage_views.model)
    cost_evidence = property(usage_views.cost_evidence)
    total_tokens = property(usage_views.total_tokens)
    usage_for_turn = usage_views.usage_for_turn
    timeline = property(timeline_views.timeline)
    is_fixture = property(timeline_views.is_fixture)
    detail_label = timeline_views.detail_label
    label = timeline_views.label
    _turn_map = cached_property(timeline_views.turn_map)
