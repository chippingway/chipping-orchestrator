# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex JSON event builders for usage tests."""

from tests.observability.usage import usage_test_values as _usage_cases


def usage(
    *,
    input: int = 0,
    cached: int = 0,
    output: int = 0,
    cache_write: int | None = None,
) -> dict:
    """A usage block; `cache_write` adds the CLI's flat `cache_write_input_tokens`, omitted when None."""
    block = {
        _usage_cases.INPUT_TOKENS_FIELD: input,
        "cached_input_tokens": cached,
        _usage_cases.OUTPUT_TOKENS_FIELD: output,
    }
    if cache_write is not None:
        block["cache_write_input_tokens"] = cache_write
    return block


def turn_complete(
    *,
    model: str | None = None,
    input: int = 0,
    cached: int = 0,
    output: int = 0,
    cache_write: int | None = None,
) -> dict:
    frame = {_usage_cases.TYPE_FIELD: "turn_complete"}
    if model is not None:
        frame[_usage_cases.MODEL_FIELD] = model
    frame[_usage_cases.USAGE_FIELD] = usage(
        input=input,
        cached=cached,
        output=output,
        cache_write=cache_write,
    )
    return frame


def task_started(**fields: object) -> dict:
    return {_usage_cases.TYPE_FIELD: "task_started", **fields}


def task_complete(**fields: object) -> dict:
    return {_usage_cases.TYPE_FIELD: "task_complete", **fields}


def stream_item(
    item_id: str,
    item_type: str,
    *,
    started: bool = False,
    **extra_fields: object,
) -> dict:
    """One `item.started` / `item.completed` frame of any codex item type."""
    event_type = (
        _usage_cases.ITEM_STARTED_EVENT
        if started
        else _usage_cases.ITEM_COMPLETED_EVENT
    )
    record = {
        _usage_cases.IDENTIFIER_FIELD: item_id,
        _usage_cases.TYPE_FIELD: item_type,
    }
    record.update(extra_fields)
    return {_usage_cases.TYPE_FIELD: event_type, _usage_cases.ITEM_FIELD: record}


def command(
    item_id: str,
    command_text: str,
    *,
    started: bool = False,
    **extra_fields: object,
) -> dict:
    return stream_item(
        item_id,
        "command_execution",
        started=started,
        **{_usage_cases.COMMAND_FIELD: command_text},
        **extra_fields,
    )


def agent_message(item_id: str, message: object, *, started: bool = False) -> dict:
    return stream_item(
        item_id,
        "agent_message",
        started=started,
        **{_usage_cases.TEXT_FIELD: message},
    )
