# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A Codex native `token_count` usage block read into counters: one request's own, or the thread's running sum.

codex-cli 0.167.1 appends an `event_msg` `token_count` line to its session log as each request settles, and its
`info` carries the same six counters twice: `last_token_usage`, the usage of the request that just settled, and
`total_token_usage`, the thread's running sum of every request it ever made -- every earlier invocation of a resumed
session included. `input_tokens` is a request's whole input, holding its cache reads (`cached_input_tokens`) and its
cache writes (`cache_write_input_tokens`); `output_tokens` holds `reasoning_output_tokens`; and `total_tokens` is the
input plus the output. Only those six are read off a block; nothing else of a line is.

The cache-write count is the CLI's flat field, which it prints as zero where a response reported no write count at
all: a raw zero is kept in `raw` as reported, but it establishes neither that nothing was written nor any lifetime, so
the normalized cache writes are unknown there, and no lifetime split is ever reported.

A request's own counters become a sample; the running sum is a checkpoint, never a request. Each request advances the
running sum by exactly its own counters, moving at least one of them -- a request always has input -- which is what
proves a line a new request rather than a repeat of the last one: a repeat leaves the sum where it was on a counter its
request moves -- a sum reporting none of those shows no such thing -- and counters that stay at zero agree with any
report. A sum never shrinks, so one holding less of a counter than the earlier sums and requests establish
contradicts them, whether or not the request reports that counter. Nothing here derives a request, or a compaction,
from the difference between two sums.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import (
    protocol,
    request_coverage as coverage,
    request_models,
    request_normalization as normalization,
    request_scan,
)
from orchestrator.observability.usage.request_normalization import Reading

CACHE_WRITES = "cache_write_input_tokens"
REASONING_FLAG = "last_usage_includes_reasoning"
CONTEXT_WINDOW = "model_context_window"
LAST_USAGE = "last_token_usage"
RUNNING_SUM = "total_token_usage"
# The counters a block is read for, each under the provider-neutral counter it normalizes as.
COUNTERS = MappingProxyType({
    protocol.INPUT_TOKENS: normalization.INPUT,
    "cached_input_tokens": normalization.CACHE_READ,
    CACHE_WRITES: normalization.CACHE_WRITE,
    protocol.OUTPUT_TOKENS: normalization.OUTPUT,
    "reasoning_output_tokens": normalization.REASONING,
    "total_tokens": normalization.SOURCE_TOTAL,
})
_SOURCE_TOTAL = "total_tokens"
# The normalized fields a block's own arithmetic can contradict, by the source counter each stands for: a total that is
# not its input plus its output, reasoning beyond its output, and cache reads and writes beyond the input holding them.
_RELATED = MappingProxyType({
    normalization.SOURCE_TOTAL_TOKENS: _SOURCE_TOTAL,
    normalization.REASONING_TOKENS: "reasoning_output_tokens",
    normalization.CACHE_READ_TOKENS: "cached_input_tokens",
    normalization.CACHE_WRITE_TOKENS: CACHE_WRITES,
})
# What a thread's running sum stands at before its first request: nothing at all.
_NOTHING = Reading(0, normalization.OBSERVED)
# How far a counter moved where it did not move by the request's own count of it.
_MISMATCH = -1


@dataclass(frozen=True)
class Counters:
    """The counters one block reported, by source counter: a count, or the evidence of why it is none."""

    readings: Mapping[str, Reading]

    @classmethod
    def of(cls, block: Any) -> Counters | None:
        """The counters `block` reports; None where it is no object or names none of them."""
        if not isinstance(block, dict):
            return None
        readings = {
            counter: Reading.of(block[counter])
            for counter in COUNTERS
            if block.get(counter) is not None
        }
        return cls(MappingProxyType(readings)) if readings else None

    @property
    def raw(self) -> dict[str, int]:
        """The whole counts the block reported, a negative one included, as the sample's `raw` keeps them."""
        return {
            counter: reading.count
            for counter, reading in self.readings.items()
            if reading.count is not None
        }

    def normalized(self) -> normalization.NormalizedUsage:
        """The block read under the Codex profile, a raw cache-write zero establishing no write count."""
        neutral = {COUNTERS[counter]: reading for counter, reading in self.readings.items()}
        if neutral.get(normalization.CACHE_WRITE) == _NOTHING:
            neutral[normalization.CACHE_WRITE] = Reading()
        return normalization.normalize(protocol.CODEX, neutral)

    def repeats(self, previous: Counters | None, moving: Collection[str]) -> bool:
        """Whether this running sum is the one `previous` already reported -- nothing at all, where none was -- beside a
        request it shows did not move it, the request reporting the counters in `moving` above zero.

        A request would have moved the sum by every counter it moves, so a sum staying where it was on one of those is
        a repeat; but one reporting no count of any of them shows nothing of the kind, however its other counters stay,
        and proves no repeat.
        """
        shown = {counter for counter, reading in self.readings.items() if reading.known}
        if moving and shown.isdisjoint(moving):
            return False
        if previous is not None:
            return self.readings == previous.readings
        return all(reading == _NOTHING for reading in self.readings.values())

    def advanced_by(self, previous: Counters | None, request: Counters, floor: Mapping[str, int]) -> bool:
        """Whether this running sum is `previous` advanced by exactly `request`'s own counters, and moved at all.

        Every counter all three report a count of is held to it, and at least one of those has to move by a count
        above zero: counters that stay at zero beside it prove nothing new happened, so a report the sum's moving
        counters cannot be compared on -- an earlier sum left unusable -- is no proven request. A counter any of the
        three reports no count of -- invalid, or left out -- is no evidence either way, so the request it belongs to
        keeps its own evidence for it rather than being refused for it -- unless the sum cannot hold the least its
        branch's earlier reports establish it holds, `floor`, beside the request's own count where it reports one: a
        running sum never shrinks, so one below that least contradicts them, whatever the request leaves out. That
        least is the whole number the reports add up to, never read again as a count one report gave, so it holds the
        sum however far past the digits a reported count may have it has grown.
        """
        established = {
            counter: Reading(count, normalization.OBSERVED)
            for counter, count in floor.items()
        }
        moves = [self._move(counter, previous, request, established) for counter in self.readings]
        compared = [move for move in moves if move is not None]
        if not compared or _MISMATCH in compared:
            return False
        return max(compared) > 0

    def evidence(self) -> dict[str, str]:
        """The state of each counter that is no usable count, or that the block's own arithmetic contradicts."""
        fields = self.normalized().fields
        found = {
            counter: normalization.CONFLICTING
            for field_name, counter in _RELATED.items()
            if fields[field_name].state == normalization.CONFLICTING
        }
        found.update(
            (counter, reading.state)
            for counter, reading in self.readings.items()
            if not reading.known
        )
        return found

    def _move(
        self,
        counter: str,
        previous: Counters | None,
        request: Counters,
        floor: Mapping[str, Reading],
    ) -> int | None:
        """How far one counter of this sum moved past `previous`'s by `request`'s own count of it.

        That count where it moved by exactly it, -1 where it moved otherwise, and None where this sum reports no count
        of it. Where `previous` or the request reports none, the move is unknown, but a sum adds up every request it
        holds and never shrinks, so one smaller than the least the earlier reports establish it holds -- beside the
        request's own count, where it reports one -- still contradicts it, as it does a move by exactly the request.
        """
        before = _NOTHING if previous is None else previous.readings.get(counter, Reading())
        own = request.readings.get(counter, Reading())
        total = self.readings[counter]
        if not total.known:
            return None
        held = Reading.at_least((own, floor.get(counter, _NOTHING)))
        if before.known and own.known:
            moved = total == Reading.summed((before, own))
            return (own.count or 0) if moved and not held.exceeds(total) else _MISMATCH
        return _MISMATCH if held.exceeds(total) else None


def checkpoint(
    kind: str,
    position: int,
    running_sum: Counters,
    conversation_id: str | None,
    gaps: Counter[str],
) -> request_models.UsageCheckpoint:
    """A thread's running sum as a checkpoint of the whole conversation it spans, never a request.

    A counter it reports no usable count of, or its own arithmetic contradicts, is a gap in `gaps` as well as its
    evidence, so a collection keeping it never reads as whole.
    """
    evidence = running_sum.evidence()
    gaps.update(coverage.evidence_gaps(evidence.values()))
    return request_models.UsageCheckpoint(
        kind=kind,
        scope=request_models.CONVERSATION_SCOPE,
        position=position,
        raw=MappingProxyType(running_sum.raw),
        conversation_id=conversation_id,
        evidence=MappingProxyType(evidence),
    )


def attribution(
    model: str | None,
    child: bool,
    fallback_model: str | None,
    known_capacity: int | None,
    version: str | None,
) -> request_models.RequestAttribution:
    """The model a request ran on and how that is established, beside the context capacity its report gives.

    `model` is the one the request's branch runs on as its last `turn_context` left it -- `REFUSED` where that named a
    model this collection refused. A named model is the request's; the thread, where none was named, falls back to
    the configured model; a child turn, or a branch whose last model was refused, runs on none this log establishes.
    """
    if model:
        return request_models.RequestAttribution(
            model, request_models.STREAM_MODEL, known_capacity, version,
        )
    if model is None and not child and fallback_model:
        return request_models.RequestAttribution(
            fallback_model, request_models.CONFIGURED_FALLBACK, known_capacity, version,
        )
    unknown = child or model == request_scan.REFUSED
    source = request_models.UNESTABLISHED if unknown else request_models.UNAVAILABLE
    return request_models.RequestAttribution(None, source, known_capacity, version)


def usage_gaps(
    token_info: dict[str, Any],
    running: Counters | None = None,
    after_compaction: bool = False,
    floor: Mapping[str, int] | None = None,
) -> frozenset[str]:
    """The gaps the request usage a report carries leaves where no sample is made of it.

    A block naming no counter is malformed usage, a counter it reports as no whole count an invalid one, and a part
    exceeding its whole, a total its parts contradict, or a count past the one the `running` sum beside it reports --
    which every request it sums, this one included, adds to -- a contradiction. So is a `running` sum holding less of a
    counter than the least its branch's earlier reports establish it holds, its `floor`, since a running sum never
    shrinks. The one total held neither to its parts nor to the running sum is the context estimate the CLI follows a
    compaction with: a total beside parts that are all zero, `after_compaction`.
    """
    own = Counters.of(token_info.get(LAST_USAGE))
    if own is None:
        return frozenset((coverage.MALFORMED_USAGE,))
    evidence = own.evidence()
    parts = dict(own.readings)
    total = parts.pop(_SOURCE_TOTAL, Reading())
    # The context estimate reports a total beside parts that are all zero, a total no request of the sum's.
    if after_compaction and total.known and set(parts.values()) <= {_NOTHING}:
        evidence.pop(_SOURCE_TOTAL, None)
        own = Counters(MappingProxyType(parts))
    gaps = set(coverage.evidence_gaps(evidence.values()))
    if running is not None and _outgrows(own, running, floor or {}):
        gaps.add(coverage.CONFLICTING_COUNTERS)
    return frozenset(gaps)


def detached_gaps(token_info: Any, metadata: request_scan.Metadata) -> frozenset[str]:
    """The gaps a report no branch takes leaves: one no record places among overlapping turns, one of a child turn
    naming no id, or one past a correlation bound.

    No sample is made of it and no running sum kept, but its evidence is judged as any report's: the metadata beside
    it, its running sum, and its request usage against both its own parts and that sum.
    """
    if not isinstance(token_info, dict):
        return frozenset((coverage.MALFORMED_USAGE,))
    report_metadata(token_info, metadata)
    running = Counters.of(token_info.get(RUNNING_SUM))
    found = set(usage_gaps(token_info, running))
    if running is None:
        found.add(coverage.MALFORMED_USAGE)
    else:
        found.update(coverage.evidence_gaps(running.evidence().values()))
    return frozenset(found)


def report_metadata(
    token_info: dict[str, Any],
    metadata: request_scan.Metadata,
) -> tuple[int | None, MappingProxyType[str, bool] | None]:
    """The context capacity and the reasoning flag a report gives beside its usage.

    A context window reported as no whole count, and a flag that is no boolean, are malformed metadata, counted into
    `metadata`; one left out is unknown, a limitation of the source rather than a gap. Whether `last_token_usage`
    counts the reasoning is the CLI's own statement, kept as it gave it: the reasoning count is read as a part of the
    output either way, never added to it.
    """
    window = token_info.get(CONTEXT_WINDOW)
    capacity = Reading() if window is None else Reading.of(window)
    flag = token_info.get(REASONING_FLAG)
    flags = MappingProxyType({REASONING_FLAG: flag}) if isinstance(flag, bool) else None
    metadata.malformed += window is not None and not capacity.known
    metadata.malformed += flag is not None and flags is None
    return capacity.count if capacity.known else None, flags


def _outgrows(own: Counters, running: Counters, floor: Mapping[str, int]) -> bool:
    """Whether a running sum holds less of a counter than the request beside it reports, or than `floor` establishes.

    The floor is compared as the whole number it is, past the digits a reported count may have as much as within them.
    """
    for counter, whole in running.readings.items():
        part = Reading.at_least((own.readings.get(counter, Reading()),))
        least = Reading(floor.get(counter, 0), normalization.OBSERVED)
        if whole.known and (part.exceeds(whole) or least.exceeds(whole)):
            return True
    return False
