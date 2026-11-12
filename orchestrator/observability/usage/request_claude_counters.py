# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The counters a Claude usage block is read for, as reported, and a block that holds none of them.

On Claude Code 2.1.295 a usage block counts ordinary input (`input_tokens`), cache reads
(`cache_read_input_tokens`), and cache writes (`cache_creation_input_tokens`) as three classes, reports the writes a
second time split by lifetime under its `cache_creation` object, and -- on a message's closing report -- breaks the
thinking inside its output out under `output_tokens_details`. Only those counters are read, each under the
provider-neutral counter it normalizes as: a lifetime or the thinking count is read off its object, or off the block
beside it where the object leaves it out, and a `cache_creation` or `output_tokens_details` that is no object at all
is an unsupported shape, so the counters it would hold are `invalid` rather than missing. The alternate spellings the
run accounting also accepts -- `prompt_tokens`, `completion_tokens`, `cached_input_tokens` -- are not read, so a
block spelled that way reports its counters as missing. Nothing else of a block is read.
"""

from __future__ import annotations

from collections.abc import Iterable
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import protocol, request_normalization as normalization
from orchestrator.observability.usage.request_normalization import Reading

THINKING_TOKENS = "thinking_tokens"
CACHE_WRITE_TOKENS = "cache_creation_input_tokens"
_FIVE_MINUTE = "ephemeral_5m_input_tokens"
_ONE_HOUR = "ephemeral_1h_input_tokens"
_LIFETIMES = (_FIVE_MINUTE, _ONE_HOUR)
_SPLIT = "cache_creation"
_DETAILS = "output_tokens_details"
COUNTERS = MappingProxyType({
    protocol.INPUT_TOKENS: normalization.INPUT,
    protocol.OUTPUT_TOKENS: normalization.OUTPUT,
    "cache_read_input_tokens": normalization.CACHE_READ,
    CACHE_WRITE_TOKENS: normalization.CACHE_WRITE,
    _FIVE_MINUTE: normalization.CACHE_WRITE_FIVE_MIN,
    _ONE_HOUR: normalization.CACHE_WRITE_ONE_HOUR,
    THINKING_TOKENS: normalization.REASONING,
})
# The counters a closing report settles: what a message generated, which only its end establishes.
SETTLED = frozenset((protocol.OUTPUT_TOKENS, THINKING_TOKENS))
_FLAT = (protocol.INPUT_TOKENS, protocol.OUTPUT_TOKENS, "cache_read_input_tokens", CACHE_WRITE_TOKENS)
# What a block names when it reports usage in a shape this collection reads at all.
_READABLE = frozenset((*COUNTERS, _SPLIT, _DETAILS))
_UNSUPPORTED_SHAPE = Reading(state=normalization.INVALID)

Readings = dict[str, Reading]


def read_counters(block: dict[str, Any], names: Iterable[str]) -> Readings:
    """The counters of `names` a block reports, as read; one it leaves out, or reports as null, has no key."""
    present = [name for name in names if block.get(name) is not None]
    return {name: Reading.of(block[name]) for name in present}


def _nested(
    usage: dict[str, Any],
    container: str,
    counters: tuple[str, ...],
) -> Readings:
    """The counters a nested object reports, each spelled beside it standing in where the object leaves it out."""
    nested = usage.get(container)
    if nested is None:
        nested = {}
    if not isinstance(nested, dict):
        return dict.fromkeys(counters, _UNSUPPORTED_SHAPE)
    return {**read_counters(usage, counters), **read_counters(nested, counters)}


def usage_readings(usage: dict[str, Any]) -> Readings:
    """The allowlisted counters one usage block reports, by source counter."""
    readings = read_counters(usage, _FLAT)
    readings.update(_nested(usage, _SPLIT, _LIFETIMES))
    readings.update(_nested(usage, _DETAILS, (THINKING_TOKENS,)))
    return readings


def malformed_usage(usage: Any) -> bool:
    """Whether a usage block holds nothing this collection can read: no object, or one naming no counter it reads.

    Such a block is usage the stream reported in a shape this collection cannot read, so it is a gap rather than an
    absence; an empty object reports nothing either way.
    """
    if usage is None:
        return False
    if not isinstance(usage, dict):
        return True
    return bool(usage) and _READABLE.isdisjoint(usage)


def raw_counts(readings: Readings) -> dict[str, int]:
    """The counts a report holds, by source counter, as decoded -- a negative one included."""
    counts = {name: reading.count for name, reading in readings.items()}
    return {name: count for name, count in counts.items() if count is not None}


def unusable(readings: Readings) -> dict[str, str]:
    """Each counter a report holds no usable count for, with the evidence it is instead."""
    states = {name: reading.state for name, reading in readings.items()}
    return {name: state for name, state in states.items() if state != normalization.OBSERVED}
