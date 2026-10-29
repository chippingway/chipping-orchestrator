# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity usage for the steps emitted by one process invocation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from orchestrator.observability.usage import agy_events, event_stream, protocol, token_evidence

if TYPE_CHECKING:
    from orchestrator.observability.usage.metrics import UsageMetrics

# The counters a completed step's usage is read for, each under its own name.
_COUNTERS = (protocol.INPUT_TOKENS, protocol.OUTPUT_TOKENS, protocol.CACHE_READ_TOKENS)


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
) -> list[dict[str, int]]:
    """The counts each completed step's usage reports, by counter; a counter it reports no count for has no key."""
    # Terminal usage includes earlier conversation turns on a resume. Only
    # the steps emitted by this invocation belong in its per-run counters.
    return [
        token_evidence.reported_counts({
            counter: token_evidence.reported_count(step[protocol.USAGE].get(counter)) for counter in _COUNTERS
        })
        for step in completed_steps(events)
        if isinstance(step.get(protocol.USAGE), dict)
    ]


def apply_usage(
    events: list[dict[str, Any]],
    metrics: UsageMetrics,
    fallback_model: str | None,
) -> None:
    records = usage_records(events)
    metrics.input_tokens = sum(row.get(protocol.INPUT_TOKENS, 0) for row in records)
    metrics.output_tokens = sum(row.get(protocol.OUTPUT_TOKENS, 0) for row in records)
    metrics.cache_read_tokens = sum(row.get(protocol.CACHE_READ_TOKENS, 0) for row in records)
    # Nothing established yet says whether a step's cache reads are part of
    # its input count, so a run that read from cache beside it has no total.
    metrics.token_evidence = token_evidence.TokenEvidence.reporting(
        (counter for row in records for counter in row),
        token_evidence.UNKNOWN,
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
    # The CLI prints no USD amount, and nothing prices its usage yet.
    metrics.apply_cost(event_stream.select_cost(None, None, bool(records)))
