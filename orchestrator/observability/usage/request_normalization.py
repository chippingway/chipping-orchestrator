# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The common counters one request's usage is normalized into, whichever provider reported it.

Providers spell a request's usage three ways. Codex's input already holds the cache reads it served
(`cached_tokens` is a part of it); Claude counts ordinary input apart from both its cache reads and its cache writes,
and reports each write twice -- in aggregate and split by lifetime; Antigravity counts ordinary input apart from its
cache reads and reports no cache writes. A `Profile` states which of those a provider is, and `normalize` reads one
request's raw counters into the same fields for all three: `context_input_tokens`, every token the request's context
held -- the input, plus the cache reads beside it where the input leaves them out, plus on Claude each cache write
once, its aggregate or its lifetime split but never both -- `output_tokens`, the cache breakdown,
`reasoning_tokens`, a subset of the output on every profile, and `total_tokens`, the context input plus the output.
The provider's own total stays apart as `source_total_tokens`: the common total is never derived from it.

Every field carries its evidence. A field the source reported a usable count for is `observed`; one it reported
nothing for is `missing`, never a zero; one whose report no count can be -- negative, a fraction, a boolean, a word,
or a string no exact whole number reads as -- is `invalid`; one two reports of the same request disagree on, or one
contradicting the counters it is a part of -- Codex's cache reads and writes together exceeding the input that holds
them included -- is `conflicting`; and one the profile has no counter for at all is `unsupported`. A derived field is
established only where each of its parts is observed, and otherwise takes the weakest evidence among them, so nothing
missing, invalid, or contradictory adds up to a count.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import protocol

OBSERVED = "observed"
UNSUPPORTED = "unsupported"
MISSING = "missing"
INVALID = "invalid"
CONFLICTING = "conflicting"
# From the strongest evidence to the weakest; a derived field takes the weakest of its parts.
_STRENGTH = (OBSERVED, UNSUPPORTED, MISSING, INVALID, CONFLICTING)

# The provider-neutral raw counters an adapter reads one request's usage into.
INPUT = protocol.INPUT
OUTPUT = protocol.OUTPUT
CACHE_READ = protocol.CACHE_READ
CACHE_WRITE = "cache_write"
CACHE_WRITE_FIVE_MIN = protocol.CACHE_WRITE_FIVE_MIN
CACHE_WRITE_ONE_HOUR = protocol.CACHE_WRITE_ONE_HOUR
REASONING = "reasoning"
SOURCE_TOTAL = "source_total"
_LIFETIMES = (CACHE_WRITE_FIVE_MIN, CACHE_WRITE_ONE_HOUR)
# The most digits a string may spell a count in; a longer number is no token count, and is never expanded into one.
_MAX_COUNT_DIGITS = 30
_MAX_COUNT = 10 ** _MAX_COUNT_DIGITS

# The normalized fields, each serialized under this name.
CONTEXT_INPUT_TOKENS = "context_input_tokens"
OUTPUT_TOKENS = protocol.OUTPUT_TOKENS
CACHE_READ_TOKENS = protocol.CACHE_READ_TOKENS
CACHE_WRITE_TOKENS = protocol.CACHE_WRITE_TOKENS
CACHE_WRITE_LIFETIMES = "cache_write_lifetimes"
REASONING_TOKENS = "reasoning_tokens"
TOTAL_TOKENS = "total_tokens"
SOURCE_TOTAL_TOKENS = "source_total_tokens"
OVERLAP = "overlap"
EVIDENCE = "evidence"


@dataclass(frozen=True)
class Reading:
    """One raw counter as a report gave it: the count, where it is one, and the evidence it is."""

    count: int | None = None
    state: str = MISSING

    @classmethod
    def of(cls, raw: Any) -> Reading:
        """Read one reported field: nothing is missing, and a report no count can be is invalid.

        The value is judged before it is turned into a count. A whole, non-negative number -- or a string spelling
        one, read exactly rather than through a float, so no rounding makes a fraction whole or changes a large count
        -- is a count; a negative whole number keeps its number as raw evidence and is invalid; and a fraction, an
        infinite or NaN value, a boolean, a word, or a number of `_MAX_COUNT_DIGITS` digits or more -- reported as
        one or spelled -- is no count at all, never the zero or whole number truncating it would make, nor a count
        whose sums no record could write.
        """
        if raw is None:
            return cls()
        number = _reported_number(raw)
        if number is None or abs(number) >= _MAX_COUNT:
            return cls(state=INVALID)
        return cls(int(number), OBSERVED if number >= 0 else INVALID)

    @classmethod
    def summed(cls, parts: Iterable[Reading]) -> Reading:
        """The parts added up where every one is observed, otherwise the weakest evidence among them."""
        readings = tuple(parts)
        weakest = max((_STRENGTH.index(part.state) for part in readings), default=0)
        if weakest:
            return cls(state=_STRENGTH[weakest])
        return cls(sum(part.count or 0 for part in readings), OBSERVED)

    @property
    def known(self) -> bool:
        return self.state == OBSERVED

    def within(self, whole: Reading) -> Reading:
        """This reading as a subset of `whole`: a part larger than the whole it sits in contradicts it."""
        if self.known and whole.known and self.exceeds(whole):
            return Reading(state=CONFLICTING)
        return self

    @classmethod
    def at_least(cls, parts: Iterable[Reading]) -> Reading:
        """What the known parts establish a whole is at least: their sum, any unknown part aside."""
        return cls.summed(part for part in parts if part.known)

    def exceeds(self, whole: Reading) -> bool:
        return (self.count or 0) > (whole.count or 0)

    def contradicted(self) -> Reading:
        """This reading as part of a contradiction: a count becomes conflicting, and any other evidence stays."""
        return Reading(state=CONFLICTING) if self.known else self


Readings = Mapping[str, Reading]


def _spelled_number(raw: str) -> int | None:
    """The whole number a string spells exactly, or None: a fraction, a non-number, or more digits than a count has."""
    try:
        number = Decimal(raw)
    except InvalidOperation:
        return None
    if not number.is_finite() or number.adjusted() >= _MAX_COUNT_DIGITS:
        return None
    return int(number) if number == number.to_integral_value() else None


def _reported_number(raw: Any) -> float | None:
    """The whole number one raw field reports, or None where it reports none."""
    if isinstance(raw, str):
        return _spelled_number(raw)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if isinstance(raw, int):
        return raw
    return raw if math.isfinite(raw) and raw.is_integer() else None


def _split_contradicts(aggregate: Reading, lifetimes: list[Reading], split: Reading) -> bool:
    """Whether a lifetime split contradicts its aggregate: summing to another count, or one lifetime exceeding it."""
    if not aggregate.known:
        return False
    if split.known:
        return split.count != aggregate.count
    return any(lifetime.known and lifetime.exceeds(aggregate) for lifetime in lifetimes)


@dataclass(frozen=True)
class NormalizedUsage:
    """One request's normalized fields, each with its evidence, and the overlap profile they were read under."""

    overlap: str
    fields: Mapping[str, Reading]
    lifetimes: Mapping[str, int]
    lifetimes_state: str

    def count(self, name: str) -> int | None:
        """The field's count where it is observed, None where its evidence establishes none."""
        reading = self.fields[name]
        return reading.count if reading.known else None

    def states(self) -> frozenset[str]:
        """Every evidence state one of the fields is in."""
        states = {reading.state for reading in self.fields.values()}
        return frozenset((*states, self.lifetimes_state))

    def to_dict(self) -> dict[str, Any]:
        counts: dict[str, Any] = {
            name: reading.count
            for name, reading in self.fields.items()
            if reading.known
        }
        if self.lifetimes:
            counts[CACHE_WRITE_LIFETIMES] = dict(self.lifetimes)
        evidence = {name: reading.state for name, reading in self.fields.items()}
        evidence[CACHE_WRITE_LIFETIMES] = self.lifetimes_state
        return {**counts, OVERLAP: self.overlap, EVIDENCE: evidence}


@dataclass(frozen=True)
class Profile:
    """What one provider's counters mean: how its input overlaps its cache, and which counters it reports at all.

    `context_parts` are the raw counters the context input is the sum of, `total_parts` the ones the provider's own
    total is the sum of, and `cache_within_input` whether the input already holds the cache reads and writes, so a
    source total disagreeing with its parts, or cache counts together larger than the input holding them, are a
    contradiction rather than a count.
    """

    overlap: str
    context_parts: tuple[str, ...]
    counters: frozenset[str]
    total_parts: tuple[str, ...] = ()
    cache_within_input: bool = False

    def reading(self, readings: Readings, name: str) -> Reading:
        if name not in self.counters:
            return Reading(state=UNSUPPORTED)
        return readings.get(name, Reading())

    def held(
        self,
        readings: Readings,
        cache_write: Reading,
        split: Reading,
    ) -> tuple[Reading, Reading, Reading]:
        """The cache reads, the writes, and their lifetime split, conflicting where the input cannot hold them.

        On a profile whose input holds its cache, it holds the reads and the writes at once, so it is their sum the
        input has to hold, not each alone. The writes are held at least at what is known of them: their settled count,
        or, where that is unknown, the lifetimes reported so far -- a lower bound that can already exceed the input
        while the writes themselves stay unknown. Each count taking part in the contradiction becomes conflicting.
        """
        cache_read = self.reading(readings, CACHE_READ)
        lifetimes = Reading.at_least(self.reading(readings, lifetime) for lifetime in _LIFETIMES)
        written = cache_write if cache_write.known else lifetimes
        held = Reading.at_least((cache_read, written))
        whole = self.reading(readings, INPUT)
        if not (self.cache_within_input and held.count and whole.known and held.exceeds(whole)):
            return cache_read, cache_write, split
        return (
            cache_read.contradicted(),
            Reading(state=CONFLICTING) if written.count else cache_write,
            Reading(state=CONFLICTING) if lifetimes.count else split,
        )

    def cache_writes(self, readings: Readings) -> tuple[Reading, Reading]:
        """The request's cache writes counted once, and its lifetime split, from the aggregate or the split.

        The aggregate is what is written where it is reported; the split stands in only where the aggregate is
        missing, and a split summing to anything but a reported aggregate, or one lifetime exceeding it, contradicts
        it, leaving both unknown.
        """
        aggregate = self.reading(readings, CACHE_WRITE)
        lifetimes = [self.reading(readings, lifetime) for lifetime in _LIFETIMES]
        split = Reading.summed(lifetimes)
        if aggregate.state == MISSING:
            return split, split
        if _split_contradicts(aggregate, lifetimes, split):
            contradiction = Reading(state=CONFLICTING)
            return contradiction, contradiction
        return aggregate, split

    def source_total(self, readings: Readings) -> Reading:
        total = self.reading(readings, SOURCE_TOTAL)
        parts = Reading.summed(self.reading(readings, part) for part in self.total_parts)
        if self.total_parts and total.known and parts.known and total.count != parts.count:
            return Reading(state=CONFLICTING)
        return total


    def lifetimes(self, readings: Readings, split: Reading) -> MappingProxyType[str, int]:
        """The cache writes by lifetime, where the split establishes them."""
        if not split.known:
            return MappingProxyType({})
        return MappingProxyType({lifetime: readings[lifetime].count or 0 for lifetime in _LIFETIMES})

    def fields(self, readings: Readings, cache_read: Reading, cache_write: Reading) -> MappingProxyType[str, Reading]:
        """The normalized fields: the context input is the profile's context parts, its cache writes counted once."""
        context = Reading.summed(
            cache_write if part == CACHE_WRITE else self.reading(readings, part)
            for part in self.context_parts
        )
        output = self.reading(readings, OUTPUT)
        return MappingProxyType({
            CONTEXT_INPUT_TOKENS: context,
            OUTPUT_TOKENS: output,
            CACHE_READ_TOKENS: cache_read,
            CACHE_WRITE_TOKENS: cache_write,
            REASONING_TOKENS: self.reading(readings, REASONING).within(output),
            TOTAL_TOKENS: Reading.summed((context, output)),
            SOURCE_TOTAL_TOKENS: self.source_total(readings),
        })

    def normalized(self, readings: Readings) -> NormalizedUsage:
        cache_write, split = self.cache_writes(readings)
        cache_read, cache_write, split = self.held(readings, cache_write, split)
        return NormalizedUsage(
            overlap=self.overlap,
            fields=self.fields(readings, cache_read, cache_write),
            lifetimes=self.lifetimes(readings, split),
            lifetimes_state=split.state,
        )


_EVERY_CACHE_COUNTER = frozenset((CACHE_READ, CACHE_WRITE, CACHE_WRITE_FIVE_MIN, CACHE_WRITE_ONE_HOUR))

PROFILES = MappingProxyType({
    # The input holds the cache reads (and any cache writes) it was served, so it is the context input alone.
    protocol.CODEX: Profile(
        "input-includes-cache",
        (INPUT,),
        frozenset((INPUT, OUTPUT, REASONING, SOURCE_TOTAL, *_EVERY_CACHE_COUNTER)),
        (INPUT, OUTPUT),
        cache_within_input=True,
    ),
    # Ordinary input, cache reads, and cache writes are three classes; each write is counted once.
    protocol.CLAUDE: Profile(
        "input-excludes-cache",
        (INPUT, CACHE_READ, CACHE_WRITE),
        frozenset((INPUT, OUTPUT, *_EVERY_CACHE_COUNTER)),
    ),
    # Ordinary input and cache reads are two classes, and no cache write is reported at all.
    protocol.AGY: Profile(
        "input-excludes-cache-reads",
        (INPUT, CACHE_READ),
        frozenset((INPUT, OUTPUT, CACHE_READ, REASONING, SOURCE_TOTAL)),
        (INPUT, OUTPUT),
    ),
})


def normalize(provider: str, readings: Readings) -> NormalizedUsage:
    """Read one request's raw counters under `provider`'s profile into the common fields and their evidence."""
    return PROFILES[provider].normalized(readings)
