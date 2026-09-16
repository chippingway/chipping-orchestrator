# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Usage-metric model and the provider parser entry points over it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from orchestrator.observability.usage import (
    agy_summary,
    claude_rows,
    claude_summary,
    codex_summary,
    event_stream,
    protocol,
)


@dataclass
class UsageMetrics:
    """Structured usage extracted from one agent run's JSONL stdout."""

    backend: str
    models: tuple[str, ...] = ()
    turns: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    cost_source: str = "no-usage"

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "models": list(self.models),
            "turns": self.turns,
            protocol.INPUT_TOKENS: self.input_tokens,
            protocol.OUTPUT_TOKENS: self.output_tokens,
            protocol.CACHED_TOKENS: self.cached_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_write_tokens": self.cache_write_tokens,
            "cost_usd": self.cost_usd,
            "cost_source": self.cost_source,
        }


def parse_claude_usage(stdout: str) -> UsageMetrics:
    """Extract usage and cost from a Claude stream-json run."""
    events = event_stream.iter_events(stdout)
    metrics = UsageMetrics(backend=protocol.CLAUDE)
    records = claude_rows.claude_usage_records(events)
    aggregate = claude_summary.aggregate_by_model(records)
    aggregate.apply_tokens(metrics)
    selected_cost = event_stream.select_cost(
        event_stream.find_last_reported_cost(events),
        claude_summary.estimate_total(aggregate.per_model),
        bool(records),
    )
    metrics.cost_usd = selected_cost[0]
    metrics.cost_source = selected_cost[1]
    metrics.turns = claude_summary.turn_count(events, records)
    return metrics


def parse_codex_usage(
    stdout: str,
    fallback_model: str | None = None,
) -> UsageMetrics:
    """Extract usage and cost from a Codex JSON run."""
    events = event_stream.iter_events(stdout)
    metrics = UsageMetrics(backend=protocol.CODEX)
    codex_summary.CodexUsageSummary.build(events, fallback_model).apply(metrics)
    return metrics


def parse_agent_usage(
    backend: str,
    stdout: str,
    *,
    fallback_model: str | None = None,
) -> UsageMetrics:
    """Dispatch usage parsing by agent backend."""
    if backend == protocol.CLAUDE:
        return parse_claude_usage(stdout)
    if backend == protocol.CODEX:
        return parse_codex_usage(stdout, fallback_model=fallback_model)
    if backend == protocol.AGY:
        metrics = UsageMetrics(backend=backend)
        agy_summary.apply_usage(event_stream.iter_events(stdout), metrics, fallback_model)
        return metrics
    raise ValueError(
        f"unknown agent backend {backend!r}; expected 'claude', 'codex', or 'agy'",
    )
