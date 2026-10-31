# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one Codex usage record establishes about the API requests it sums, and the estimate it is priced at.

`codex exec --json` prints usage on `turn.completed` alone, and on codex-cli 0.166.0 that block sums every API request
of the thread: each request of the turn, and on `exec resume` every request of the earlier invocations too. Its
`input_tokens` is the requests' whole input, `cached_input_tokens` the cache reads billed within it, and
`cache_write_input_tokens` the cache writes within it: the responses' `input_tokens_details.cache_write_tokens`
summed, their `cache_write_tokens_details` split by lifetime dropped, and printed as zero where a response reported
no write count at all. A record therefore never sizes one request. It bounds them, since none it sums has more input
than the whole.

A record's counts are by token class, a class it does not report having no key. Its input holds its cache reads and
its cache writes, the writes counted by lifetime -- 30-minute, 12-hour, or unknown -- and the unknown-lifetime class is
present exactly when the record establishes its whole write count. The CLI's flat field establishes it only when
positive, with every write of unknown lifetime: its zero is no evidence that nothing was written, and a negative count
is kept beside the others, so the record it contradicts prices nothing.

The estimate follows OpenAI's cache accounting
(https://developers.openai.com/api/docs/guides/prompt-caching#monitor-cache-performance). A model whose row publishes
cache-write rates -- GPT-5.6 and later, at 1.25x ordinary input for the 30-minute lifetime and 2.5x for 12 hours --
bills as ordinary input what is left of the input once its reads and writes are taken out, and each write once, at its
own lifetime's rate, never the aggregate again. A write of unknown lifetime finds no rate there, and a record not
establishing its whole write count cannot separate its ordinary input, so neither has a price. A model before GPT-5.6
charges a cache write nothing of its own, so there a write is ordinary input. Reads and writes beyond the input
contradict it, and a negative count is no count: neither prices on any model. A request-tiered row prices a record at
its base rates only where the record's input keeps every request at or under the tier's threshold; past it nothing
says which of the requests crossed, so the record has no price.
"""

from __future__ import annotations

from dataclasses import dataclass

from orchestrator.observability.usage import cost_evidence, prices, protocol

CACHE_WRITE_CLASSES = (
    protocol.CACHE_WRITE_THIRTY_MIN,
    protocol.CACHE_WRITE_TWELVE_HOUR,
    protocol.CACHE_WRITE_UNKNOWN_LIFETIME,
)
# A row publishing either rate charges each cache write at its lifetime's rate.
_LIFETIME_RATES = frozenset((protocol.CACHE_WRITE_THIRTY_MIN, protocol.CACHE_WRITE_TWELVE_HOUR))


@dataclass(frozen=True)
class CodexUsageRow:
    """One usage record: the model it is priced as and its counts by token class, summed over its requests."""

    model: str
    counts: protocol.TokenBucket

    @property
    def cache_writes(self) -> protocol.TokenBucket:
        """The record's cache writes by lifetime, a lifetime it reports no count of having no key."""
        reported = (token_class for token_class in CACHE_WRITE_CLASSES if token_class in self.counts)
        return {token_class: self.counts[token_class] for token_class in reported}

    @property
    def uncached_input(self) -> int:
        """The input left once the record's cache reads are taken out: its ordinary input and its cache writes."""
        reads = self.counts.get(protocol.CACHED, 0)
        return self.counts.get(protocol.INPUT, 0) - reads

    @property
    def ordinary_input(self) -> int:
        """The input left once the record's cache reads and every cache write it counts are taken out."""
        return self.uncached_input - sum(self.cache_writes.values())

    @property
    def consistent(self) -> bool:
        """Whether the counts can all be right: none negative, and the reads and writes no more than the input."""
        return min(self.ordinary_input, *self.counts.values()) >= 0

    def estimate(self) -> cost_evidence.CostContribution | None:
        """The record priced as an OpenAI API estimate, or None when nothing establishes its price."""
        row = prices.codex_row(self.model)
        if row is None:
            return None
        rates = row.rates_for_requests_within(self.counts.get(protocol.INPUT))
        if rates is None:
            return None
        billed = self.billed_counts(rates)
        amount = None if billed is None else prices.priced_amount(rates, billed)
        if amount is None:
            return None
        return cost_evidence.CostContribution(cost_evidence.OPENAI_API_ESTIMATE, amount, (row.verified_on,))

    def billed_counts(self, rates: protocol.RateMap) -> protocol.TokenBucket | None:
        """The record's tokens by the class `rates` bill each at, or None where its counts cannot establish them."""
        by_lifetime = not _LIFETIME_RATES.isdisjoint(rates)
        whole_writes = protocol.CACHE_WRITE_UNKNOWN_LIFETIME in self.counts
        if not self.consistent or (by_lifetime and not whole_writes):
            return None
        if by_lifetime:
            return {**self.counts, protocol.INPUT: self.ordinary_input}
        return {**_without_writes(self.counts), protocol.INPUT: self.uncached_input}


def _without_writes(counts: protocol.TokenBucket) -> protocol.TokenBucket:
    return {token_class: count for token_class, count in counts.items() if token_class not in CACHE_WRITE_CLASSES}
