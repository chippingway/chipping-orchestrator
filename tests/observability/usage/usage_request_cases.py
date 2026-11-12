# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One Antigravity stream collected into its serialized request usage, and the parts a test reads back.

The request tests read the field as a record carries it -- `RequestUsage.to_dict()` -- so the keys below are the
serialized format they pin, named once here rather than spelled out in every module.
"""

import json
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import protocol, trajectory
from tests.support import agy_stream as stream

COVERAGE = "coverage"
SAMPLES = "samples"
MARKERS = "markers"
CHECKPOINTS = "checkpoints"
RAW = "raw"
STATUS = "status"
REASONS = "reasons"
EVIDENCE = "evidence"
MODEL = "model"
MODEL_SOURCE = "model_source"
STEP_INDEX = "step_index"
CONVERSATION_ID = "conversation_id"
# Ten to the thirtieth: the first count with more digits than any token count has.
PAST_ANY_COUNT = 1_000_000_000_000_000_000_000_000_000_000
# The largest count the JSON decoder accepts, beside one cache read: a context input one digit past what a record could
# write, were it ever derived. The model is one no price applies to, so the run accounting does not price it.
_LARGEST_COUNT = int("9" * sys.get_int_max_str_digits())
# A line the JSON decoder refuses although it parses: a number past the interpreter's digit limit.
_REFUSED_DIGITS = "1" * (sys.get_int_max_str_digits() + 1)
REFUSED_LINE = f'{{"unrelated": {_REFUSED_DIGITS}}}'
_HUGE_USAGE = MappingProxyType({protocol.INPUT_TOKENS: _LARGEST_COUNT, protocol.CACHE_READ_TOKENS: 1})
HUGE_STDOUT = "\n".join((
    json.dumps({"event": "init", CONVERSATION_ID: stream.SESSION_ID, "init": {MODEL: "unpriced-model"}}),
    stream.step(1, usage={**_HUGE_USAGE, protocol.OUTPUT_TOKENS: 0}),
    stream.terminal(),
))

Entries = Iterable[Mapping[str, Any]]


@dataclass(frozen=True)
class Collected:
    """The request usage one stdout serialized as, read part by part."""

    serialized: dict[str, Any]

    @property
    def samples(self) -> list[dict[str, Any]]:
        return self.serialized.get(SAMPLES, [])

    @property
    def markers(self) -> list[dict[str, Any]]:
        return self.serialized.get(MARKERS, [])

    @property
    def checkpoints(self) -> list[dict[str, Any]]:
        return self.serialized.get(CHECKPOINTS, [])

    @property
    def coverage(self) -> dict[str, Any]:
        return self.serialized[COVERAGE]

    @property
    def reasons(self) -> dict[str, int]:
        return self.coverage[REASONS]

    @property
    def status(self) -> str:
        return self.coverage[STATUS]


def collected(*lines: str, fallback_model: str | None = None) -> Collected:
    """The request usage one Antigravity stdout of `lines` serializes as."""
    usage = trajectory.parse_agent_request_usage(protocol.AGY, "\n".join(lines), fallback_model)
    return Collected(usage.to_dict())


def picked(mapping: Mapping[str, Any], *names: str) -> tuple[Any, ...]:
    """The values `mapping` holds under `names`, None for a name it leaves out."""
    return tuple(mapping.get(name) for name in names)


def sums(entries: Entries, counters: Iterable[str]) -> list[int]:
    """Each raw counter of `counters` added up over `entries`."""
    kept = list(entries)
    return [sum(entry[RAW][counter] for entry in kept) for counter in counters]


def column(entries: Entries, name: str) -> list[Any]:
    return [entry.get(name) for entry in entries]
