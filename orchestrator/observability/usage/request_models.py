# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one request-usage collection is made of: observations, markers, and aggregate checkpoints.

An observation is one request the provider's stream settled usage for, under an identity that stays the same however
often the stream repeats it: what it is called and what kind of name that is, where the stream placed it, every
session, conversation, turn, message, step, and parent or subagent identity the stream gave it, the model it ran on
and how that model was established, the raw counters as reported, the normalized counters with their evidence, and
whether its usage is final or provisional and which report settled it. A source timestamp is the stream's own; the
moment a collection ran is the record's, never one of these. A field the stream did not give is absent, never guessed:
no timestamp, branch order across conversations, context capacity, or model is inferred from unrelated data.

A marker is an explicit boundary the stream printed -- a model change, a context compaction, or a reset -- and a
checkpoint is aggregate evidence such as a terminal total, with the scope it covers. Neither is a request, so neither
is ever counted as one, and a stream that prints no such boundary records none rather than one inferred.

Everything here is a counter or a short piece of correlation metadata an adapter has already bounded: no prompt,
response or tool text, reasoning text, or unrestricted source dictionary enters a record.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from orchestrator.observability.usage.request_normalization import NormalizedUsage

# Identity kinds: a step within a named conversation, and a step the stream named no conversation for, which is
# known only within the process that printed it.
CONVERSATION_STEP = "conversation-step"
PROCESS_STEP = "process-step"

# Scopes: one request, and every request of a conversation however many processes it spanned.
REQUEST_SCOPE = "request"
CONVERSATION_SCOPE = "conversation"

FINAL = "final"
PROVISIONAL = "provisional"

# Where a model attribution came from.
STREAM_MODEL = "stream"
CONFIGURED_FALLBACK = "configured-fallback"
UNESTABLISHED = "unestablished"
UNAVAILABLE = "unavailable"

# Marker kinds: the boundaries an adapter records where its stream prints one -- a model change, and a context
# compaction or reset -- and never infers where it does not.
MODEL_CHANGE = "model-change"
COMPACTION = "compaction"
RESET = "reset"
CONVERSATION_ID = "conversation_id"
POSITION = "position"
RAW = "raw"
MODEL = "model"
KIND = "kind"
SCOPE = "scope"


def compact(fields: Mapping[str, Any]) -> dict[str, Any]:
    """The fields that hold something: a field the stream did not give is absent rather than null."""
    return {name: field_value for name, field_value in fields.items() if field_value is not None}


@dataclass(frozen=True)
class RequestIdentity:
    """Who one request is: a stable key, what kind of key it is, and every identity the stream gave it."""

    key: str
    kind: str
    conversation_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    message_id: str | None = None
    step_index: int | None = None
    parent_conversation_id: str | None = None
    parent_step_index: int | None = None
    subagent_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return compact({
            "id": self.key,
            "id_kind": self.kind,
            CONVERSATION_ID: self.conversation_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "message_id": self.message_id,
            "step_index": self.step_index,
            "parent_conversation_id": self.parent_conversation_id,
            "parent_step_index": self.parent_step_index,
            "subagent_type": self.subagent_type,
        })


@dataclass(frozen=True)
class RequestAttribution:
    """The model one request ran on, how that was established, and what the stream said about its context and CLI."""

    model: str | None
    model_source: str
    context_capacity: int | None = None
    source_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return compact({
            MODEL: self.model,
            "model_source": self.model_source,
            "context_capacity": self.context_capacity,
            "source_version": self.source_version,
        })


@dataclass(frozen=True)
class RequestObservation:
    """One request the stream settled usage for.

    `position` is the stream line that completed it and `branch_order` its place among its own conversation's
    requests; neither orders it against another conversation's. `raw` holds the allowlisted counters that are whole
    counts, a negative one included -- a value that is none is left out, its field invalid -- `usage` the normalized
    ones, and `settlement` the report its `status` rests on.
    """

    identity: RequestIdentity
    position: int
    branch_order: int
    attribution: RequestAttribution
    usage: NormalizedUsage
    raw: Mapping[str, int]
    status: str
    settlement: str
    scope: str = REQUEST_SCOPE
    source_kind: str | None = None
    source_timestamp: str | None = None
    source_duration_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.identity.to_dict(),
            POSITION: self.position,
            "branch_order": self.branch_order,
            **compact({
                "source_kind": self.source_kind,
                "source_timestamp": self.source_timestamp,
                "source_duration_s": self.source_duration_s,
            }),
            **self.attribution.to_dict(),
            SCOPE: self.scope,
            "status": self.status,
            "settlement": self.settlement,
            RAW: dict(self.raw),
            **self.usage.to_dict(),
        }


@dataclass(frozen=True)
class RequestMarker:
    """An explicit boundary the stream printed, at the line it printed it; never a request."""

    kind: str
    position: int
    conversation_id: str | None = None
    model: str | None = None
    previous_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return compact({
            KIND: self.kind,
            POSITION: self.position,
            CONVERSATION_ID: self.conversation_id,
            MODEL: self.model,
            "previous_model": self.previous_model,
        })


@dataclass(frozen=True)
class UsageCheckpoint:
    """Aggregate usage the stream reported over a wider scope than one request; never a request itself."""

    kind: str
    scope: str
    position: int
    raw: Mapping[str, int]
    conversation_id: str | None = None
    source_status: str | None = None
    turns: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return compact({
            KIND: self.kind,
            SCOPE: self.scope,
            POSITION: self.position,
            CONVERSATION_ID: self.conversation_id,
            "source_status": self.source_status,
            "turns": self.turns,
            RAW: dict(self.raw),
        })
