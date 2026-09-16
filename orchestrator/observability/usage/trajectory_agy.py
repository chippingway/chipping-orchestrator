# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity text deltas and tool steps in their stream order."""

from __future__ import annotations

from typing import Any

from orchestrator.observability.usage import agy_events, protocol
from orchestrator.observability.usage.trajectory_models import AgentTrajectory, TrajectoryStep

_TEXT = "text"


def _group_steps(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for step in agy_events.payloads(events, agy_events.STEP_UPDATE):
        index = step.get(agy_events.STEP_INDEX)
        if not isinstance(index, int):
            continue
        previous = grouped.get(index, {})
        if previous.get(agy_events.STATE) == agy_events.DONE:
            continue
        text_delta = step.get("text_delta")
        if not isinstance(text_delta, str):
            text_delta = ""
        grouped[index] = {
            **previous, **step, _TEXT: previous.get(_TEXT, "") + text_delta,
        }
    return list(grouped.values())


def _tool_steps(step: dict[str, Any]) -> list[TrajectoryStep]:
    tool = step.get("tool_info")
    if not isinstance(tool, dict):
        return []
    tool_id = str(step[agy_events.STEP_INDEX])
    name = str(tool.get("name") or step.get("tool_name") or "")
    steps = [TrajectoryStep(
        "tool_call", name=name, tool_id=tool_id, content=tool.get("parameters"),
    )]
    if "output" in tool or "error" in tool:
        steps.append(TrajectoryStep(
            "tool_result", name=name, tool_id=tool_id,
            content=tool.get("error", tool.get("output")),
        ))
    return steps


def reconstruct(events: list[dict[str, Any]]) -> AgentTrajectory:
    steps: list[TrajectoryStep] = []
    for step in _group_steps(events):
        if step.get(agy_events.STEP_TYPE) == "agent_response" and step[_TEXT]:
            steps.append(TrajectoryStep("assistant_message", content=step[_TEXT]))
        elif step.get(agy_events.STEP_TYPE) == "tool":
            steps.extend(_tool_steps(step))
    tools = dict.fromkeys(
        name
        for init in agy_events.payloads(events, agy_events.INIT)
        if isinstance(init.get("tools"), list)
        for name in init["tools"]
        if isinstance(name, str)
    )
    return AgentTrajectory(
        backend=protocol.AGY,
        tools=tuple(tools),
        steps=tuple(steps),
        final_output=agy_events.final_output(events),
    )
