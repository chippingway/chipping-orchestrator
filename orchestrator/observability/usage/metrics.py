# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Usage-metric model and the provider parser entry points over it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from orchestrator.observability.usage import (
    agy_summary,
    claude_settlement,
    claude_summary,
    codex_summary,
    cost_evidence as usage_cost,
    event_stream,
    protocol,
    token_evidence as usage_tokens,
)

if TYPE_CHECKING:
    from orchestrator.observability.usage.price_catalogue import UsageSpan


@dataclass
class UsageMetrics:
    """Structured usage extracted from one agent run's JSONL stdout.

    The raw counters and the `cost_usd` / `cost_source` pair keep their meaning; `cost_evidence` and
    `token_evidence` state what they mean together. A parser always fills both, so a metrics object holding neither
    was built with no evidence and reads back as unknown rather than as any provider's semantics.
    """

    backend: str
    models: tuple[str, ...] = ()
    turns: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: float | None = None
    cost_source: str = usage_cost.NO_USAGE_SOURCE
    cost_evidence: usage_cost.CostEvidence | None = None
    token_evidence: usage_tokens.TokenEvidence | None = None

    def apply_cost(self, cost: usage_cost.CostEvidence) -> None:
        """Record one run's selected cost, its `cost_usd` and `cost_source` read off the same evidence."""
        self.cost_evidence = cost
        self.cost_usd = cost.complete_usd
        self.cost_source = cost.cost_source

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "models": list(self.models),
            "turns": self.turns,
            protocol.INPUT_TOKENS: self.input_tokens,
            protocol.OUTPUT_TOKENS: self.output_tokens,
            protocol.CACHED_TOKENS: self.cached_tokens,
            protocol.CACHE_READ_TOKENS: self.cache_read_tokens,
            protocol.CACHE_WRITE_TOKENS: self.cache_write_tokens,
            usage_cost.COST_USD: self.cost_usd,
            "cost_source": self.cost_source,
            usage_cost.COST_EVIDENCE: None if self.cost_evidence is None else self.cost_evidence.to_dict(),
            usage_tokens.TOKEN_EVIDENCE: None if self.token_evidence is None else self.token_evidence.to_dict(),
        }


def parse_claude_usage(stdout: str) -> UsageMetrics:
    """Extract usage and cost from a Claude stream-json run."""
    events = event_stream.iter_events(stdout)
    metrics = UsageMetrics(backend=protocol.CLAUDE)
    records = claude_settlement.claude_usage_records(events)
    aggregate = claude_summary.aggregate_by_model(records)
    aggregate.apply_tokens(metrics)
    metrics.apply_cost(
        event_stream.select_cost(
            event_stream.find_last_reported_cost(events),
            claude_summary.estimate_total(records),
            bool(records),
        ),
    )
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
    span: UsageSpan | None = None,
) -> UsageMetrics:
    """Dispatch usage parsing by agent backend.

    `span` is when the run spent its usage; an Antigravity estimate needs it to find the dated Gemini row in effect,
    and without one the run is unpriced. The Claude and OpenAI rows carry no dates, so their estimates ignore it.
    """
    if backend == protocol.CLAUDE:
        return parse_claude_usage(stdout)
    if backend == protocol.CODEX:
        return parse_codex_usage(stdout, fallback_model=fallback_model)
    if backend == protocol.AGY:
        metrics = UsageMetrics(backend=backend)
        agy_summary.apply_usage(event_stream.iter_events(stdout), metrics, fallback_model, span)
        return metrics
    raise ValueError(
        f"unknown agent backend {backend!r}; expected 'claude', 'codex', or 'agy'",
    )
