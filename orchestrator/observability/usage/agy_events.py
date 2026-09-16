# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity stream envelopes shared by execution and observability."""

from __future__ import annotations

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
