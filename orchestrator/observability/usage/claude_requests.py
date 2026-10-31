# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One Claude usage row: the counts it holds, the lifetime of each cache write, and the request it covers.

A usage block reports its cache writes twice: `cache_creation_input_tokens` is their aggregate, and the
`cache_creation` object splits it by lifetime into `ephemeral_5m_input_tokens` and `ephemeral_1h_input_tokens`, which
the API documents as summing to the aggregate. Each write counts once, under the lifetime the block reports for it,
so a write is never charged twice nor at another lifetime's rate. A write the block gives no lifetime counts under
an unknown one, which no catalogue row prices: the whole aggregate beside no split, and the part of it a partial split
leaves over. A lifetime field holding anything but a non-negative whole number -- a fraction, a non-finite number, a
string, a bool -- is no lifetime count, read before any coercion could round it into one. With no aggregate, a split
reporting both lifetimes is the whole write count, and one reporting a single lifetime counts those writes alone and
leaves the whole unknown. An explicit zero is a count like any other. The unknown-lifetime class is present exactly
when the block establishes its whole write count, zero where every write has its lifetime.

A split claiming more writes than the aggregate holds -- a zero aggregate included -- contradicts it, and counts that
cannot both be right establish neither the write count nor the request's prompt. The aggregate stays the observed
count, all of it under the unknown lifetime, and the row records the conflict apart from any token count
(`conflicting_writes`), so it has no price on any model, however small that aggregate is.

A row's scope says what its counts cover. A `message` row is one API message's usage block, so its input, cache
reads, and cache writes are that request's prompt, the size a request-tiered model's rates depend on. A
`handback-output` row holds only the output count of the message that closed a subagent, and a `result-total` row the
`result` frame's usage, a sum over the lead thread's requests: neither establishes any request's prompt. Each row is
priced on its own (`ClaudeUsageRow.estimate`), so the run aggregate and every turn price their rows on one path and
a run's estimate is its rows' estimates summed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from orchestrator.observability.usage import cost_evidence, prices, protocol, token_evidence

# A block's cache writes by lifetime, None for a lifetime it reports no count of, and whether its split contradicts
# its aggregate.
CacheWrites = tuple[dict[str, int | None], bool]

MESSAGE = "message"
HANDBACK_OUTPUT = "handback-output"
RESULT_TOTAL = "result-total"

CACHE_WRITE_CLASSES = (
    protocol.CACHE_WRITE_FIVE_MIN,
    protocol.CACHE_WRITE_ONE_HOUR,
    protocol.CACHE_WRITE_UNKNOWN_LIFETIME,
)
# Each lifetime's token class and the field the `cache_creation` split reports it under.
_LIFETIME_FIELDS = (
    (protocol.CACHE_WRITE_FIVE_MIN, "ephemeral_5m_input_tokens"),
    (protocol.CACHE_WRITE_ONE_HOUR, "ephemeral_1h_input_tokens"),
)
# A row establishes its request's prompt only when it reports all three parts of it.
_PROMPT_CLASSES = frozenset((protocol.INPUT, protocol.CACHE_READ, protocol.CACHE_WRITE_UNKNOWN_LIFETIME))


@dataclass(frozen=True)
class ClaudeUsageRow:
    """One usage row in stream order: its model, its counts by token class, and the scope those counts cover."""

    ordinal: int
    model: str
    counts: protocol.TokenBucket
    scope: str = MESSAGE
    conflicting_writes: bool = False

    @property
    def prompt_tokens(self) -> int | None:
        """The prompt of the request the row is, or None where it establishes none."""
        one_request = self.scope == MESSAGE and not self.conflicting_writes
        if not one_request or not _PROMPT_CLASSES <= self.counts.keys():
            return None
        output = self.counts.get(protocol.OUTPUT, 0)
        return sum(self.counts.values()) - output

    def with_output(self, output: int) -> ClaudeUsageRow:
        return replace(self, counts={**self.counts, protocol.OUTPUT: output})

    def estimate(self) -> cost_evidence.CostContribution | None:
        """The row priced on its own as an Anthropic API estimate, or None when nothing establishes its price."""
        if self.conflicting_writes:
            return None
        return prices.claude_estimate(self.model, self.counts, self.prompt_tokens)


def cache_writes(usage: dict[str, Any]) -> CacheWrites:
    """The cache writes one usage block reports, by lifetime, and whether its split contradicts its aggregate."""
    aggregate = token_evidence.reported_count(usage.get("cache_creation_input_tokens"))
    by_lifetime = _lifetime_counts(usage)
    attributed = sum(count or 0 for count in by_lifetime.values())
    if aggregate is None and None not in by_lifetime.values():
        aggregate = attributed
    if aggregate is None:
        return by_lifetime, False
    if attributed > aggregate:
        return {protocol.CACHE_WRITE_UNKNOWN_LIFETIME: aggregate}, True
    return {**by_lifetime, protocol.CACHE_WRITE_UNKNOWN_LIFETIME: aggregate - attributed}, False


def cache_write_total(counts: protocol.TokenBucket) -> int:
    """Every cache write a bucket counts, whatever its lifetime."""
    return sum(counts.get(token_class, 0) for token_class in CACHE_WRITE_CLASSES)


def _lifetime_counts(usage: dict[str, Any]) -> dict[str, int | None]:
    cache_creation = usage.get("cache_creation")
    split = cache_creation if isinstance(cache_creation, dict) else {}
    return {
        token_class: _lifetime_count(split.get(field_name), usage.get(field_name))
        for token_class, field_name in _LIFETIME_FIELDS
    }


def _lifetime_count(*spellings: Any) -> int | None:
    """The first nonzero whole count among a lifetime's spellings, zero if they hold only zeros, else None."""
    counts = [count for count in map(_whole_count, spellings) if count is not None]
    return next((count for count in counts if count), counts[0] if counts else None)


def _whole_count(raw: Any) -> int | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    # A float is a count only when it is a finite whole number: `is_integer` is false for a fraction, inf, and nan.
    if isinstance(raw, float) and not raw.is_integer():
        return None
    return int(raw) if raw >= 0 else None
