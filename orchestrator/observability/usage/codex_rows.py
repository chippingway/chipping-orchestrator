# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex cumulative usage-frame decoding and model selection; `codex_requests` says what a frame's counts establish."""

from __future__ import annotations

from typing import Any

from orchestrator.observability.usage import (
    event_stream,
    model_names,
    protocol,
    token_evidence,
)

CODEX_USAGE_PATHS: tuple[tuple[str, ...], ...] = (
    (protocol.USAGE,),
    ("token_usage",),
    (protocol.TOTAL_TOKEN_USAGE,),
    (protocol.INFO_KEY, protocol.TOTAL_TOKEN_USAGE),
    (protocol.INFO_KEY, protocol.USAGE),
    (protocol.PAYLOAD, protocol.USAGE),
    (protocol.PAYLOAD, "token_usage"),
    (protocol.PAYLOAD, protocol.TOTAL_TOKEN_USAGE),
    (protocol.PAYLOAD, protocol.INFO_KEY, protocol.TOTAL_TOKEN_USAGE),
    (protocol.PAYLOAD, protocol.INFO_KEY, protocol.USAGE),
)


def codex_usage_block(event: dict[str, Any]) -> dict[str, Any] | None:
    for path in CODEX_USAGE_PATHS:
        current: Any = event
        for key in path:
            if not isinstance(current, dict):
                current = None
                break
            current = current.get(key)
        if isinstance(current, dict):
            return current
    return None


def nested_usage_field(
    usage: dict[str, Any],
    outer_key: str,
    inner_key: str,
) -> Any:
    outer = usage.get(outer_key)
    return outer.get(inner_key) if isinstance(outer, dict) else None


def codex_usage_record(usage: dict[str, Any]) -> protocol.TokenBucket:
    """The counts one usage block reports, by token class; a class it reports no count for has no key.

    The CLI prints `cache_write_input_tokens` without a lifetime, and as zero where the provider reported no write
    count, so a zero establishes no writes and any other count is kept under the unknown lifetime: a positive one as
    the block's writes, a negative one for the estimate to refuse rather than to read as no count at all.
    """
    input_tokens = token_evidence.first_count(
        usage.get(protocol.INPUT_TOKENS), usage.get("prompt_tokens"), usage.get("total_input_tokens"),
    )
    cached_tokens = token_evidence.first_count(
        usage.get("cached_input_tokens"),
        usage.get(protocol.CACHED_TOKENS),
        nested_usage_field(usage, "input_tokens_details", protocol.CACHED_TOKENS),
        nested_usage_field(usage, "prompt_tokens_details", protocol.CACHED_TOKENS),
    )
    output_tokens = token_evidence.first_count(
        usage.get(protocol.OUTPUT_TOKENS), usage.get("completion_tokens"), usage.get("total_output_tokens"),
    )
    cache_writes = token_evidence.reported_count(usage.get("cache_write_input_tokens"))
    return token_evidence.reported_counts({
        protocol.INPUT: input_tokens,
        protocol.CACHED: cached_tokens,
        protocol.CACHE_WRITE_UNKNOWN_LIFETIME: cache_writes or None,
        protocol.OUTPUT: output_tokens,
    })


def codex_usage_events(
    events: list[dict[str, Any]],
) -> list[protocol.CodexUsageEvent]:
    """Every usage block the stream printed, with the model it names: one reporting only zeros included."""
    usage_events: list[protocol.CodexUsageEvent] = []
    for event in events:
        usage = codex_usage_block(event)
        if usage is not None:
            usage_events.append((model_names.codex_model_name(event, usage), codex_usage_record(usage)))
    return usage_events


def codex_select_model(
    events: list[dict[str, Any]],
    last_model: str,
    fallback_model: str | None,
) -> str | None:
    chosen_model = model_names.known_model(last_model)
    if chosen_model is not None:
        return chosen_model
    stream_model = last_stream_model(events)
    if stream_model is not None:
        return stream_model
    return model_names.known_model(fallback_model)


def last_stream_model(events: list[dict[str, Any]]) -> str | None:
    last_model: str | None = None
    for event in events:
        for payload in event_stream.walk_objects(event):
            model = model_names.known_model(payload.get(protocol.MODEL))
            if model is not None:
                last_model = model
    return last_model


def last_codex_usage(
    usage_events: list[protocol.CodexUsageEvent],
) -> protocol.CodexUsageEvent:
    """The last of `usage_events`, an input, cached, or output class it reports no count for read as zero."""
    nothing_counted = {protocol.INPUT: 0, protocol.CACHED: 0, protocol.OUTPUT: 0}
    if not usage_events:
        return protocol.UNKNOWN, nothing_counted
    model, record = usage_events[-1]
    return model, {**nothing_counted, **record}
