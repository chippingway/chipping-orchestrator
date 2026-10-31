# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which token counters a run's stream evidences, whether its cache counters sit inside its input, and the total.

The raw counters stay exactly as each provider reports them, so what they mean together is stated beside them.
`observed` names the counters the stream's usage payloads reported a count for, an explicit zero included: a counter
it does not name is missing evidence, never a zero, even though the raw field reads `0` for it. The decoders keep that
apart by reading each field through `reported_count` / `first_count`, which answer None for a field no payload
reported, and keeping only the counts they answer (`reported_counts`). `cache_overlap` says how the cache counters
relate to the input counter: `disjoint` when each is a class of its own beside the input (Claude's cache reads and
writes), `within-input` when they count part of the input again (Codex's `cached_tokens`), and `unknown` when nothing
establishes either.

`non_overlapping_total` is the one way to add the counters up, and it answers only where that evidence permits: every
observed counter once, a cache counter left out only where it sits inside an input count that was observed. Beside an
observed input, a nonzero cache counter of unknown overlap leaves the total unknown rather than guessed either way.
`recorded_tokens` is the evidence a serialized record is read with: a record that states none is read with the counters
it carries and an unknown overlap.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.observability.usage import protocol

TOKEN_EVIDENCE = "token_evidence"
OBSERVED = "observed"
CACHE_OVERLAP = "cache_overlap"

DISJOINT = "disjoint"
WITHIN_INPUT = "within-input"
UNKNOWN = "unknown"

CACHE_COUNTERS = (protocol.CACHED_TOKENS, protocol.CACHE_READ_TOKENS, protocol.CACHE_WRITE_TOKENS)
COUNTERS = (protocol.INPUT_TOKENS, protocol.OUTPUT_TOKENS, *CACHE_COUNTERS)
_OVERLAPS = (DISJOINT, WITHIN_INPUT, UNKNOWN)


@dataclass(frozen=True)
class TokenEvidence:
    """The counters one stream evidenced, in counter order, and how its cache counters relate to its input."""

    observed: tuple[str, ...]
    cache_overlap: str

    @classmethod
    def from_dict(cls, raw: Any) -> TokenEvidence | None:
        """Read serialized evidence, or None when it is not evidence a current producer writes."""
        if not isinstance(raw, dict) or raw.get(CACHE_OVERLAP) not in _OVERLAPS:
            return None
        observed = raw.get(OBSERVED)
        if not isinstance(observed, list):
            return None
        known = tuple(counter for counter in COUNTERS if counter in observed)
        # Every entry has to be a distinct counter name for the two lengths to agree.
        if len(known) != len(observed):
            return None
        return cls(known, raw[CACHE_OVERLAP])

    @classmethod
    def reporting(cls, counters: Iterable[str], cache_overlap: str) -> TokenEvidence:
        """Evidence observing each of `counters`, the counters some usage payload of the stream reported."""
        reported = set(counters)
        return cls(tuple(counter for counter in COUNTERS if counter in reported), cache_overlap)

    def total(self, counts: Mapping[str, Any]) -> int | None:
        """The non-overlapping total of the observed counters in `counts`, or None where evidence cannot settle it."""
        observed = {counter: counts.get(counter) for counter in self.observed}
        if not all(is_count(count) for count in observed.values()):
            return None
        whole = sum(observed.values())
        cached = sum(observed.get(counter, 0) for counter in CACHE_COUNTERS)
        # Only an observed input count can hold a cache count a second time.
        if not cached or protocol.INPUT_TOKENS not in observed or self.cache_overlap == DISJOINT:
            return whole
        return whole - cached if self.cache_overlap == WITHIN_INPUT else None

    def to_dict(self) -> dict[str, Any]:
        return {OBSERVED: list(self.observed), CACHE_OVERLAP: self.cache_overlap}


def recorded_tokens(record: Mapping[str, Any]) -> TokenEvidence:
    """The token evidence one serialized usage record is read with.

    A record whose `token_evidence` is missing, or is not evidence a current producer writes, is read as observing the
    counters it carries, with a cache overlap nothing establishes: nothing is inferred from its backend or models.
    """
    evidence = TokenEvidence.from_dict(record.get(TOKEN_EVIDENCE))
    if evidence is not None:
        return evidence
    return TokenEvidence(tuple(counter for counter in COUNTERS if counter in record), UNKNOWN)


def non_overlapping_total(record: Mapping[str, Any]) -> int | None:
    """The token total one serialized usage record establishes, each token counted once, or None.

    A run that printed no usage observed nothing and totals zero; its empty `observed` list is what tells that zero
    apart from a counted one.
    """
    return recorded_tokens(record).total(record)


def reported_count(raw: Any) -> int | None:
    """The token count one raw usage field reports, or None when it reports none: absent, null, or not a number.

    An infinite or NaN value, a JSON number or a string spelling one, is no number a count can hold, so it reports
    none rather than stopping the whole stream's parse.
    """
    number = raw
    if isinstance(raw, str):
        try:
            number = float(raw)
        except ValueError:
            return None
    if isinstance(number, float):
        return int(number) if math.isfinite(number) else None
    return int(number) if isinstance(number, int) else None


def first_count(*raw_counts: Any) -> int | None:
    """The first nonzero count among one field's alternative spellings, zero if they report only zeros, else None."""
    reported = [count for count in map(reported_count, raw_counts) if count is not None]
    if not reported:
        return None
    return next((count for count in reported if count), 0)


def reported_counts(counts: Mapping[str, int | None]) -> dict[str, int]:
    """The counts a payload reported, by token class: a class it reported no count for has no key."""
    return {token_class: count for token_class, count in counts.items() if count is not None}


def is_count(raw: Any) -> bool:
    """Whether a serialized counter holds a count a total can add: a non-negative integer, never a bool or a string."""
    return isinstance(raw, int) and not isinstance(raw, bool) and raw >= 0
