# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One request-usage collection as a record serializes it: every field the stream gave, and none it did not.

The keys asserted here are the serialized format a trajectory record's `request_usage` carries, so they are spelled
out literally rather than read back off the owners.
"""

import dataclasses
import json
import unittest
from types import MappingProxyType

from orchestrator.observability.usage import (
    protocol,
    request_coverage as coverage,
    request_models as models,
    request_normalization as normalization,
)

_CHILD = "child"
_FALLBACK_MODEL = "configured-model"
_CAPACITY = 1_048_576
_SOURCE_VERSION = "1.4.10"
_LINE = 12
_DURATION_S = 1.5
_CHECKPOINT_LINE = 20
_SCANNED_LINES = 21
_KIND = "kind"
_POSITION = "position"
_CONVERSATION_ID = "conversation_id"
_CACHE_READ_TOKENS = "cache_read_tokens"
_TOTAL_TOKENS = "total_tokens"
_MISSING = normalization.MISSING
_UNSUPPORTED = normalization.UNSUPPORTED
_OBSERVED = normalization.OBSERVED
# An Antigravity request reporting zero cache reads and no thinking or total: the zero is a count, the rest unknown.
_RAW = MappingProxyType({"input_tokens": 10, _CACHE_READ_TOKENS: 0, "output_tokens": 4})
_READINGS = MappingProxyType({
    normalization.INPUT: normalization.Reading.of(10),
    normalization.CACHE_READ: normalization.Reading.of(0),
    normalization.OUTPUT: normalization.Reading.of(4),
})
_FULL = MappingProxyType({
    "id": "child:3",
    "id_kind": "conversation-step",
    _CONVERSATION_ID: _CHILD,
    "session_id": "session-1",
    "turn_id": "turn-2",
    "message_id": "message-7",
    "step_index": 3,
    "parent_conversation_id": "lead",
    "parent_step_index": 1,
    "subagent_type": "explorer",
    _POSITION: _LINE,
    "branch_order": 0,
    "source_kind": "agent_response",
    "source_timestamp": "2026-11-12T08:00:00Z",
    "source_duration_s": _DURATION_S,
    "model": _FALLBACK_MODEL,
    "model_source": "configured-fallback",
    "context_capacity": _CAPACITY,
    "source_version": _SOURCE_VERSION,
    "scope": "request",
    "status": "provisional",
    "settlement": "unconfirmed-frame",
    "raw": dict(_RAW),
    "context_input_tokens": 10,
    "output_tokens": 4,
    _CACHE_READ_TOKENS: 0,
    _TOTAL_TOKENS: 14,
    "overlap": "input-excludes-cache-reads",
    "evidence": {
        "context_input_tokens": _OBSERVED,
        "output_tokens": _OBSERVED,
        _CACHE_READ_TOKENS: _OBSERVED,
        "cache_write_tokens": _UNSUPPORTED,
        "reasoning_tokens": _MISSING,
        _TOTAL_TOKENS: _OBSERVED,
        "source_total_tokens": _MISSING,
        "cache_write_lifetimes": _UNSUPPORTED,
    },
})
# Every identity and source field a sample keys only where its stream gave one.
_NEVER_GIVEN = frozenset((
    _CONVERSATION_ID, "session_id", "turn_id", "message_id", "parent_conversation_id", "parent_step_index",
    "parent_turn_id", "subagent_type", "source_kind", "source_timestamp", "source_duration_s", "source_flags",
))
# A request a native session log reported in a child turn, known by the line reporting it, with the flag its source
# reported beside its counters.
_TURN_IDS = MappingProxyType({"turn_id": "turn-3", "parent_turn_id": "turn-2"})
_FLAGS = MappingProxyType({"last_usage_includes_reasoning": False})
_NATIVE = MappingProxyType({
    "id": "rollout-line:7",
    "id_kind": "native-position",
    **_TURN_IDS,
    "source_flags": dict(_FLAGS),
})
_MARKERS = (
    models.RequestMarker(models.MODEL_CHANGE, 4, _CHILD, model="b", previous_model="a"),
    models.RequestMarker(models.COMPACTION, 6),
    models.RequestMarker(models.RESET, 8),
    models.RequestMarker(models.MODEL_CHANGE, 10, _CHILD, model="d", previous_model="c", **_TURN_IDS),
)
_SERIALIZED_MARKERS = (
    {_KIND: "model-change", _POSITION: 4, _CONVERSATION_ID: _CHILD, "model": "b", "previous_model": "a"},
    {_KIND: "compaction", _POSITION: 6},
    {_KIND: "reset", _POSITION: 8},
    {_KIND: "model-change", _POSITION: 10, _CONVERSATION_ID: _CHILD, **_TURN_IDS, "model": "d", "previous_model": "c"},
)
_CHECKPOINT = models.UsageCheckpoint(
    "result-total",
    models.CONVERSATION_SCOPE,
    _CHECKPOINT_LINE,
    MappingProxyType({_TOTAL_TOKENS: 9}),
    conversation_id=_CHILD,
    source_status="SUCCESS",
    turns=2,
    evidence=MappingProxyType({_TOTAL_TOKENS: normalization.CONFLICTING}),
)
_SERIALIZED_CHECKPOINT = MappingProxyType({
    _KIND: "result-total",
    "scope": "conversation",
    _POSITION: _CHECKPOINT_LINE,
    _CONVERSATION_ID: _CHILD,
    "source_status": "SUCCESS",
    "turns": 2,
    "raw": {_TOTAL_TOKENS: 9},
    "evidence": {_TOTAL_TOKENS: "conflicting"},
})
_COUNTS = MappingProxyType({
    "status": coverage.COMPLETE,
    "observed_samples": 1,
    "observed_markers": len(_MARKERS),
    "observed_checkpoints": 2,
    "retained_checkpoints": 1,
})


def _observation(identity: models.RequestIdentity, **source: str | float) -> models.RequestObservation:
    attribution = models.RequestAttribution(
        _FALLBACK_MODEL, models.CONFIGURED_FALLBACK, context_capacity=_CAPACITY, source_version=_SOURCE_VERSION,
    )
    return models.RequestObservation(
        identity=identity,
        position=_LINE,
        branch_order=0,
        attribution=attribution,
        usage=normalization.normalize(protocol.AGY, _READINGS),
        raw=_RAW,
        status=models.PROVISIONAL,
        settlement="unconfirmed-frame",
        **source,
    )


def _full() -> models.RequestObservation:
    identity = models.RequestIdentity(
        "child:3", models.CONVERSATION_STEP, conversation_id=_CHILD, session_id="session-1", turn_id="turn-2",
        message_id="message-7", step_index=3, parent_conversation_id="lead", parent_step_index=1,
        subagent_type="explorer",
    )
    return _observation(
        identity, source_kind="agent_response", source_timestamp="2026-11-12T08:00:00Z", source_duration_s=_DURATION_S,
    )


class ObservationRecordTest(unittest.TestCase):
    """A sample carries what its stream gave under fixed keys, and a key for nothing it did not."""

    def test_every_given_field_is_serialized(self) -> None:
        serialized = _full().to_dict()
        self.assertEqual(serialized, dict(_FULL))
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)
        # When the collection ran is the record's own envelope, never a field of the sample.
        self.assertNotIn("ts", serialized)

    def test_what_the_stream_left_out_is_absent(self) -> None:
        sparse = _observation(models.RequestIdentity("process:3", models.PROCESS_STEP, step_index=3)).to_dict()
        self.assertFalse(_NEVER_GIVEN & set(sparse))
        self.assertEqual((sparse["id"], sparse["id_kind"]), ("process:3", "process-step"))
        # A counter reported as zero is a count; one never reported is missing evidence with no count beside it.
        self.assertEqual(sparse[_CACHE_READ_TOKENS], 0)
        self.assertFalse({"reasoning_tokens", "source_total_tokens"} & set(sparse))
        self.assertNotIn(None, sparse.values())

    def test_native_turns_and_flags(self) -> None:
        # The child turn a native request settled in, the turn it was started from, and the source's flags as given.
        identity = models.RequestIdentity("rollout-line:7", models.NATIVE_POSITION, **_TURN_IDS)
        native = dataclasses.replace(_observation(identity), source_flags=_FLAGS).to_dict()
        self.assertEqual({name: native[name] for name in _NATIVE}, dict(_NATIVE))


class CollectionRecordTest(unittest.TestCase):
    """Markers and checkpoints ride beside the samples, each in its own list, and neither is counted as a request."""

    def test_markers_and_checkpoints_are_no_requests(self) -> None:
        usage = coverage.RequestUsage(
            coverage.CollectionCoverage(MappingProxyType({}), scanned_lines=_SCANNED_LINES, observed_checkpoints=2),
            observations=(_full(),),
            markers=_MARKERS,
            checkpoints=(_CHECKPOINT,),
        )
        serialized = usage.to_dict()
        self.assertEqual(serialized["markers"], list(_SERIALIZED_MARKERS))
        # A checkpoint keeps the scope its total covers, apart from the request scope of every sample.
        self.assertEqual(serialized["checkpoints"], [dict(_SERIALIZED_CHECKPOINT)])
        self.assertEqual([sample["scope"] for sample in serialized["samples"]], ["request"])
        summary = serialized["coverage"]
        self.assertEqual({name: summary[name] for name in _COUNTS}, dict(_COUNTS))
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)
