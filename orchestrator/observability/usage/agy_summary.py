# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity usage for the steps emitted by one process invocation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orchestrator.observability.usage import agy_events, event_stream, protocol

if TYPE_CHECKING:
    from orchestrator.observability.usage.metrics import UsageMetrics


def completed_steps(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Count each completed step once, even if the CLI repeats its frame."""
    steps: dict[int, dict[str, Any]] = {}
    for step in agy_events.payloads(events, agy_events.STEP_UPDATE):
        index = step.get(agy_events.STEP_INDEX)
        if isinstance(index, int) and step.get(agy_events.STATE) == agy_events.DONE:
            steps[index] = step
    return list(steps.values())


def usage_records(
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # Terminal usage includes earlier conversation turns on a resume. Only
    # the steps emitted by this invocation belong in its per-run counters.
    return [
        step[protocol.USAGE]
        for step in completed_steps(events)
        if isinstance(step.get(protocol.USAGE), dict)
    ]


def apply_usage(
    events: list[dict[str, Any]],
    metrics: UsageMetrics,
    fallback_model: str | None,
) -> None:
    records = usage_records(events)
    metrics.input_tokens = sum(
        event_stream.token_count(row.get(protocol.INPUT_TOKENS)) for row in records
    )
    metrics.output_tokens = sum(
        event_stream.token_count(row.get(protocol.OUTPUT_TOKENS)) for row in records
    )
    metrics.cache_read_tokens = sum(
        event_stream.token_count(row.get("cache_read_tokens")) for row in records
    )
    metrics.turns = sum(
        step.get(agy_events.STEP_TYPE) == "user_input" for step in completed_steps(events)
    ) or None
    metrics.models = event_stream.dedup_models(
        init[protocol.MODEL]
        for init in agy_events.payloads(events, agy_events.INIT)
        if isinstance(init.get(protocol.MODEL), str)
    )
    if not metrics.models and fallback_model:
        metrics.models = (fallback_model,)
    metrics.cost_source = "unknown-price" if records else "no-usage"
