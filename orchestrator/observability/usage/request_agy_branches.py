# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which Antigravity conversation one step belongs to, and the model it is established to have run on.

A process stream is its own conversation -- the one its `init` names, or, where no `init` names one, the one
conversation its steps name besides its subagents' -- and every subagent a step spawned (`subagent_info`) is a branch
of its own. `init.model` echoes the `--model` slug the process was given, and every
generation of that conversation, a response's and each helper generation beside it, runs on the model it selected,
so a step of the process's own conversation is attributed to the `init` model in effect when it began, or, where no
`init` named one, to the configured `--model` the caller passes as a fallback, each under its own provenance. A
subagent's conversation is another conversation whose model no frame names: its steps keep their parent and subagent
identities and no model at all, never their parent's, and so does a step of any conversation other than the
process's. A step naming no conversation in a stream that spawned a subagent could be either side's, so it is given
no model either. An `init` of the process naming a different model than the one before it is a model change, kept as
a marker; an `init` of another conversation changes nothing.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from orchestrator.observability.usage import (
    protocol,
    request_coverage as coverage,
    request_models,
)
from orchestrator.observability.usage.request_agy_steps import StepFold, StepKey
from orchestrator.observability.usage.request_scan import CollectionLimits, Metadata

CONVERSATION_ID = request_models.CONVERSATION_ID
_SUBAGENTS = "subagents"


@dataclass(frozen=True)
class Child:
    """A subagent conversation one step spawned, and the step it was spawned from."""

    parent_conversation_id: str | None
    parent_step_index: int | None
    subagent_type: str | None


def _kept(markers: list[request_models.RequestMarker], limit: int, marker: request_models.RequestMarker) -> bool:
    """Keep `marker` where the markers are still within their bound."""
    if len(markers) >= limit:
        return False
    markers.append(marker)
    return True


@dataclass
class Branches:
    """The process's own conversation and model, the subagents its steps spawned, and the markers between them.

    A step's `subagent_info` repeats on every frame of it, so the subagents it could not name or correlate are kept as
    the steps that spawned them, and each counts once however often the stream repeats it.
    """

    limits: CollectionLimits
    metadata: Metadata
    process_conversation: str | None = None
    model: str | None = None
    markers: list[request_models.RequestMarker] = field(default_factory=list)
    children: dict[str, Child] = field(default_factory=dict)
    unidentified: set[StepKey] = field(default_factory=set)
    unbranched: set[StepKey] = field(default_factory=set)
    gaps: Counter[str] = field(default_factory=Counter)

    def read_init(
        self,
        position: int,
        event: dict[str, Any],
        init: dict[str, Any],
    ) -> None:
        """Read the process's `init`: the conversation it names, and the model it runs on from here on.

        Only the process's own `init` says what its conversation runs on, so one naming another conversation changes
        no model and marks nothing.
        """
        conversation = self.metadata.text(event.get(CONVERSATION_ID))
        if self.process_conversation is None:
            self.process_conversation = conversation
        model = self.metadata.text(init.get(protocol.MODEL))
        if model is None or conversation != self.process_conversation:
            return
        previous = self.model
        self.model = model
        if previous in {None, model}:
            return
        changed = request_models.RequestMarker(request_models.MODEL_CHANGE, position, conversation, model, previous)
        if not _kept(self.markers, self.limits.markers, changed):
            self.gaps[coverage.CORRELATION_LIMIT] += 1

    def read_subagents(self, parent: StepFold, subagent_info: Any) -> None:
        """Record each subagent conversation a step's `subagent_info` names; an unnamed one is a gap."""
        subagents = subagent_info.get(_SUBAGENTS) if isinstance(subagent_info, dict) else None
        if not isinstance(subagents, list) or not subagents:
            self.unidentified.add(parent.key)
            return
        for subagent in subagents:
            self._read_child(parent, subagent)

    def settle(self, conversations: Iterable[str | None]) -> None:
        """Name the process's conversation where no `init` did: the one its steps name besides its subagents'.

        A stream naming two or more such conversations leaves it unnamed, so a step of any of them is attributed to
        none rather than to a model only one of them may have run on.
        """
        if self.process_conversation is not None:
            return
        named = {conversation for conversation in conversations if conversation is not None}
        named.difference_update(self.children)
        if len(named) == 1:
            self.process_conversation = named.pop()

    def child(self, step: StepFold) -> Child | None:
        conversation = step.key[0]
        return None if conversation is None else self.children.get(conversation)

    def attribution(self, step: StepFold, fallback_model: str | None) -> request_models.RequestAttribution:
        if self._foreign(step.key[0]):
            return request_models.RequestAttribution(None, request_models.UNESTABLISHED)
        if step.model is not None:
            return request_models.RequestAttribution(step.model, request_models.STREAM_MODEL)
        if fallback_model:
            return request_models.RequestAttribution(fallback_model, request_models.CONFIGURED_FALLBACK)
        return request_models.RequestAttribution(None, request_models.UNAVAILABLE)

    def _foreign(self, conversation: str | None) -> bool:
        """Whether a step may belong to a conversation other than the process's own."""
        if conversation is None:
            return bool(self.children)
        return conversation in self.children or conversation != self.process_conversation

    def _read_child(self, parent: StepFold, subagent: Any) -> None:
        named = subagent if isinstance(subagent, dict) else {}
        conversation = self.metadata.text(named.get(CONVERSATION_ID))
        if conversation is None:
            self.unidentified.add(parent.key)
        elif conversation not in self.children and len(self.children) >= self.limits.branches:
            self.unbranched.add(parent.key)
        else:
            parent_conversation, parent_index = parent.key
            subagent_type = self.metadata.text(named.get("type_name"))
            self.children.setdefault(conversation, Child(parent_conversation, parent_index, subagent_type))
