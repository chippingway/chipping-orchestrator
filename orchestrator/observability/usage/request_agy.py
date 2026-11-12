# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Antigravity request usage: one observation per completed usage-bearing step the process's stream printed.

What a step's usage counts is pinned to agy 1.4.10, the same captures the run accounting is: each completed step
carries one generation's usage -- a response's, or a helper generation's such as a `checkpoint` step's -- under
`input_tokens` (ordinary input apart from `cache_read_tokens`), `output_tokens` (holding `thinking_tokens`), and
`total_tokens` (input plus output). A step is keyed by its conversation and `step_index`, so two steps reporting equal
counts stay two requests, and a step repeated over many frames stays one. Observations keep the order the stream
completed them in, a `checkpoint` step's among them.

Only this process's stream is read. A resumed run prints only its own steps, so its observations are its own; the
terminal `result` usage counts the whole conversation, every earlier process of it included, so it is kept as a
conversation-scope checkpoint and never as a request. Before any step is folded, the stream is read for the
conversations it names, so a frame naming none joins the one conversation a stream names, and in a stream naming
none or several is still this process's stdout, kept under a process-scoped identity -- a gap where it could be more
than one conversation's. Which conversation a step belongs to and the model it ran on are the `request_agy_branches`
owner's to establish; a subagent whose conversation exposes no usage, a step completed with no usage, one the stream
never completed, a frame with no step index that carries usage or a generation, an envelope that is no object, and a
stream whose own conversation printed no terminal `result` -- a subagent's result ends only its own conversation --
are gaps the collection records rather than requests it counts.

The stream reports no timestamp, context capacity, CLI version, cache write, or compaction or reset boundary, so none
is ever recorded; `LIMITATIONS` names them for every collection.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterator
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import (
    agy_events,
    protocol,
    request_coverage as coverage,
    request_models,
    request_normalization as normalization,
    request_scan,
)
from orchestrator.observability.usage.request_agy_branches import CONVERSATION_ID, Branches, Census, Child
from orchestrator.observability.usage.request_agy_steps import (
    COUNTERS,
    StepFold,
    StepKey,
    malformed_usage,
    raw_counts,
    unindexed_gap,
    usage_readings,
)
from orchestrator.observability.usage.request_normalization import Reading

LIMITATIONS = (
    "no-source-timestamps",
    "no-context-capacity",
    "no-source-version",
    "no-cache-write-counters",
    "no-compaction-markers",
)
RESULT_TOTAL = "result-total"
# The step indices a step is keyed by: a counter of the conversation's steps, so never negative, and bounded like any
# other correlation metadata.
MAX_STEP_INDEX = 2_147_483_647
STEP_INDICES = range(MAX_STEP_INDEX + 1)
# The source counters a terminal total's own arithmetic can contradict: its total, and the thinking inside its output.
_RELATED_COUNTERS = MappingProxyType({
    normalization.SOURCE_TOTAL_TOKENS: "total_tokens",
    normalization.REASONING_TOKENS: "thinking_tokens",
})
_ENVELOPES = (agy_events.INIT, agy_events.STEP_UPDATE, agy_events.RESULT_EVENT)


def malformed_envelope(event: dict[str, Any]) -> bool:
    """Whether nothing of an event's envelope can be read: no object under the one it names, or no name at all.

    An event whose discriminator is no string -- an array, an object, a number -- could have been any envelope, so it
    is malformed rather than another kind of event; one naming none is simply not an Antigravity event.
    """
    name = event.get(agy_events.EVENT)
    if not isinstance(name, str):
        return name is not None
    return name in _ENVELOPES and not isinstance(event.get(name), dict)


def terminal_checkpoint(
    position: int,
    terminal: dict[str, Any],
    named: str | None,
    metadata: request_scan.Metadata,
) -> request_models.UsageCheckpoint:
    """A terminal `result` as a conversation-scope checkpoint: its counters, and the evidence of any it cannot hold."""
    readings = usage_readings(terminal) or {}
    turns = normalization.Reading.of(terminal.get("num_turns"))
    return request_models.UsageCheckpoint(
        kind=RESULT_TOTAL,
        scope=request_models.CONVERSATION_SCOPE,
        position=position,
        raw=MappingProxyType(raw_counts(readings)),
        conversation_id=named,
        source_status=metadata.text(terminal.get("status")),
        turns=turns.count if turns.known else None,
        evidence=MappingProxyType(checkpoint_evidence(readings)),
    )


def related_conflicts(readings: dict[str, Reading]) -> dict[str, str]:
    """The terminal counters the total's own arithmetic contradicts, each conflicting.

    The total is held to the same arithmetic a request is, within its own conversation scope: a `total_tokens` that is
    not its input plus its output, or thinking beyond its output, contradicts the counters it is made of.
    """
    neutral = {COUNTERS[name]: reading for name, reading in readings.items()}
    fields = normalization.normalize(protocol.AGY, neutral).fields
    return {
        name: normalization.CONFLICTING
        for field_name, name in _RELATED_COUNTERS.items()
        if fields[field_name].state == normalization.CONFLICTING
    }


def checkpoint_evidence(readings: dict[str, Reading]) -> dict[str, str]:
    """The evidence of each terminal counter that is no usable count, or that the total's own arithmetic contradicts."""
    evidence = related_conflicts(readings)
    for name, reading in readings.items():
        if not reading.known:
            evidence[name] = reading.state
    return evidence


@dataclass
class Observations:
    """The requests a fold's settled steps become, in order, with each conversation's own count beside them."""

    branches: Branches
    fallback_model: str | None
    kept: list[request_models.RequestObservation] = field(default_factory=list)
    orders: Counter[str | None] = field(default_factory=Counter)
    gaps: Counter[str] = field(default_factory=Counter)

    @property
    def conversations(self) -> frozenset[str | None]:
        return frozenset(self.orders)

    def add(self, step: StepFold) -> None:
        settled = step.usage()
        if settled is None:
            return
        child = self.branches.children.get(step.key[0] or "")
        observation = request_models.RequestObservation(
            identity=self.identity(step, child),
            position=step.settled_position or 0,
            branch_order=self.orders[step.key[0]],
            attribution=self.branches.attribution(step, self.fallback_model),
            usage=normalization.normalize(protocol.AGY, {
                COUNTERS[counter]: reading for counter, reading in settled.readings.items()
            }),
            raw=MappingProxyType(raw_counts(settled.readings)),
            status=settled.status,
            settlement=settled.settlement,
            source_kind=step.kind,
            source_duration_s=step.duration,
        )
        self.orders[step.key[0]] += 1
        self.kept.append(observation)
        self.gaps.update(coverage.observation_gaps(observation, subagent=child is not None))
        self.gaps[coverage.CONVERSATION_AMBIGUOUS] += self._unplaced(step)

    def identity(self, step: StepFold, child: Child | None) -> request_models.RequestIdentity:
        """A step's stable identity: its conversation and index, or its index alone within the process."""
        conversation, index = step.key
        parent = Child(None, None, None) if child is None else child
        return request_models.RequestIdentity(
            key=f"process:{index}" if conversation is None else f"{conversation}:{index}",
            kind=request_models.PROCESS_STEP if conversation is None else request_models.CONVERSATION_STEP,
            conversation_id=conversation,
            step_index=index,
            parent_conversation_id=parent.parent_conversation_id,
            parent_step_index=parent.parent_step_index,
            subagent_type=parent.subagent_type,
        )

    def _unplaced(self, step: StepFold) -> bool:
        """Whether a request naming no conversation is kept in a stream where whose it is stays unknown."""
        return step.key[0] is None and self.branches.census.unplaced


@dataclass
class StreamFold:
    """One bounded pass over a process's stream: its steps, its branches, and its terminal totals."""

    scan: request_scan.EventScan
    branches: Branches
    steps: dict[StepKey, StepFold] = field(default_factory=dict)
    checkpoints: deque[request_models.UsageCheckpoint] = field(default_factory=deque)
    observed_checkpoints: int = 0
    terminals: set[str | None] = field(default_factory=set)
    envelopes: int = 0
    gaps: Counter[str] = field(default_factory=Counter)

    @classmethod
    def read(cls, stdout: str) -> StreamFold:
        """Scan `stdout`, learn which conversations it names, then fold every event in stream order."""
        limits = request_scan.current_limits()
        scan = request_scan.scan_events(stdout, limits)
        census = Census.taken(scan)
        fold = cls(
            scan,
            Branches(limits, request_scan.Metadata(limits.metadata_chars), census, census.settled),
            checkpoints=deque(maxlen=limits.checkpoints),
        )
        for positioned in scan.events:
            fold.feed(*positioned)
        return fold

    def feed(self, position: int, event: dict[str, Any]) -> None:
        init = agy_events.payload(event, agy_events.INIT)
        frame = agy_events.payload(event, agy_events.STEP_UPDATE)
        terminal = agy_events.payload(event, agy_events.RESULT_EVENT)
        self.envelopes += any(envelope is not None for envelope in (init, frame, terminal))
        self.gaps[coverage.MALFORMED_ENVELOPES] += malformed_envelope(event)
        if event.get(agy_events.EVENT) == agy_events.INIT:
            self.branches.read_init(position, event, init)
        if frame is not None:
            self._step(position, frame)
        if terminal is not None:
            self._terminal(position, terminal)

    def settled_steps(self) -> Iterator[StepFold]:
        """The completed steps in the order the stream completed them."""
        settled = (step for step in self.steps.values() if step.settled)
        return iter(sorted(settled, key=lambda step: step.settled_position or 0))

    def reasons(self, observations: Observations) -> MappingProxyType[str, int]:
        """Every gap the scan, the fold, and the observations recorded, each with how often it occurred."""
        gaps = Counter(self.scan.gaps)
        gaps.update(self.gaps)
        gaps.update(self.branches.gaps)
        gaps.update(observations.gaps)
        # Steps leave gaps without becoming requests: never completed, or completed reporting no usage.
        for step in self.steps.values():
            gaps[coverage.UNSETTLED_STEPS] += step.unsettled_gap
            gaps[coverage.UNREPORTED_USAGE] += step.unreported_gap
        unexposed = set(self.branches.children) - observations.conversations
        gaps[coverage.SUBAGENT_USAGE_UNAVAILABLE] += len(unexposed)
        gaps[coverage.SUBAGENT_UNIDENTIFIED] += len(self.branches.unidentified)
        gaps[coverage.CORRELATION_LIMIT] += len(self.branches.unbranched)
        gaps[coverage.OVERSIZE_METADATA] += self.branches.metadata.oversize
        gaps[coverage.MALFORMED_METADATA] += self.branches.metadata.malformed
        gaps[coverage.NO_STREAM_EVENTS] += not self.envelopes
        # Only the process's own conversation ending ends the process; a subagent's result ends its own alone.
        ended = self.branches.process_conversation in self.terminals
        gaps[coverage.NO_TERMINAL_RESULT] += bool(self.envelopes) and not ended
        gaps[coverage.CONVERSATION_AMBIGUOUS] += self.branches.unsettled
        return MappingProxyType(dict(+gaps))

    def _step(self, position: int, frame: dict[str, Any]) -> None:
        """Fold one `step_update` frame into its step; the subagents it names are read whether or not it has one."""
        self.gaps[coverage.MALFORMED_USAGE] += malformed_usage(frame)
        named = self.branches.metadata.text(frame.get(CONVERSATION_ID))
        conversation = self.branches.census.placed(named)[0]
        index = frame.get(agy_events.STEP_INDEX)
        if isinstance(index, bool) or not isinstance(index, int) or index not in STEP_INDICES:
            self.gaps[coverage.UNINDEXED_FRAMES] += unindexed_gap(frame, self.branches.metadata)
            index = None
        else:
            step = self._tracked((conversation, index))
            if step is not None:
                step.absorb(position, frame, self.branches.metadata)
        if frame.get(agy_events.SUBAGENT_INFO) is not None:
            self.branches.read_subagents((conversation, index), frame[agy_events.SUBAGENT_INFO])

    def _tracked(self, key: StepKey) -> StepFold | None:
        """The fold of the step `key` names, opened on its first frame under the model then in effect."""
        step = self.steps.get(key)
        if step is None and len(self.steps) >= self.branches.limits.tracked_steps:
            self.gaps[coverage.CORRELATION_LIMIT] += 1
        elif step is None:
            models = self.branches.models
            conversation = key[0]
            # A conversation's own model is keyed by its name; the None key is the process's unnamed one alone.
            own = None if conversation is None else models.get(conversation)
            step = StepFold(key, own, models.get(self.branches.process_conversation))
            self.steps[key] = step
        return step

    def _terminal(self, position: int, terminal: dict[str, Any]) -> None:
        """Keep a terminal total as a checkpoint, and note the conversation it ended where that could be the process's.

        Only the process's own conversation ending ends the process. Once its first `init` has settled which that is,
        a result of any other takes no room, so however many the stream prints the process's own is still noted; one
        printed before then could be the process's, so it is held within the branch bound, and one with no room left
        is a correlation-limit gap rather than a result silently dropped.
        """
        named = self.branches.metadata.text(terminal.get(CONVERSATION_ID))
        checkpoint = terminal_checkpoint(position, terminal, named, self.branches.metadata)
        self.gaps[coverage.MALFORMED_USAGE] += malformed_usage(terminal)
        self.gaps.update(coverage.evidence_gaps((checkpoint.evidence or {}).values()))
        self.observed_checkpoints += 1
        self.checkpoints.append(checkpoint)
        conversation, placed = self.branches.census.placed(named)
        settled = self.branches.process_seen
        if not placed or (settled and conversation != self.branches.process_conversation):
            return
        if settled or len(self.terminals) <= self.branches.limits.branches:
            self.terminals.add(conversation)
        else:
            self.gaps[coverage.CORRELATION_LIMIT] += 1


def collect(stdout: str, fallback_model: str | None = None) -> coverage.RequestUsage:
    """Collect the request usage one Antigravity process's stdout reports, within the collection bounds."""
    fold = StreamFold.read(stdout)
    observations = Observations(fold.branches, fallback_model)
    for step in fold.settled_steps():
        observations.add(step)
    return coverage.RequestUsage(
        coverage.CollectionCoverage(
            reasons=fold.reasons(observations),
            limitations=LIMITATIONS,
            scanned_lines=fold.scan.scanned_lines,
            skipped_lines=fold.scan.skipped_lines,
            observed_checkpoints=fold.observed_checkpoints,
        ),
        observations=tuple(observations.kept),
        markers=tuple(fold.branches.markers),
        checkpoints=tuple(fold.checkpoints),
    )
