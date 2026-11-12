# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a Claude stream reports about its process rather than about one request.

The `init` frame names the process's session, its model, and the CLI version (`claude_code_version`); a `result` frame
closes the process with aggregate usage; a `system` `task_started` frame names a subagent call and its type; and a
`system` `compact_boundary` frame marks a compaction of the context. None of them is a request.

A `result` frame's `usage` sums the lead thread's final message counts -- on the captures, exactly the lead-thread
requests of the process -- so it is a `result-total` checkpoint of `lead-thread` scope; its `modelUsage` adds every
subagent message to that, one `model-usage` checkpoint of `model` scope per model it names, whose `contextWindow` is
the context capacity the CLI reports for that model. Each total is held to the same arithmetic a request is -- a
lifetime split contradicting its aggregate, or thinking beyond its output, is `conflicting` -- and names in its
`evidence` each counter it reported no usable count for. No capture establishes that a resumed process's totals stop
at the process, so nothing reconciles a request against a total beyond the scope a fresh capture establishes.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import (
    protocol,
    request_coverage as coverage,
    request_models,
    request_normalization as normalization,
)
from orchestrator.observability.usage.request_claude_counters import (
    CACHE_WRITE_TOKENS,
    COUNTERS,
    THINKING_TOKENS,
    malformed_usage,
    raw_counts,
    read_counters,
    unusable,
    usage_readings,
)
from orchestrator.observability.usage.request_normalization import Reading
from orchestrator.observability.usage.request_scan import CollectionLimits, Metadata

RESULT_TOTAL = "result-total"
MODEL_TOTAL = "model-usage"
SESSION_ID = "session_id"
_SUBTYPE = "subtype"
_CONFLICTING = normalization.CONFLICTING
_MODEL_USAGE_COUNTERS = MappingProxyType({
    "inputTokens": normalization.INPUT,
    "outputTokens": normalization.OUTPUT,
    "cacheReadInputTokens": normalization.CACHE_READ,
    "cacheCreationInputTokens": normalization.CACHE_WRITE,
    "thinkingTokens": normalization.REASONING,
})


@dataclass(frozen=True)
class TotalKind:
    """One kind of aggregate total: its name, the scope it covers, and the counters it is read for.

    `related` names, for each normalized field the total's own arithmetic can contradict, the source counter that is
    then conflicting.
    """

    kind: str
    scope: str
    counters: Mapping[str, str]
    related: Mapping[str, str]

    def readings(self, totals: dict[str, Any]) -> dict[str, Reading]:
        if self.counters is COUNTERS:
            return usage_readings(totals)
        return read_counters(totals, self.counters)

    def evidence(self, readings: dict[str, Reading]) -> dict[str, str]:
        """Each counter that is no usable count, or that the total's own arithmetic contradicts, with its state."""
        evidence = dict.fromkeys(self._contradicted(readings), normalization.CONFLICTING)
        evidence.update(unusable(readings))
        return evidence

    def _contradicted(self, readings: dict[str, Reading]) -> list[str]:
        """The reported counters the total's own arithmetic contradicts."""
        conflicting = _conflicting_fields(self.counters, readings)
        contradicted = [name for field_name, name in self.related.items() if field_name in conflicting]
        return [name for name in contradicted if name in readings]


def _conflicting_fields(
    counters: Mapping[str, str],
    readings: dict[str, Reading],
) -> frozenset[str]:
    """The normalized fields of a total its own counters contradict, read under Claude's profile."""
    neutral = {counters[name]: reading for name, reading in readings.items()}
    states = normalization.normalize(protocol.CLAUDE, neutral).to_dict()[normalization.EVIDENCE]
    return frozenset(name for name, state in states.items() if state == _CONFLICTING)


RESULT_KIND = TotalKind(
    RESULT_TOTAL,
    request_models.LEAD_THREAD_SCOPE,
    COUNTERS,
    MappingProxyType({
        normalization.CACHE_WRITE_TOKENS: CACHE_WRITE_TOKENS,
        normalization.REASONING_TOKENS: THINKING_TOKENS,
    }),
)
MODEL_KIND = TotalKind(
    MODEL_TOTAL,
    request_models.MODEL_SCOPE,
    _MODEL_USAGE_COUNTERS,
    MappingProxyType({normalization.REASONING_TOKENS: "thinkingTokens"}),
)


def _counted(reading: Reading) -> bool:
    return bool(reading.known and reading.count)


@dataclass
class Process:
    """What the stream said about the process: its own identities, its totals, its subagent calls, its compactions.

    `launched` holds every subagent call the stream named -- by a `task_started` frame, or by a frame printed on its
    branch -- with the type a `task_started` frame gave it, within the branch bound. `model_usage` is the last
    `modelUsage` the stream printed, which the context capacity of a request's model is read off, and `checkpoints`
    the last totals the stream printed, within the checkpoint bound.
    """

    limits: CollectionLimits
    metadata: Metadata
    session_id: str | None = None
    model: str | None = None
    version: str | None = None
    terminals: int = 0
    aggregate_usage: bool = False
    model_usage: dict[str, Any] = field(default_factory=dict)
    checkpoints: deque[request_models.UsageCheckpoint] = field(default_factory=deque)
    observed_checkpoints: int = 0
    launched: dict[str, str | None] = field(default_factory=dict)
    markers: list[request_models.RequestMarker] = field(default_factory=list)
    gaps: Counter[str] = field(default_factory=Counter)

    def read_system(self, position: int, event: dict[str, Any]) -> None:
        subtype = event.get(_SUBTYPE)
        if subtype == "init":
            self._init(event)
        elif subtype == "task_started":
            self.launch(event.get("tool_use_id"), event.get("subagent_type"))
        elif subtype == "compact_boundary":
            self._compaction(position, event)

    def launch(self, raw_call: Any, raw_type: Any = None) -> None:
        """Note a subagent call, and the type a `task_started` frame gave it, within the branch bound."""
        call = self.metadata.text(raw_call)
        if call is None:
            return
        if call not in self.launched and len(self.launched) >= self.limits.branches:
            self.gaps[coverage.CORRELATION_LIMIT] += 1
            return
        subagent_type = self.metadata.text(raw_type)
        if subagent_type is not None or call not in self.launched:
            self.launched[call] = subagent_type

    def read_result(self, position: int, event: dict[str, Any]) -> None:
        """Keep a `result` frame's totals as checkpoints, and note that the process ended."""
        self.terminals += 1
        self.session_id = self.session_id or self.metadata.text(event.get(SESSION_ID))
        usage = event.get(protocol.USAGE)
        self.gaps[coverage.MALFORMED_USAGE] += malformed_usage(usage)
        if isinstance(usage, dict):
            turns = Reading.of(event.get("num_turns"))
            self._keep(
                RESULT_KIND,
                position,
                usage,
                source_status=self.metadata.text(event.get(_SUBTYPE)),
                turns=turns.count if turns.known else None,
            )
        model_usage = event.get("modelUsage")
        if model_usage is None:
            return
        if not isinstance(model_usage, dict):
            self.gaps[coverage.MALFORMED_USAGE] += 1
            return
        self.model_usage = model_usage
        for model, totals in model_usage.items():
            if isinstance(totals, dict):
                self._keep(MODEL_KIND, position, totals, model=self.metadata.text(model))
            else:
                self.gaps[coverage.MALFORMED_USAGE] += 1

    def capacity(self, model: str | None) -> int | None:
        """The context window the last `modelUsage` reports for `model`, where it reports a usable one."""
        totals = self.model_usage.get(model or "")
        if not isinstance(totals, dict):
            return None
        window = Reading.of(totals.get("contextWindow"))
        return window.count if window.known else None

    def _init(self, event: dict[str, Any]) -> None:
        """The process's own names, each the first an `init` frame gave."""
        text = self.metadata.text
        self.session_id = self.session_id or text(event.get(SESSION_ID))
        self.model = self.model or text(event.get(protocol.MODEL))
        self.version = self.version or text(event.get("claude_code_version"))

    def _keep(self, kind: TotalKind, position: int, totals: dict[str, Any], **details: Any) -> None:
        readings = kind.readings(totals)
        evidence = kind.evidence(readings)
        self.gaps.update(coverage.evidence_gaps(evidence.values()))
        self.aggregate_usage = self.aggregate_usage or any(map(_counted, readings.values()))
        self.observed_checkpoints += 1
        self.checkpoints.append(request_models.UsageCheckpoint(
            kind=kind.kind,
            scope=kind.scope,
            position=position,
            raw=MappingProxyType(raw_counts(readings)),
            evidence=MappingProxyType(evidence),
            **details,
        ))

    def _compaction(self, position: int, event: dict[str, Any]) -> None:
        if len(self.markers) >= self.limits.markers:
            self.gaps[coverage.CORRELATION_LIMIT] += 1
            return
        self.markers.append(request_models.RequestMarker(
            request_models.COMPACTION,
            position,
            parent_tool_use_id=self.metadata.text(event.get(request_models.PARENT_TOOL_USE_ID)),
        ))
