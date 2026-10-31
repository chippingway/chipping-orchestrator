# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude run aggregation, pricing, and turn counting.

A run's estimate is its usage rows priced one by one, each on `claude_requests.ClaudeUsageRow.estimate`, and summed:
pricing per-model totals would charge a request-tiered model's rate on a sum of requests that no single request
paid.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from orchestrator.observability.usage import (
    claude_requests,
    cost_evidence,
    event_stream,
    protocol,
    token_evidence,
)

if TYPE_CHECKING:
    from orchestrator.observability.usage.metrics import UsageMetrics

# The counter each token class of a usage row is serialized under.
COUNTER_NAMES = MappingProxyType({
    protocol.INPUT: protocol.INPUT_TOKENS,
    protocol.CACHE_WRITE_FIVE_MIN: protocol.CACHE_WRITE_TOKENS,
    protocol.CACHE_WRITE_ONE_HOUR: protocol.CACHE_WRITE_TOKENS,
    protocol.CACHE_WRITE_UNKNOWN_LIFETIME: protocol.CACHE_WRITE_TOKENS,
    protocol.CACHE_READ: protocol.CACHE_READ_TOKENS,
    protocol.OUTPUT: protocol.OUTPUT_TOKENS,
})


@dataclass
class ClaudeUsageAggregate:
    """Per-model token buckets with stable first-seen model order."""

    per_model: dict[str, protocol.TokenBucket] = field(default_factory=dict)
    model_order: list[str] = field(default_factory=list)
    reported_classes: set[str] = field(default_factory=set)

    def add(self, model: str, record: protocol.TokenBucket) -> None:
        bucket = self.per_model.setdefault(model, dict.fromkeys(COUNTER_NAMES, 0))
        if model not in self.model_order:
            self.model_order.append(model)
        self.reported_classes.update(record)
        for key, count in record.items():
            bucket[key] += count

    def apply_tokens(self, metrics: UsageMetrics) -> None:
        for bucket in self.per_model.values():
            metrics.input_tokens += bucket[protocol.INPUT]
            metrics.output_tokens += bucket[protocol.OUTPUT]
            metrics.cache_read_tokens += bucket[protocol.CACHE_READ]
            metrics.cache_write_tokens += claude_requests.cache_write_total(bucket)
        metrics.models = event_stream.dedup_models(self.model_order)
        metrics.token_evidence = token_evidence_of((self.reported_classes,))


def aggregate_by_model(
    records: Iterable[claude_requests.ClaudeUsageRow],
) -> ClaudeUsageAggregate:
    aggregate = ClaudeUsageAggregate()
    for usage_row in records:
        aggregate.add(usage_row.model, usage_row.counts)
    return aggregate


def estimate_total(
    records: Iterable[claude_requests.ClaudeUsageRow],
) -> cost_evidence.CostContribution | None:
    """Every row priced on its own and summed, or None when any row has no price: an estimate is never partial."""
    total: cost_evidence.CostContribution | None = None
    for usage_row in records:
        estimate = usage_row.estimate()
        if estimate is None:
            return None
        total = estimate if total is None else total.plus(estimate)
    return total


def token_evidence_of(records: Iterable[Iterable[str]]) -> token_evidence.TokenEvidence:
    """The counters the token classes of `records` were reported under, each record naming the classes it reports.

    A Claude usage block counts its ordinary input apart from the cache reads and writes, so the counters it carries
    never count a token twice. A run's counter is observed once any of the rows it sums reported it.
    """
    reported = (COUNTER_NAMES[token_class] for record in records for token_class in record)
    return token_evidence.TokenEvidence.reporting(reported, token_evidence.DISJOINT)


def turn_count(
    events: list[dict[str, Any]],
    records: list[claude_requests.ClaudeUsageRow],
) -> int | None:
    reported_turns: int | None = None
    for event in events:
        if event.get(protocol.TYPE) == protocol.RESULT_KEY:
            candidate = event.get("num_turns")
            if isinstance(candidate, (int, float)):
                reported_turns = int(candidate)
    if reported_turns is None and records:
        reported_turns = len(records)
    return reported_turns
