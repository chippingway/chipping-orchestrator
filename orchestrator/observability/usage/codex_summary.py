# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex cumulative usage pricing and run summary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

from orchestrator.observability.usage import (
    codex_rows,
    cost_evidence,
    event_stream,
    prices,
    protocol,
    token_evidence,
)

if TYPE_CHECKING:
    from orchestrator.observability.usage.metrics import UsageMetrics


TURN_COMPLETE_RE = re.compile(r"turn[_ -]?complete|turncomplete", re.IGNORECASE)

# The counter each token class of a usage record is serialized under.
COUNTER_NAMES = MappingProxyType({
    protocol.INPUT: protocol.INPUT_TOKENS,
    protocol.CACHED: protocol.CACHED_TOKENS,
    protocol.OUTPUT: protocol.OUTPUT_TOKENS,
})


@dataclass(frozen=True)
class CodexPrice:
    rates: protocol.RateMap
    usage: protocol.TokenBucket

    def estimate(self) -> float | None:
        input_cost = self._input_cost()
        if input_cost is None:
            return None
        output_cost = self.usage[protocol.OUTPUT] * self.rates[protocol.OUTPUT]
        return (input_cost + output_cost) / protocol.TOKENS_PER_MILLION

    def _input_cost(self) -> float | None:
        cached_tokens = self.usage[protocol.CACHED]
        cached_rate = self.rates.get(protocol.CACHED)
        if cached_tokens > 0 and cached_rate is None:
            return None
        uncached_tokens = max(self.usage[protocol.INPUT] - cached_tokens, 0)
        return uncached_tokens * self.rates[protocol.INPUT] + cached_tokens * (cached_rate or 0)


def estimate_cost(
    model: str,
    usage: protocol.TokenBucket,
) -> cost_evidence.CostContribution | None:
    row = prices.codex_row(model)
    billable_tokens = usage[protocol.INPUT] + usage[protocol.OUTPUT]
    if row is None or billable_tokens <= 0:
        return None
    amount = CodexPrice(row.rates_for_prompt(usage[protocol.INPUT]), usage).estimate()
    if amount is None:
        return None
    return cost_evidence.CostContribution(cost_evidence.OPENAI_API_ESTIMATE, amount, (row.verified_on,))


def reported_turn_count(events: list[dict[str, Any]]) -> int | None:
    reported: int | None = None
    for event in events:
        for payload in event_stream.walk_objects(event):
            turns_value = payload.get("num_turns")
            if isinstance(turns_value, (int, float)):
                reported = int(turns_value)
    return reported


def completed_turn_count(events: list[dict[str, Any]]) -> int | None:
    count = 0
    for event in events:
        event_type = event.get(protocol.TYPE)
        if isinstance(event_type, str) and TURN_COMPLETE_RE.search(event_type):
            count += 1
    return count or None


def turn_count(events: list[dict[str, Any]]) -> int | None:
    reported = reported_turn_count(events)
    if reported is not None:
        return reported
    return completed_turn_count(events)


def last_record_evidence(usage_events: list[protocol.CodexUsageEvent]) -> token_evidence.TokenEvidence:
    """The counters the last of `usage_events` reports a count for, its cached input sitting within its input."""
    if not usage_events:
        return token_evidence.TokenEvidence((), token_evidence.WITHIN_INPUT)
    last_record = usage_events[-1][1]
    return token_evidence.TokenEvidence.reporting(map(COUNTER_NAMES.get, last_record), token_evidence.WITHIN_INPUT)


@dataclass(frozen=True)
class CodexUsageSummary:
    """One run's cumulative usage: the records that counted tokens, the authoritative total, and what it observed.

    The total is the last record reporting any tokens. The observation is that record's, or -- when every record
    reports only zeros -- that of the last record reporting a count at all, since those zeros were reported rather
    than missing and a block reporting none says nothing of them. Its cached input is the part of its input count
    served from cache, so it sits within that count.
    """

    events: list[dict[str, Any]]
    usage_events: list[protocol.CodexUsageEvent]
    usage: protocol.TokenBucket
    model: str | None
    observed: token_evidence.TokenEvidence

    @classmethod
    def build(
        cls,
        events: list[dict[str, Any]],
        fallback_model: str | None,
    ) -> CodexUsageSummary:
        printed = codex_rows.codex_usage_events(events)
        usage_events = [usage_event for usage_event in printed if any(usage_event[1].values())]
        last_model, usage = codex_rows.last_codex_usage(usage_events)
        return cls(
            events=events,
            usage_events=usage_events,
            usage=usage,
            model=codex_rows.codex_select_model(events, last_model, fallback_model),
            observed=last_record_evidence(usage_events or [usage_event for usage_event in printed if usage_event[1]]),
        )

    def apply(self, metrics: UsageMetrics) -> None:
        metrics.input_tokens = self.usage[protocol.INPUT]
        metrics.cached_tokens = self.usage[protocol.CACHED]
        metrics.output_tokens = self.usage[protocol.OUTPUT]
        metrics.token_evidence = self.observed
        if self.model is not None:
            metrics.models = (self.model,)
        metrics.apply_cost(
            event_stream.select_cost(
                event_stream.find_last_reported_cost(self.events),
                estimate_cost(self.model or protocol.UNKNOWN, self.usage),
                bool(self.usage_events),
            ),
        )
        metrics.turns = turn_count(self.events)
