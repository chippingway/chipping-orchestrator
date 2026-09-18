# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity stream envelopes and tool lifecycles shared by execution and observability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

EVENT = "event"
INIT = "init"
RESULT_EVENT = "result"
STEP_UPDATE = "step_update"
STEP_INDEX = "step_index"
STEP_TYPE = "step_type"
STATE = "state"
DONE = "DONE"
SUCCESS = "SUCCESS"
TOOL = "tool"
TOOL_INFO = "tool_info"
TOOL_NAME = "tool_name"
ACTIVE = "ACTIVE"
NAME = "name"


@dataclass(frozen=True, slots=True, init=False)
class ToolLifecycle:
    step_index: int
    tool_name: str
    state: str

    def __init__(
        self,
        step_index: int,
        tool_name: str = "",
        state: str = "",
        *,
        name: str = "",
    ) -> None:
        object.__setattr__(self, "step_index", step_index)
        object.__setattr__(self, "tool_name", tool_name or name)
        object.__setattr__(self, "state", state)

    @property
    def name(self) -> str:
        return self.tool_name

    @classmethod
    def extract_name(cls, step: dict[str, Any]) -> str:
        tool_info = step.get(TOOL_INFO)
        info_name = tool_info.get(NAME) if isinstance(tool_info, dict) else ""
        tool = step.get(TOOL)
        tool_name = ""
        if isinstance(tool, str):
            tool_name = tool
        elif isinstance(tool, dict):
            tool_name = tool.get(NAME, "")
        named = info_name or step.get(TOOL_NAME) or tool_name
        if not named and step.get(STEP_TYPE) == TOOL:
            named = step.get(NAME)
        return str(named) if named else ""

    @classmethod
    def is_tool_step(cls, step: dict[str, Any]) -> bool:
        if step.get(STEP_TYPE) == TOOL:
            return True
        if isinstance(step.get(TOOL_INFO), dict):
            return True
        return bool(cls.extract_name(step))

    @classmethod
    def fold_frame(cls, folded: dict[int, Any], frame: dict[str, Any]) -> None:
        index = frame.get(STEP_INDEX)
        if not isinstance(index, int):
            return
        step = folded.get(index)
        if step is None:
            step = {TOOL: False}
            step[NAME] = ""
            step[STATE] = ""
            folded[index] = step
        tool_name = cls.extract_name(frame)
        if cls.is_tool_step(frame):
            step[TOOL] = True
        if tool_name:
            step[NAME] = tool_name
        state = frame.get(STATE)
        if isinstance(state, str) and state:
            step[STATE] = state


def payloads(
    events: list[dict[str, Any]],
    event_name: str,
) -> list[dict[str, Any]]:
    """Read only the envelope belonging to the named event."""
    return [
        event[event_name]
        for event in events
        if event.get(EVENT) == event_name and isinstance(event.get(event_name), dict)
    ]


def terminal_result(events: list[dict[str, Any]]) -> dict[str, Any]:
    terminal_events = payloads(events, RESULT_EVENT)
    return terminal_events[-1] if terminal_events else {}


def final_output(events: list[dict[str, Any]]) -> str | None:
    """Only a successful terminal response is an agent's final answer."""
    terminal = terminal_result(events)
    response = terminal.get("response")
    if terminal.get("status") == SUCCESS and isinstance(response, str):
        return response
    return None


def tool_lifecycles(
    events: list[dict[str, Any]] | str,
) -> list[ToolLifecycle]:
    """Fold repeated and sparse step updates by step_index into authoritative tool lifecycles."""
    stream_events = events
    if isinstance(stream_events, str):
        from orchestrator.observability.usage import event_stream

        stream_events = event_stream.iter_events(stream_events)

    folded: dict[int, dict[str, Any]] = {}
    for frame in payloads(stream_events, STEP_UPDATE):
        ToolLifecycle.fold_frame(folded, frame)

    return [
        ToolLifecycle(index, step[NAME], step[STATE])
        for index, step in folded.items()
        if step[TOOL]
    ]


def incomplete_tool_steps(
    events: list[dict[str, Any]] | str,
) -> list[ToolLifecycle]:
    """Report every indexed tool step whose latest state is not DONE."""
    return [
        step
        for step in tool_lifecycles(events)
        if step.state != DONE
    ]
