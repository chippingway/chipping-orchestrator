# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One pass over a Codex native session log: the models its turns run on, the requests it settles, the running sums
beside them, the boundaries it marks, and the subagent threads it names.

Every line is read, the earlier invocations' as much as this one's, since what the invocation's lines mean depends on
what came before them: the model the thread's last `turn_context` set, and the running sum its last `token_count`
left. Only the invocation's own lines -- the ones its timeline places past the boundary -- become samples, markers,
and checkpoints. Which turn, and so which branch, a request belongs to is the `request_codex_scope` turns' to say: a
child turn's own branch, or the thread's.

Models. A `turn_context` sets the model its turn runs on: a child turn's own, or else the thread's, which holds until
the next one. A request that settles before its turn's own `turn_context` -- the compaction a model switch runs first,
on the model the thread had -- ran on the thread's model as the last one left it. A child turn without a `turn_context`
of its own ran on no model this log establishes, never its parent's; a thread with none falls back to the configured
`-m` model. A thread `turn_context` naming another model than the last one the invocation's lines inherit is a
`model-change` marker, a `compacted` line a `compaction` marker, and a `thread_rolled_back` event a `reset` marker.

Requests. Each `token_count` reports one request's own usage (`last_token_usage`) beside its branch's running sum
(`total_token_usage`). A sum equal to the last one the branch reported repeats a notification -- the CLI prints the
same report again, opens a turn with the sum the last one left, and follows a compaction with a context estimate --
and is no request. A sum advancing by exactly the request's own counters, at least one of them moving, is a new
request, so two requests of equal counts stay two; one advancing by anything else, one only counters staying at zero
agree with, or one following a line this pass could not read -- which could have been the report it repeats -- is not
proven a new request, and is an `unreconciled-usage` gap rather than a sample, so no earlier invocation's request is
ever copied into this one. The thread's running sums are checkpoints of the whole
conversation: the last one before the boundary as the invocation's baseline, and the ones its own requests advance.
A child turn's sums are kept only to prove its requests, since nothing establishes what they span.

Subagents. A child turn the invocation opened that settled no request, and a subagent thread its lines name -- in an
`item_completed` `SubAgentActivity`, or in a legacy history's `sub_agent_activity` event -- whose requests are in a log
of that thread's own, which this pass never reads, are usage this collection saw happen and could not observe, so each
is a gap rather than a silence; so is a child turn naming no id, whose requests no branch can keep, whether or not any
settles in it.

Checkpoints are held to a request's arithmetic, so a running sum reporting a counter no usable count, or contradicting
its own parts, is a gap of the collection keeping it as well as its own evidence.
"""

from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, NamedTuple

from orchestrator.observability.usage import request_coverage as coverage, request_models, request_scan
from orchestrator.observability.usage.request_codex_counters import Counters, attribution, checkpoint, source_flags
from orchestrator.observability.usage.request_codex_scope import (
    PAYLOAD,
    SESSION_META,
    TYPE,
    Timeline,
    Turn,
    Turns,
    stamped,
)

SETTLED_BY_TOKEN_COUNT = "token-count"
CUMULATIVE_TOTAL = "cumulative-total"
INVOCATION_BASELINE = "invocation-baseline"
NATIVE_LINE = "rollout-line"
_TURN_ID = "turn_id"
_EVENT_MSG = "event_msg"
_TURN_CONTEXT = "turn_context"
# The kinds of line whose payload this collection reads; every other kind is read for its kind alone, if at all.
_READ = frozenset((SESSION_META, _TURN_CONTEXT, _EVENT_MSG))
_CLOSES = frozenset(("task_complete", "turn_aborted"))
_MARKED = MappingProxyType({"compacted": request_models.COMPACTION})
_EVENT_MARKERS = MappingProxyType({"thread_rolled_back": request_models.RESET})
_ITEM_COMPLETED = "item_completed"
# The events naming a subagent's activity, each by the type the activity it carries is spelled with.
_ACTIVITIES = MappingProxyType({_ITEM_COMPLETED: "SubAgentActivity", "sub_agent_activity": "sub_agent_activity"})


class Line(NamedTuple):
    """Where one line sits in the log, whether the invocation wrote it, and the stamp it was written at."""

    position: int
    own: bool
    stamp: str | None


class Report(NamedTuple):
    """One readable `token_count`: its line, its `info`, the running sum it reports, and whether the last is known."""

    line: Line
    token_info: dict[str, Any]
    running: Counters
    proven: bool


class Envelope(NamedTuple):
    """What one line is read as: its kind, the name of the event it carries where it is one, and its payload."""

    kind: str
    name: str | None
    payload: dict[str, Any]

    @classmethod
    def of(cls, event: dict[str, Any]) -> Envelope | None:
        """A line's envelope, or None where nothing of it can be read: no kind, no payload object, or no event name.

        A line of a kind whose payload is not read -- a `compacted` line, a `response_item` -- is its kind alone.
        """
        kind = event.get(TYPE)
        payload = event.get(PAYLOAD)
        if not isinstance(kind, str):
            return None
        if kind not in _READ:
            return cls(kind, None, {})
        if not isinstance(payload, dict):
            return None
        name = payload.get(TYPE) if kind == _EVENT_MSG else kind
        return cls(kind, name, payload) if isinstance(name, str) else None


@dataclass
class Branch:
    """One branch's state as the log is read: the model in effect, its last running sum, and the requests kept."""

    model: str | None = None
    running: Counters | None = None
    position: int | None = None
    proven: bool = True
    unread_at: int = 0
    kept: int = 0

    def proven_at(self, unread_lines: int) -> bool:
        """Whether its last running sum is the last it reported: no line since then could have been another."""
        return self.proven and unread_lines == self.unread_at

    def advance(self, running: Counters, position: int, unread_lines: int) -> None:
        """Move the branch on to a running sum it just reported."""
        self.running = running
        self.position = position
        self.proven = True
        self.unread_at = unread_lines


@dataclass
class Requests:
    """The requests, running sums, and baseline the log's `token_count` lines settle, branch by branch."""

    session_id: str | None
    scan: request_scan.EventScan
    metadata: request_scan.Metadata
    fallback_model: str | None
    version: str | None = None
    branches: dict[str | None, Branch] = field(default_factory=lambda: {None: Branch()})
    samples: list[request_models.RequestObservation] = field(default_factory=list)
    checkpoints: deque[request_models.UsageCheckpoint] = field(default_factory=deque)
    baseline: request_models.UsageCheckpoint | None = None
    observed_checkpoints: int = 0
    gaps: Counter[str] = field(default_factory=Counter)

    def branch(self, key: str | None) -> Branch | None:
        """The state of the branch `key` names, opened on first use within the branch bound."""
        full = len(self.branches) > self.scan.limits.branches
        if full and key not in self.branches:
            return None
        return self.branches.setdefault(key, Branch())

    def cross(self) -> None:
        """Keep the thread's running sum as the invocation's baseline, where its last before the boundary is known."""
        thread = self.branches[None]
        if thread.running is None or thread.position is None:
            return
        if thread.proven_at(self.scan.unread_lines):
            self.baseline = checkpoint(
                INVOCATION_BASELINE, thread.position, thread.running, self.session_id, self.gaps,
            )
            self.observed_checkpoints += 1

    def lose_track(self) -> None:
        """Leave every branch's last running sum unproven: a line no reading could place may have reported one."""
        for branch in self.branches.values():
            branch.proven = False

    def report(self, line: Line, token_info: Any, turn: Turn | None) -> None:
        """Fold one `token_count` into its branch: a sample where the invocation's line proves a new request.

        An `info` of null is a notification carrying no usage, such as a rate-limit update, so it is nothing; one of a
        child turn naming no id has no branch to be proven in, and the turn it settles in is already a gap.
        """
        if token_info is None or (turn is not None and turn.unnamed_child):
            return
        branch = self.branch(None if turn is None else turn.branch)
        if branch is None:
            self.gaps[coverage.CORRELATION_LIMIT] += line.own
        elif isinstance(token_info, dict):
            self._settle(line, token_info, branch, turn)
        else:
            self.gaps[coverage.MALFORMED_USAGE] += line.own
            branch.proven = False

    def _settle(
        self,
        line: Line,
        token_info: dict[str, Any],
        branch: Branch,
        turn: Turn | None,
    ) -> None:
        """Read a `token_count`'s running sum: a repeat is nothing, and anything else moves its branch on to it."""
        running = Counters.of(token_info.get("total_token_usage"))
        if running is None:
            self.gaps[coverage.MALFORMED_USAGE] += line.own
            branch.proven = False
            return
        report = Report(line, token_info, running, branch.proven_at(self.scan.unread_lines))
        if report.proven and running.repeats(branch.running):
            return
        if line.own:
            self._observe(report, branch, turn)
        branch.advance(running, line.position, self.scan.unread_lines)

    def _observe(self, report: Report, branch: Branch, turn: Turn | None) -> None:
        """Keep the invocation's new request as a sample, and the thread's advanced running sum as a checkpoint."""
        child = turn is not None and turn.parent_turn_id is not None
        if not child:
            self.checkpoints.append(
                checkpoint(CUMULATIVE_TOTAL, report.line.position, report.running, self.session_id, self.gaps),
            )
            self.observed_checkpoints += 1
        own_usage = Counters.of(report.token_info.get("last_token_usage"))
        if own_usage is None:
            self.gaps[coverage.MALFORMED_USAGE] += 1
        elif not report.proven or not report.running.advanced_by(branch.running, own_usage):
            self.gaps[coverage.UNRECONCILED_USAGE] += 1
        elif len(self.samples) >= self.scan.limits.tracked_steps:
            self.gaps[coverage.CORRELATION_LIMIT] += 1
        else:
            observation = self._sample(report, own_usage, branch, turn)
            branch.kept += 1
            self.samples.append(observation)
            self.gaps.update(coverage.observation_gaps(observation, subagent=child))

    def _sample(
        self,
        report: Report,
        own_usage: Counters,
        branch: Branch,
        turn: Turn | None,
    ) -> request_models.RequestObservation:
        """One request as its sample, keyed by the log line that reported it."""
        position = report.line.position
        parent = None if turn is None else turn.parent_turn_id
        return request_models.RequestObservation(
            identity=request_models.RequestIdentity(
                key=f"{NATIVE_LINE}:{position}",
                kind=request_models.NATIVE_POSITION,
                conversation_id=self.session_id,
                session_id=self.session_id,
                turn_id=None if turn is None else turn.turn_id,
                parent_turn_id=parent,
            ),
            position=position,
            branch_order=branch.kept,
            attribution=attribution(
                branch.model, parent is not None, self.fallback_model, report.token_info, self.version,
            ),
            usage=own_usage.normalized(),
            raw=MappingProxyType(own_usage.raw),
            status=request_models.FINAL,
            settlement=SETTLED_BY_TOKEN_COUNT,
            source_timestamp=report.line.stamp,
            source_flags=source_flags(report.token_info, self.metadata),
        )


@dataclass
class Notes:
    """The boundaries the invocation's lines mark, and the subagent threads they name whose logs are their own."""

    session_id: str | None
    limits: request_scan.CollectionLimits
    metadata: request_scan.Metadata
    markers: list[request_models.RequestMarker] = field(default_factory=list)
    child_threads: set[str] = field(default_factory=set)
    gaps: Counter[str] = field(default_factory=Counter)

    def mark(
        self,
        line: Line,
        kind: str,
        model: str | None = None,
        previous: str | None = None,
    ) -> None:
        """Keep an explicit boundary the invocation's line printed, within the marker bound."""
        if not line.own:
            return
        if len(self.markers) >= self.limits.markers:
            self.gaps[coverage.CORRELATION_LIMIT] += 1
            return
        self.markers.append(request_models.RequestMarker(
            kind=kind,
            position=line.position,
            conversation_id=self.session_id,
            model=model,
            previous_model=previous,
        ))

    def noted(self, line: Line, name: str, payload: dict[str, Any]) -> None:
        """Read an event that is neither a turn's boundary nor a request: a reset, or a subagent's activity."""
        marker = _EVENT_MARKERS.get(name)
        if marker is not None:
            self.mark(line, marker)
        elif line.own and name in _ACTIVITIES:
            self._activity(name, payload)

    def _activity(self, name: str, payload: dict[str, Any]) -> None:
        """Note a subagent thread the invocation's activity names: its requests are in a log of its own, never read.

        A paginated history names it in a completed `SubAgentActivity` item, and a legacy one also in a
        `sub_agent_activity` event, for every activity but completion.
        """
        activity = payload.get("item") if name == _ITEM_COMPLETED else payload
        spelled = _ACTIVITIES[name]
        if not isinstance(activity, dict) or activity.get(TYPE) != spelled:
            return
        thread = self.metadata.text(activity.get("agent_thread_id"))
        if thread is None:
            self.gaps[coverage.SUBAGENT_UNIDENTIFIED] += 1
        elif thread in self.child_threads or len(self.child_threads) < self.limits.branches:
            self.child_threads.add(thread)
        else:
            self.gaps[coverage.CORRELATION_LIMIT] += 1


@dataclass
class NativeFold:
    """Every line of one session log folded in order, with the invocation's own lines kept as what they report."""

    timeline: Timeline
    turns: Turns
    requests: Requests
    notes: Notes
    metadata: request_scan.Metadata

    def feed(self, position: int, event: dict[str, Any] | None) -> None:
        """Fold one line in, where it decoded to an event: place it, then read it as whatever kind of line it is.

        A line whose envelope nothing can be read off could have held a running sum, so none is proven past it.
        """
        if event is None:
            return
        line = self._placed(position, event)
        envelope = Envelope.of(event)
        if envelope is None:
            self.notes.gaps[coverage.MALFORMED_ENVELOPES] += line.own
            self.requests.lose_track()
        elif envelope.kind == _EVENT_MSG:
            self._event(line, envelope)
        else:
            self._line(line, envelope)

    def reasons(self) -> Counter[str]:
        """Every gap the read, the fold, and its requests recorded."""
        self.turns.abandon()
        gaps = Counter(self.requests.scan.gaps)
        gaps.update(self.notes.gaps)
        gaps.update(self.requests.gaps)
        sampled = {sample.identity.turn_id for sample in self.requests.samples}
        unexposed = self.turns.own_children - sampled
        gaps[coverage.SUBAGENT_USAGE_UNAVAILABLE] += len(self.notes.child_threads) + len(unexposed)
        gaps[coverage.SUBAGENT_UNIDENTIFIED] += self.turns.unnamed
        gaps[coverage.NO_TERMINAL_RESULT] += self.turns.unclosed
        gaps[coverage.OVERSIZE_METADATA] += self.metadata.oversize
        gaps[coverage.MALFORMED_METADATA] += self.metadata.malformed
        return +gaps

    def _placed(self, position: int, event: dict[str, Any]) -> Line:
        """Where a line sits, and whether it is the invocation's; crossing the boundary keeps the baseline before it."""
        stamp, moment = stamped(event, self.metadata)
        crossing = self.timeline.boundary is None
        line = Line(position, self.timeline.place(position, event, moment), stamp)
        if crossing and line.own:
            self.requests.cross()
        return line

    def _line(self, line: Line, envelope: Envelope) -> None:
        marker = _MARKED.get(envelope.kind)
        if marker is not None:
            self.notes.mark(line, marker)
        elif envelope.kind == _TURN_CONTEXT:
            self._turn_context(line, envelope.payload)
        elif envelope.kind == SESSION_META and line.position == 0:
            self.requests.version = self.timeline.writer_version(envelope.payload, self.metadata)

    def _event(self, line: Line, envelope: Envelope) -> None:
        name = envelope.name or ""
        if name == "task_started":
            self.turns.start(envelope.payload, line.own)
        elif name in _CLOSES:
            self.turns.close(envelope.payload)
        elif name == "token_count":
            self._token_count(line, envelope.payload.get("info"))
        else:
            self.notes.noted(line, name, envelope.payload)

    def _token_count(self, line: Line, token_info: Any) -> None:
        """Hand a `token_count` to its requests, unless the child turns overran their bound before it."""
        if not self.turns.overflowed:
            self.requests.report(line, token_info, self.turns.current(line.own))
        elif token_info is not None:
            self.notes.gaps[coverage.CORRELATION_LIMIT] += line.own

    def _turn_context(self, line: Line, payload: dict[str, Any]) -> None:
        """Set the model the named turn runs on: its own where it is a child, the thread's otherwise."""
        turn_id = self.metadata.text(payload.get(_TURN_ID))
        branch = self.requests.branch(turn_id if turn_id in self.turns.children else None)
        if branch is None:
            return
        model = self.metadata.text(payload.get("model"))
        thread = branch is self.requests.branches[None]
        if thread and model and branch.model and model != branch.model:
            self.notes.mark(line, request_models.MODEL_CHANGE, model, branch.model)
        branch.model = model or request_scan.REFUSED
