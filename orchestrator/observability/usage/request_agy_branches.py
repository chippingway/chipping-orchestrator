# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which Antigravity conversation one step belongs to, and the model it is established to have run on.

A process stream is its own conversation -- the one its first `init` names, or, where that names none, the one
conversation the stream names besides the subagents any `subagent_info` names -- and every subagent a step spawned is a
branch of its own, with what its frames say of its parent and type merged, a contradiction among them a gap. Which
conversations a stream names, and which of them are subagents, is read before any step is folded (`Census`), so the
process's conversation is known as its first `init` is read -- an unnamed one's model is that conversation's -- and a
frame or an `init` naming no conversation in a stream that names exactly one, and spawns no subagent, is that
conversation's -- a frame folded into the same step as the frames that do name it -- and in a stream naming none it is
the process's own unnamed conversation; in any other stream it could be any of them, so it stays unplaced and is a gap.
A name this collection refused -- too long to keep, or no string -- is not an absent one: it names a conversation
nothing can be compared with, so the stream is never taken to name only one, and a process `init` naming one leaves the
process's conversation unknown rather than settled on whichever other conversation the steps name. A line the scan left
unread -- past the scan bound, too long to read, or one the decoder refused -- could have named any conversation or
spawned any subagent, so a stream missing one is never taken to name only one either, and nor is one carrying a frame
or a `result` whose envelope is no object, since each names its conversation inside it. An `init` names its
conversation beside its envelope, so that name is read whatever the envelope holds.

`init.model` echoes the `--model` slug a conversation was started with, and every generation of that conversation, a
response's and each helper generation beside it, runs on the model it selected. So a step is attributed to the model its
own conversation's `init` named as the step began -- a subagent's own `init` included -- and a step of the process's
conversation, where its own conversation's `init` named none, to the process's `init` model or the configured `--model`
the caller passes as a fallback -- held to the same metadata bound as a streamed name -- each under its own provenance.
A step of any other conversation whose `init` named no model keeps its parent and subagent identities and no model at
all, never its parent's, and so does an unplaced step. An `init` naming a different model than its conversation's
previous one is a model change, kept as a marker; a later `init` this collection cannot place changes no model and is a
gap, since the model it names could be any conversation's. An `init` naming a model this collection refused -- too long
to keep, or no string -- or one whose envelope is no object, so any model it named went unread, leaves its
conversation's model unknown from there on: a step begun before it keeps the model it began under, while a later one
has no model, neither an earlier `init`'s nor the fallback, and is a gap; no marker is kept, since the model it changed
to is unknown.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import astuple, dataclass, field
from typing import Any

from orchestrator.observability.usage import (
    agy_events,
    protocol,
    request_coverage as coverage,
    request_models,
)
from orchestrator.observability.usage.request_agy_steps import UNKEPT_MODEL, StepFold
from orchestrator.observability.usage.request_scan import CollectionLimits, EventScan, Metadata

CONVERSATION_ID = request_models.CONVERSATION_ID
_SUBAGENTS = "subagents"
# The events naming their conversation inside their envelope rather than beside it.
_NAMED_INSIDE = frozenset((agy_events.STEP_UPDATE, agy_events.RESULT_EVENT))
# The step a subagent was spawned from: its conversation, and its index where the frame named one.
ParentKey = tuple[str | None, int | None]


def _named(raw: Any) -> bool:
    """Whether a field names anything at all -- kept or refused -- rather than nothing."""
    return raw is not None and raw != ""


def _model(metadata: Metadata, init: dict[str, Any] | None) -> str | None:
    """The model one `init` names: as kept, `UNKEPT_MODEL` where this collection refused it, and None where none.

    `init` is the event's envelope, None where that is no object: any model it named went unread, which is a model
    refused like any other.
    """
    if init is None:
        return UNKEPT_MODEL
    raw = init.get(protocol.MODEL)
    kept = metadata.text(raw)
    if kept is None and _named(raw):
        return UNKEPT_MODEL
    return kept


def _differ(earlier: Any, now: Any) -> bool:
    """Whether two reports of one field both name a value, and different ones."""
    return None not in {earlier, now} and earlier != now


@dataclass(frozen=True)
class Child:
    """A subagent conversation one step spawned, and the step it was spawned from."""

    parent_conversation_id: str | None
    parent_step_index: int | None
    subagent_type: str | None

    def merged(self, later: Child) -> Child:
        """This child with what a later frame adds: any parent identity or subagent type no earlier frame named."""
        pairs = zip(astuple(self), astuple(later), strict=True)
        kept = [now if earlier is None else earlier for earlier, now in pairs]
        return Child(*kept)

    def contradicts(self, later: Child) -> bool:
        """Whether a later frame names this child's parent conversation, parent step, or type differently."""
        pairs = zip(astuple(self), astuple(later), strict=True)
        return any(_differ(earlier, now) for earlier, now in pairs)


@dataclass
class Census:
    """Which conversations a stream names, read before any of its steps is folded.

    It keeps each name within a bound, the subagent conversations any `subagent_info` names, and whether a name was
    refused -- too long to keep, no string at all, past the bound, on a line the scan left unread, or inside an envelope
    that is no object -- or a subagent spawn followed, so it costs no more than the bound however many conversations a
    stream names, and a stream it could not read whole is never taken to name only the ones it kept.
    """

    limit: int
    bound: int
    names: set[str] = field(default_factory=set)
    children: set[str] = field(default_factory=set)
    refused: bool = False
    spawned: bool = False

    @classmethod
    def taken(cls, scan: EventScan) -> Census:
        """The census of every event `scan` decoded; any line it left unread could have named any conversation."""
        census = cls(scan.limits.metadata_chars, scan.limits.branches + 1)
        census.refused = bool(scan.gaps)
        for _, event in scan.events:
            census.read(event)
        return census

    @property
    def unplaced(self) -> bool:
        """Whether a frame naming no conversation could belong to more than one."""
        return self.refused or self.spawned or len(self.names) > 1

    @property
    def settled(self) -> str | None:
        """The one conversation the stream names besides its subagents', where it names exactly one and kept all."""
        candidates = self.names - self.children
        if self.refused or len(candidates) != 1:
            return None
        return next(iter(candidates))

    def placed(self, named: str | None) -> tuple[str | None, bool]:
        """The conversation a frame or `init` belongs to, and whether that is established.

        `named` is the conversation it names as this collection keeps it. One naming none, or one whose name was
        refused, is the stream's one conversation where it names exactly one, its unnamed process conversation where
        it names none, and established in neither way otherwise.
        """
        if named is not None:
            return named, True
        if self.unplaced:
            return None, False
        return next(iter(self.names), None), True

    def read(self, event: dict[str, Any]) -> None:
        """Note the conversations one event names, wherever the fold reads them from.

        An `init` names its conversation beside its envelope, so that name is read whatever the envelope holds. A
        frame or a `result` names it inside, so one whose envelope is no object could have named any conversation, or
        spawned any subagent, and is a refusal like a line the scan left unread.
        """
        name = event.get(agy_events.EVENT)
        if name == agy_events.INIT:
            self._name(event.get(CONVERSATION_ID))
            return
        if name not in _NAMED_INSIDE:
            return
        envelope = agy_events.payload(event, name)
        if envelope is None:
            self.refused = True
            return
        self._name(envelope.get(CONVERSATION_ID))
        if name == agy_events.STEP_UPDATE:
            self._spawn(envelope.get(agy_events.SUBAGENT_INFO))

    def _name(self, raw: Any) -> None:
        if not _named(raw):
            return
        # A name too long to keep, no string at all, or one past the bound cannot be compared with the rest.
        if not isinstance(raw, str) or len(raw) > self.limit:
            self.refused = True
            return
        if raw in self.names or len(self.names) < self.bound:
            self.names.add(raw)
        else:
            self.refused = True

    def _spawn(self, subagent_info: Any) -> None:
        """Note a spawn, and each subagent conversation it names within the bound."""
        if subagent_info is None:
            return
        self.spawned = True
        subagents = subagent_info.get(_SUBAGENTS) if isinstance(subagent_info, dict) else None
        for subagent in subagents if isinstance(subagents, list) else ():
            named = subagent.get(CONVERSATION_ID) if isinstance(subagent, dict) else None
            kept = isinstance(named, str) and len(named) <= self.limit
            if kept and len(self.children) < self.bound:
                self.children.add(named)


def _kept(markers: list[request_models.RequestMarker], limit: int, marker: request_models.RequestMarker) -> bool:
    """Keep `marker` where the markers are still within their bound."""
    if len(markers) >= limit:
        return False
    markers.append(marker)
    return True


@dataclass
class Branches:
    """The process's own conversation, each conversation's model, the subagents its steps spawned, and the markers.

    A step's `subagent_info` repeats on every frame of it, so the subagents it could not name or correlate are kept as
    the steps that spawned them, and each counts once however often the stream repeats it. The models are kept by the
    conversation whose `init` named them, within the branch bound, a model it refused as `UNKEPT_MODEL`. The process's
    conversation starts as the one the census settles; its first `init` overrides it with the conversation it names,
    keeps it where it names none -- so its model is that conversation's, and a later `init` naming the conversation is a
    change from it -- and leaves it unknown where its name was refused.
    """

    limits: CollectionLimits
    metadata: Metadata
    census: Census
    process_conversation: str | None = None
    process_seen: bool = False
    process_refused: bool = False
    models: dict[str | None, str] = field(default_factory=dict)
    markers: list[request_models.RequestMarker] = field(default_factory=list)
    children: dict[str, Child] = field(default_factory=dict)
    unidentified: set[ParentKey] = field(default_factory=set)
    unbranched: set[ParentKey] = field(default_factory=set)
    gaps: Counter[str] = field(default_factory=Counter)

    def read_init(
        self,
        position: int,
        event: dict[str, Any],
        init: dict[str, Any] | None,
    ) -> None:
        """Read one `init`: the conversation it names, and the model that conversation runs on from here on.

        `init` is its envelope, None where that is no object: the conversation it names beside the envelope is still
        read, while the model it names cannot be, so it is one this collection refused.
        """
        conversation, placed = self._init_conversation(event.get(CONVERSATION_ID))
        if not placed:
            self.gaps[coverage.CONVERSATION_AMBIGUOUS] += 1
            return
        model = _model(self.metadata, init)
        if model is None:
            return
        previous = self.models.get(conversation)
        if previous is None and len(self.models) > self.limits.branches:
            self.gaps[coverage.CORRELATION_LIMIT] += 1
            return
        self.models[conversation] = model
        # A change is one between two models this collection kept: none is known to or from a refused one.
        if UNKEPT_MODEL in {previous, model} or previous in {None, model}:
            return
        changed = request_models.RequestMarker(request_models.MODEL_CHANGE, position, conversation, model, previous)
        if not _kept(self.markers, self.limits.markers, changed):
            self.gaps[coverage.CORRELATION_LIMIT] += 1

    @property
    def unsettled(self) -> bool:
        """Whether the process's conversation goes unestablished in a stream naming conversations it could be.

        Every conversation the stream names counts -- in an `init`, a step, or a `result` -- so a stream naming two or
        more besides its subagents, or one whose names this collection could not all keep, leaves it unnamed: a request
        of any of them is attributed to none rather than to a model only one of them may have run on.
        """
        if self.process_conversation is not None or self.process_refused:
            return False
        return self.census.refused or bool(self.census.names - self.census.children)

    def read_subagents(self, parent: ParentKey, subagent_info: Any) -> None:
        """Record each subagent conversation a step's `subagent_info` names; an unnamed one is a gap.

        `parent` is the spawning step's conversation and index -- no index where the frame named none, since the
        children it announces are no less the stream's for it.
        """
        subagents = subagent_info.get(_SUBAGENTS) if isinstance(subagent_info, dict) else None
        if not isinstance(subagents, list) or not subagents:
            self.unidentified.add(parent)
            return
        for subagent in subagents:
            self._read_child(parent, subagent)

    def attribution(self, step: StepFold, fallback_model: str | None) -> request_models.RequestAttribution:
        foreign = self._foreign(step.key[0])
        model = step.own_model if foreign or step.own_model is not None else step.process_model
        if model == UNKEPT_MODEL or (model is None and foreign):
            return request_models.RequestAttribution(None, request_models.UNESTABLISHED)
        if model is not None:
            return request_models.RequestAttribution(model, request_models.STREAM_MODEL)
        fallback = self.metadata.text(fallback_model)
        if fallback is not None:
            return request_models.RequestAttribution(fallback, request_models.CONFIGURED_FALLBACK)
        return request_models.RequestAttribution(None, request_models.UNAVAILABLE)

    def _init_conversation(self, raw: Any) -> tuple[str | None, bool]:
        """The conversation one `init` belongs to, and whether that is established.

        The first `init` is the process's own, whichever conversation it names or fails to: one naming none keeps the
        conversation the census settled, and one whose name was refused leaves the process's conversation unknown.
        """
        named = self.metadata.text(raw)
        if self.process_seen:
            return self.census.placed(named)
        self.process_seen = True
        self.process_refused = named is None and _named(raw)
        if named is not None or self.process_refused:
            self.process_conversation = named
        return self.process_conversation, True

    def _foreign(self, conversation: str | None) -> bool:
        """Whether a step may belong to a conversation other than the process's own."""
        if conversation is None:
            return self.census.unplaced
        return conversation in self.children or conversation != self.process_conversation

    def _read_child(self, parent: ParentKey, subagent: Any) -> None:
        named = subagent if isinstance(subagent, dict) else {}
        conversation = self.metadata.text(named.get(CONVERSATION_ID))
        if conversation is None:
            self.unidentified.add(parent)
        elif conversation not in self.children and len(self.children) >= self.limits.branches:
            self.unbranched.add(parent)
        else:
            subagent_type = self.metadata.text(named.get("type_name"))
            spawned = Child(*parent, subagent_type)
            known = self.children.setdefault(conversation, spawned)
            self.children[conversation] = known.merged(spawned)
            self.gaps[coverage.SUBAGENT_ATTRIBUTION_CONFLICTING] += known.contradicts(spawned)
