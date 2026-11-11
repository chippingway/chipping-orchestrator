# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One Antigravity step folded from every `step_update` frame the stream printed for it, and the usage it settled.

The CLI reports a step over as many frames as it takes and repeats a completed one, and a frame may carry only some
of a step's fields. A step is therefore folded field by field: a frame adds what it carries and never takes away what
an earlier one supplied, so a repeated or sparse completed frame keeps the usage the first completed frame reported.
Two completed frames reporting different counts for one counter contradict each other, and that counter is
`conflicting` rather than either count. Usage a frame carried before the step completed is kept apart and stands for
every counter no completed frame reported -- all of them where none did -- so a sparse completion never takes back
what an earlier frame supplied, and a request any of whose counters rests on such a frame is provisional rather than
final. Only the counters `COUNTERS` names are read off a usage block; nothing else of a frame -- its text delta, its
tool payload -- is.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, NamedTuple

from orchestrator.observability.usage import (
    agy_events,
    protocol,
    request_models,
    request_normalization as normalization,
)
from orchestrator.observability.usage.request_normalization import Reading
from orchestrator.observability.usage.request_scan import Metadata

# The counters a step's usage block is read for, each under the provider-neutral counter it normalizes as. On agy
# 1.4.10 `input_tokens` is ordinary input apart from `cache_read_tokens`, `thinking_tokens` sits inside
# `output_tokens`, and `total_tokens` is the input plus the output.
COUNTERS = MappingProxyType({
    protocol.INPUT_TOKENS: normalization.INPUT,
    protocol.OUTPUT_TOKENS: normalization.OUTPUT,
    "thinking_tokens": normalization.REASONING,
    protocol.CACHE_READ_TOKENS: normalization.CACHE_READ,
    "total_tokens": normalization.SOURCE_TOTAL,
})
# Steps that are generations, whose completion without usage is usage the stream did not report.
GENERATIONS = frozenset(("agent_response", "checkpoint"))
SETTLED_BY_COMPLETION = "completed-frame"
SETTLED_BEFORE_COMPLETION = "pre-completion-frame"
SETTLED_IN_PART_BEFORE_COMPLETION = "completed-and-pre-completion-frames"
_USER_INPUT = "user_input"
_DURATION = "duration_seconds"

StepKey = tuple[str | None, int]


class SettledUsage(NamedTuple):
    """The readings one step settled on, the status they have, and the report that settled them."""

    readings: dict[str, Reading]
    status: str
    settlement: str


def source_duration(raw: Any) -> float | None:
    """A frame's reported duration in seconds, where it is a finite, non-negative number a float holds."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    try:
        seconds = float(raw)
    except OverflowError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def usage_readings(frame: dict[str, Any]) -> dict[str, Reading] | None:
    """The counters one frame's usage block reports, by source counter; None where the frame carries no block."""
    usage = frame.get(protocol.USAGE)
    if not isinstance(usage, dict):
        return None
    return {
        counter: Reading.of(usage[counter])
        for counter in COUNTERS
        if usage.get(counter) is not None
    }


def unindexed_gap(frame: dict[str, Any], metadata: Metadata) -> bool:
    """Whether a frame naming no step index may hold a request no step can be folded under.

    Usage on it, readable or not, or a generation's step type, is a request the stream reported without the index a
    request is keyed by, so it is a gap rather than nothing. The step type is read as metadata, so a malformed one is a
    gap of its own rather than an error that would cost every other request of the stream.
    """
    if frame.get(protocol.USAGE) is not None:
        return True
    return metadata.text(frame.get(agy_events.STEP_TYPE)) in GENERATIONS


def raw_counts(readings: dict[str, Reading]) -> dict[str, int]:
    """The counts a usage block reported, by source counter, as decoded -- a negative one included."""
    return {
        counter: reading.count
        for counter, reading in readings.items()
        if reading.count is not None
    }


@dataclass
class StepFold:
    """Everything the stream said about one step, in the order it said it.

    `own_model` is the model an `init` of the step's own conversation named, and `process_model` the one the process's
    `init` named, each as in effect when the step's first frame arrived; which of them the step ran on is the
    conversation attribution's to decide.
    """

    key: StepKey
    own_model: str | None
    process_model: str | None
    kind: str | None = None
    settled_position: int | None = None
    duration: float | None = None
    tool: bool = False
    final: dict[str, Reading] = field(default_factory=dict)
    early: dict[str, Reading] | None = None

    @property
    def settled(self) -> bool:
        return self.settled_position is not None

    @property
    def unsettled_gap(self) -> bool:
        """Whether a step the stream never completed may have spent usage it never reported."""
        if self.settled or self.tool or self.kind == _USER_INPUT:
            return False
        return self.early is not None or self.kind in GENERATIONS

    @property
    def unreported_gap(self) -> bool:
        """Whether a completed generation reported no usage at all."""
        if not self.settled or self.kind not in GENERATIONS:
            return False
        return not self.final and self.early is None

    def absorb(self, position: int, frame: dict[str, Any], metadata: Metadata) -> None:
        self.tool = self.tool or agy_events.ToolLifecycle.is_tool_step(frame)
        self.kind = self.kind or metadata.text(frame.get(agy_events.STEP_TYPE))
        readings = usage_readings(frame)
        if frame.get(agy_events.STATE) == agy_events.DONE:
            self._complete(position, readings or {})
            self._timed(frame.get(_DURATION), metadata)
        elif readings and not self.settled:
            self.early = {**(self.early or {}), **readings}

    def usage(self) -> SettledUsage | None:
        """The usage this step settled on, or None where no frame of it carried any.

        A counter a completed frame reported is that frame's; one only an earlier frame reported keeps that frame's
        count, and makes the request provisional.
        """
        early = self.early or {}
        readings = {**early, **self.final}
        if not readings:
            return None
        if not self.final:
            return SettledUsage(readings, request_models.PROVISIONAL, SETTLED_BEFORE_COMPLETION)
        if early.keys() <= self.final.keys():
            return SettledUsage(readings, request_models.FINAL, SETTLED_BY_COMPLETION)
        return SettledUsage(readings, request_models.PROVISIONAL, SETTLED_IN_PART_BEFORE_COMPLETION)

    def _complete(self, position: int, readings: dict[str, Reading]) -> None:
        if self.settled_position is None:
            self.settled_position = position
        for counter, reading in readings.items():
            if self.final.setdefault(counter, reading) != reading:
                self.final[counter] = Reading(state=normalization.CONFLICTING)

    def _timed(self, raw: Any, metadata: Metadata) -> None:
        """Keep the first duration a completed frame reports; one that is no duration is malformed metadata."""
        if self.duration is not None or raw is None:
            return
        self.duration = source_duration(raw)
        metadata.malformed += self.duration is None
