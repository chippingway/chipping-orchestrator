# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared JSON-lines and content-block builders for usage tests."""

import json

from tests.observability.usage import usage_test_values as _usage_cases


def jsonl(*events: dict) -> str:
    return "\n".join(json.dumps(event) for event in events)


def stdout_lines(*emitted: str) -> str:
    """Splice lines a run already emitted as text -- a banner, a truncated
    frame, blank padding -- around a serialized event. `jsonl` cannot carry
    them, because not one of them is a JSON object.
    """
    return "\n".join(emitted)


def without_frames(stdout: str, *frame_types: str) -> str:
    """A captured run's lines, in their order, less every frame of the named types."""
    return "\n".join(
        line for line in stdout.splitlines() if json.loads(line)[_usage_cases.TYPE_FIELD] not in frame_types
    )


def text(text_value: object) -> dict:
    return {_usage_cases.TYPE_FIELD: _usage_cases.TEXT_FIELD, _usage_cases.TEXT_FIELD: text_value}


def tool_use(name: str, tool_input: object, *, id: str | None = None) -> dict:
    block = {
        _usage_cases.TYPE_FIELD: _usage_cases.TOOL_USE_EVENT,
        _usage_cases.NAME_FIELD: name,
        _usage_cases.INPUT_FIELD: tool_input,
    }
    if id is not None:
        block[_usage_cases.IDENTIFIER_FIELD] = id
    return block


def tool_result(tool_use_id: str, tool_content: object) -> dict:
    return {
        _usage_cases.TYPE_FIELD: "tool_result",
        "tool_use_id": tool_use_id,
        "content": tool_content,
    }


def user(message_content: object) -> dict:
    return {
        _usage_cases.TYPE_FIELD: "user",
        "message": {"content": message_content},
    }
