# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One pass over a Codex native session log: the models its turns run on, the requests it settles, the running sums
beside them, the boundaries it marks, and the subagent threads it names.

Every line is read, the earlier invocations' as much as this one's, since what the invocation's lines mean depends on
what came before them: the model the thread's last `turn_context` set, and the running sum its last `token_count`
left. Which lines are the invocation's, what each is read as, and the turn -- and so the branch, a child turn's own or
the thread's -- each usage line settles in are the `request_codex_scope` scope's to say, which follows the turns with
`request_codex_turns`; only the invocation's own lines become samples, markers, and checkpoints.

Models. A `turn_context` sets the model the turn it names runs on: a child turn's own, where it names a child the log
named, or the thread's, where it names the thread's open root turn, which holds until the next one; one naming any other
turn sets no model, since nothing places it, and the invocation's is a `conversation-ambiguous` gap. A request that
settles before its turn's own `turn_context` -- the compaction a model switch runs first, on the model the thread had --
ran on the thread's model as the last one left it. A child turn without a `turn_context` of its own ran on no model this
log establishes, never its parent's; a thread with none falls back to the configured `-m` model. A line this pass could
not read could have been a `turn_context`, so past it no branch runs on a model this log establishes, the thread's
included, until a `turn_context` of its own names one. A `turn_context` naming another model than the last one its
branch ran on is a `model-change` marker -- a child turn's naming that turn and the one it was started from -- a
`compacted` line a `compaction` marker, and a `thread_rolled_back` event a `reset` marker.

Requests. `request_codex_settlement.Report.settle` decides whether a `token_count` repeats a notification or proves a
new request, and which usage record on its branch it answers. The fold applies both decisions from the same reading of
the pending records. Each sample takes its counters from the report's `last_token_usage`. The thread's running sums
are checkpoints of the whole conversation, including its proven baseline at the invocation boundary. A child turn's
sums are used only to establish its requests. Earlier invocations' reports also establish their branches' floors.

A repeat still carries evidence about its request and holds its branch's floor. After compaction the CLI can repeat
the sum with a context estimate, whose total measures the estimated context. A report that advances the branch
without proving a request leaves a gap, as does an unanswered usage record of this invocation. Records past the request
bound are counted on their branch without their counters. Earlier records are retained up to the branch bound, with
one unplaced record standing for any overflow. A record placed on no branch stays unanswered.

Subagents. A child turn the invocation opened that settled no request, and a subagent thread its lines name -- in an
`item_completed` `SubAgentActivity`, or in a legacy history's `sub_agent_activity` event -- whose requests are in a log
of that thread's own, which this pass never reads, are usage this collection saw happen and could not observe, so each
is a gap rather than a silence; so is a child turn naming no id, whose requests no branch can keep, whether or not any
settles in it.

Checkpoints are held to a request's arithmetic, so a running sum reporting a counter no usable count, or contradicting
its own parts, is a gap of the collection keeping it as well as its own evidence; a child turn's running sum, kept as no
checkpoint, is the gap alone.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from operator import delitem
from types import MappingProxyType
from typing import Any

from orchestrator.observability.usage import (
    request_codex_scope as native,
    request_coverage as coverage,
    request_models,
    request_scan,
)
from orchestrator.observability.usage.request_codex_counters import (
    LAST_USAGE,
    RUNNING_SUM,
    Counters,
    attribution,
    checkpoint,
    detached_gaps,
    report_metadata,
    usage_gaps,
)
from orchestrator.observability.usage.request_codex_settlement import RecordMatch, Report
from orchestrator.observability.usage.request_codex_turns import TURN_ID, UNPLACED, Turn
from orchestrator.observability.usage.request_normalization import Reading

SETTLED_BY_TOKEN_COUNT = "token-count"
CUMULATIVE_TOTAL = "cumulative-total"
INVOCATION_BASELINE = "invocation-baseline"
NATIVE_LINE = "rollout-line"
_MARKED = MappingProxyType({"compacted": request_models.COMPACTION})
_EVENT_MARKERS = MappingProxyType({"thread_rolled_back": request_models.RESET})
_ITEM_COMPLETED = "item_completed"
# A counter's reading in a running sum of nothing at all, and in one that reports no count of it.
_ZERO = Reading.of(0)
_UNKNOWN = Reading()
_USAGE = "usage"
# The one counter the context estimate the CLI follows a compaction with moves: a total beside parts all zero.
_ESTIMATED = frozenset(("total_tokens",))
# The events naming a subagent's activity, each by the type the activity it carries is spelled with.
_ACTIVITIES = MappingProxyType({_ITEM_COMPLETED: "SubAgentActivity", "sub_agent_activity": "sub_agent_activity"})


@dataclass
class Branch:
    """One branch's state as the log is read: the model in effect, its last running sum, and the requests kept.

    `earlier` holds the counters of the earlier invocations' usage records written on it that no report has answered
    yet, in the order the log holds them, and `pending` the invocation's own: requests settled that no `token_count`
    has reported, the sum lagging them until one does -- `unkept` counting the ones after them kept past the request
    bound, whose counters are not. Only a later report of the branch itself whose running sum rises
    past the most its earlier reports establish -- the one evidence it repeats nothing -- answers one, since a report
    of another branch establishes nothing of this one's records: so two records before a single report leave one
    unanswered, and the sum behind it. `compacted` is whether a compaction followed that sum, after which the CLI
    reports a context estimate repeating it. `floor` is the least each counter of its running sum is established to
    hold: the most any of its reports gave, or, where the last gave none, the floor before it and the request it proved
    since, an earlier invocation's included, and never less than a request any of its reports gave, proven or not, so a
    sum leaving a counter out -- or giving less of it -- still cannot shrink below its requests.
    `opening` is the running sum the invocation began from -- none, for nothing at all -- where `reconcilable` holds
    that it is known, and `last_own` the request usage its last report gave, which a repeat of it gives again.
    `reported` is whether it took any report at all, an earlier invocation's included -- one naming no running sum, or
    whose `info` is no object, as much as one whose sum it kept -- which a report of another branch could repeat.
    """

    model: str | None = None
    running: Counters | None = None
    reported: bool = False
    position: int | None = None
    proven: bool = True
    unread_at: int = 0
    earlier: list[Counters | None] = field(default_factory=list)
    pending: deque[Counters | None] = field(default_factory=deque)
    unkept: int = 0
    floor: dict[str, int] = field(default_factory=dict)
    compacted: bool = False
    opening: Counters | None = None
    reconcilable: bool = False
    last_own: Counters | None = None
    kept: int = 0

    def contradicted_by(self, repeated: Counters | None) -> bool:
        """Whether a repeat of its last report gives request usage that report did not.

        The context estimate after a compaction repeats the sum with usage of its own, so a compaction since sets
        nothing to compare against, and nor does the boundary or a reset, where `last_own` is cleared.
        """
        if repeated is None or self.last_own is None or self.compacted:
            return False
        return repeated.readings != self.last_own.readings

    def unreconciled(self, samples: Sequence[request_models.RequestObservation]) -> bool:
        """Whether the invocation's requests kept on the thread fail to add up to what its last running sum advanced
        past the one it began from, on every counter all of them, and both sums, report a count of.

        Only a known opening is reconciled, and only with no gap beside it, so a resumed run's broader total is never
        forced to match requests the collection already says it missed.
        """
        if not self.reconcilable or self.running is None:
            return False
        kept = [sample.raw for sample in samples if sample.identity.parent_turn_id is None]
        readings = self.running.readings.items()
        return any(self._disagrees(counter, reading, kept) for counter, reading in readings)

    def proven_at(self, unread_lines: int) -> bool:
        """Whether its last running sum is the last it reported: no line since then could have been another."""
        return self.proven and unread_lines == self.unread_at

    def advance(self, running: Counters, position: int, unread_lines: int, gained: Counters | None = None) -> None:
        """Move the branch on to a running sum it just reported, beside the request it proved, `gained`, if any.

        The sum is held to its floor first, the request its last report gave, `last_own`, included.
        """
        self.hold(running, self.last_own, gained)
        self.running = running
        self.position = position
        self.unread_at = unread_lines
        self.compacted = False

    def hold(
        self,
        running: Counters,
        reported: Counters | None,
        gained: Counters | None = None,
        estimate: bool = False,
    ) -> None:
        """Hold the floor to a running sum the branch reported, a repeat of its last included, and judge the sum by it.

        Each counter is held at the count the sum gives, never below the floor, or, where it gives none, at the floor
        and the count of the request proved beside it, `gained` -- and, proved or not, at no less than the count of the
        request `reported` beside it, which the sum holds however often it was counted -- but for the context estimate
        the CLI follows a compaction with, moving its total alone, `estimate`, which is no request. A sum never shrinks,
        so one holding less of a counter than that floor contradicts the reports before it, an earlier invocation's as
        much as this one's, or its own: the branch is left unproven, and no report is proven to advance it, nor a
        baseline kept at it, until one has reported where it stands. The floor is the whole number its reports add up
        to, compared as it is rather than read again as a reported count, so one grown past the digits a count may have
        still holds the sum.
        """
        proved = MappingProxyType({}) if gained is None else gained.readings
        held = (
            MappingProxyType({})
            if reported is None or (estimate and self.compacted)
            else reported.readings
        )
        self.floor.update({
            counter: self.floor.get(counter, 0) + (reading.count or 0)
            for counter, reading in proved.items()
            if reading.known and not running.readings.get(counter, _UNKNOWN).known
        })
        for part in (running.readings, held):
            self.floor.update({
                counter: max(self.floor.get(counter, 0), reading.count or 0)
                for counter, reading in part.items()
                if reading.known
            })
        self.proven = not any(
            self.floor.get(counter, 0) > (reading.count or 0)
            for counter, reading in running.readings.items()
            if reading.known
        )

    def _disagrees(self, counter: str, reading: Reading, kept: Sequence[Mapping[str, int]]) -> bool:
        """Whether the requests kept, every one reporting `counter`, add up to other than the running sum's move."""
        if self.opening is None:
            before = _ZERO
        else:
            before = self.opening.readings.get(counter, _UNKNOWN)
        counts = [raw.get(counter) for raw in kept]
        if not (reading.known and before.known) or None in counts:
            return False
        moved = sum(count or 0 for count in counts)
        return (before.count or 0) + moved != reading.count


@dataclass
class Requests:
    """The requests, running sums, and baseline the log's `token_count` lines settle, branch by branch.

    `unplaced` holds the counters of the earlier invocations' usage records no branch was placed for, which no report
    can be shown to answer, so they are never answered, and `held` counts those and the ones branches await a report of,
    as `recorded` counts the invocation's own records kept with their counters. While an earlier one is left, the thread
    keeps no baseline, and a report coming late could settle in whatever turn is open -- a child turn the invocation
    opens included -- so no report of the invocation's giving counters such a record could repeat is proven new, on any
    branch.
    """

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
    unplaced: list[Counters | None] = field(default_factory=list)
    held: int = 0
    recorded: int = 0
    lost: bool = False
    gaps: Counter[str] = field(default_factory=Counter)

    def branch(self, key: str | None) -> Branch | None:
        """The state of the branch `key` names, opened on first use within the branch bound."""
        full = len(self.branches) > self.scan.limits.branches
        if full and key not in self.branches:
            return None
        return self.branches.setdefault(key, Branch(proven=not self.lost))

    def cross(self) -> None:
        """Keep the thread's running sum as the invocation's baseline, where its last before the boundary is known.

        A request the earlier lines settled that no report answered -- a usage record beyond the reports after it,
        however many records came before the last one, on any branch or on none -- leaves it behind, nothing at all
        included, so no baseline is established, and no report of the invocation's is proven to advance it until one
        has reported where it stands and none of those records is left for a report of the invocation's to answer. A
        last sum shrinking below an earlier one contradicts it, and is no baseline either.
        """
        thread = self.branches[None]
        thread.last_own = None
        if self.held or self.unplaced:
            thread.proven = False
            return
        thread.reconcilable = thread.proven_at(self.scan.unread_lines)
        thread.opening = thread.running
        if thread.running is None or thread.position is None:
            return
        if thread.reconcilable:
            self.baseline = checkpoint(
                INVOCATION_BASELINE, thread.position, thread.running, self.session_id, self.gaps,
            )
            self.observed_checkpoints += 1

    def lose_track(self, models: bool = False) -> None:
        """Leave every branch's last running sum unproven: a report no reading could place may have moved one on.

        A branch opened after it is opened unproven too, since that report could be one its first repeats, which
        settles in whatever turn is open by then. With `models`, every branch's model is unknown too -- a line no
        reading could place may have been a `turn_context` -- until one of its own names it again.
        """
        self.lost = True
        for branch in self.branches.values():
            branch.proven = False
            if models:
                branch.model = request_scan.REFUSED

    def report(self, line: native.Line, token_info: Any, turn: Turn | None) -> None:
        """Fold one `token_count` carrying usage into its branch: a sample where the invocation's line proves a new
        request.

        One of a child turn naming no id has no branch to be proven in, the turn it settles in a gap already, and one
        past the branch bound none to be kept in; the invocation's has its evidence judged all the same. Either, an
        earlier invocation's included, could be repeated in whatever turn is open later, with a running sum no branch
        kept, so no branch's running sum is proven past it, nor the first report of a branch opened after it.
        """
        unnamed = turn is not None and turn.unnamed_child
        key = None if turn is None else turn.branch
        branch = None if unnamed else self.branch(key)
        if branch is None:
            self.gaps[coverage.CORRELATION_LIMIT] += line.own and not unnamed
            if line.own:
                self.gaps.update(detached_gaps(token_info, self.metadata))
            self.lose_track()
            return
        # Whatever it carries, a report another branch's could repeat once this branch has taken it.
        branch.reported = True
        if isinstance(token_info, dict):
            self._settle(line, token_info, branch, turn)
        else:
            self.gaps[coverage.MALFORMED_USAGE] += line.own
            branch.proven = False

    def _settle(
        self,
        line: native.Line,
        token_info: dict[str, Any],
        branch: Branch,
        turn: Turn | None,
    ) -> None:
        """Apply a readable report's settlement. Every report of this invocation also contributes its evidence,
        including a repeat or a report whose running sum is missing.
        """
        details = report_metadata(token_info, self.metadata) if line.own else (None, None)
        running = Counters.of(token_info.get(RUNNING_SUM))
        if running is None:
            if line.own:
                self.gaps.update(usage_gaps(token_info) | {coverage.MALFORMED_USAGE})
            branch.proven = False
            return
        report = Report(line, token_info, running, *details)
        settlement = report.settle(branch, self)
        if settlement.repeated:
            if line.own:
                self.gaps.update(usage_gaps(token_info, running, branch.compacted))
                self.gaps[coverage.CONFLICTING_COUNTERS] += branch.contradicted_by(report.own)
            branch.hold(running, report.own, estimate=report.moving <= _ESTIMATED)
            return
        _consume(self, branch, settlement.record)
        if line.own:
            self._observe(report, branch, turn, settlement.gained)
        branch.last_own = report.own
        branch.advance(running, line.position, self.scan.unread_lines, settlement.gained)

    def _observe(self, report: Report, branch: Branch, turn: Turn | None, gained: Counters | None) -> None:
        """Keep the proven request within the sample bound and record the evidence of every advanced sum."""
        child = turn is not None and turn.parent_turn_id is not None
        if child:
            child_evidence = report.running.evidence()
            self.gaps.update(coverage.evidence_gaps(child_evidence.values()))
        else:
            self.checkpoints.append(
                checkpoint(CUMULATIVE_TOTAL, report.line.position, report.running, self.session_id, self.gaps),
            )
            self.observed_checkpoints += 1
        if report.own is None:
            self.gaps[coverage.MALFORMED_USAGE] += 1
            return
        if gained is not None and len(self.samples) < self.scan.limits.tracked_steps:
            observation = self._sample(report, gained, branch, turn)
            branch.kept += 1
            self.samples.append(observation)
            self.gaps.update(coverage.observation_gaps(observation, subagent=child))
            return
        self.gaps[coverage.UNRECONCILED_USAGE if gained is None else coverage.CORRELATION_LIMIT] += 1
        self.gaps.update(usage_gaps(report.token_info, report.running, floor=branch.floor))

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
                branch.model, parent is not None, self.fallback_model, report.capacity, self.version,
            ),
            usage=own_usage.normalized(),
            raw=MappingProxyType(own_usage.raw),
            status=request_models.FINAL,
            settlement=SETTLED_BY_TOKEN_COUNT,
            source_timestamp=report.line.stamp,
            source_flags=report.flags,
        )


def _consume(requests: Requests, branch: Branch, record: RecordMatch | None) -> None:
    """Remove the selected record and release its place in the corresponding retention bound."""
    if record is None:
        return
    if record.queue == "pending":
        delitem(branch.pending, record.index)
        requests.recorded -= 1
    elif record.queue == "unkept":
        branch.unkept -= 1
    else:
        branch.earlier.pop(record.index)
        requests.held -= 1


def _hold(requests: Requests, branch: Branch | None, own: bool, payload: Any) -> None:
    """Leave a usage record awaiting a report, with its counters, the usage of its `payload`.

    The invocation's own is kept on its `branch`, where it has one, within the request bound: past it, and behind one
    past it on the same branch, a record is counted without its counters, a `correlation-limit` gap, so it still awaits
    a report. An earlier invocation's is kept on its branch, or among the ones placed on no branch, within the branch
    bound: no more of those are told apart than branches are, and past it one record ruling nothing out stands, on no
    branch, for every one dropped, so no report of the invocation's is proven new.
    """
    usage = payload.get(_USAGE) if isinstance(payload, dict) else None
    counters = Counters.of(usage)
    limits = requests.scan.limits
    if own and branch is not None:
        overflowing = branch.unkept > 0 or requests.recorded >= limits.tracked_steps
        branch.unkept += overflowing
        requests.gaps[coverage.CORRELATION_LIMIT] += overflowing
        if not overflowing:
            branch.pending.append(counters)
            requests.recorded += 1
        return
    if own:
        return
    records = requests.unplaced if branch is None else branch.earlier
    if requests.held < limits.branches:
        records.append(counters)
        requests.held += 1
    elif None not in requests.unplaced:
        requests.unplaced.append(None)


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
        line: native.Line,
        kind: str,
        models: tuple[str, str] | None = None,
        turn: Turn | None = None,
    ) -> None:
        """Keep an explicit boundary the invocation's line printed, within the marker bound.

        `models` is the model a `model-change` moves to and the one it moves from, and `turn` the child turn whose
        branch it bounds, where it is not the thread's.
        """
        if not line.own:
            return
        if len(self.markers) >= self.limits.markers:
            self.gaps[coverage.CORRELATION_LIMIT] += 1
            return
        model, previous = models or (None, None)
        self.markers.append(request_models.RequestMarker(
            kind=kind,
            position=line.position,
            conversation_id=self.session_id,
            model=model,
            previous_model=previous,
            turn_id=None if turn is None else turn.turn_id,
            parent_turn_id=None if turn is None else turn.parent_turn_id,
        ))

    def noted(self, line: native.Line, name: str, payload: dict[str, Any]) -> None:
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
        if not isinstance(activity, dict) or activity.get(native.TYPE) != spelled:
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
    """Every line of one session log folded in order, with the invocation's own lines kept as what they report.

    `scope` places each line and settles its usage in a turn, decoding into the scan its reader shares, and its
    metadata counts every value this pass refused, so the requests and notes record theirs in the same one.
    """

    scope: native.NativeScope
    requests: Requests
    notes: Notes

    def feed(self, position: int, raw_line: str) -> None:
        """Fold one line in, where it decodes to an event: the scope places it, then it is read as whatever kind of line
        it is.

        A line no reading could place -- one the scan left unread, or whose envelope nothing can be read off -- could
        have been any line: a running sum, a turn opened or closed, a model set. So no running sum is proven past it,
        and no branch runs on a model this log establishes until a `turn_context` of its own names one; which turns are
        open is the scope's to lose. A line the scan left unread is noticed once the line after it is placed, before
        that one is read as anything: a baseline crossed there is already unproven past it.
        """
        crossing = self.scope.timeline.boundary is None
        line = self.scope.read(position, raw_line)
        if line is None:
            return
        if crossing and line.own:
            # The first of the invocation's lines keeps the baseline the earlier lines left.
            self.requests.cross()
        if line.lost:
            self.requests.lose_track(models=True)
        envelope = line.envelope
        if envelope is None:
            self.notes.gaps[coverage.MALFORMED_ENVELOPES] += line.own
        elif envelope.kind == native.EVENT_MSG:
            self._event(line, envelope)
        elif envelope.kind == native.USAGE_RECORD:
            self._record(line)
        else:
            self._line(line, envelope)

    def reasons(self) -> Counter[str]:
        """Every gap the read, the scope, the fold, and its requests recorded."""
        self.scope.turns.abandon()
        gaps = Counter(self.scope.scan.gaps)
        gaps.update(self.notes.gaps)
        gaps.update(self.requests.gaps)
        sampled = {sample.identity.turn_id for sample in self.requests.samples}
        unexposed = self.scope.turns.own_children - sampled
        gaps[coverage.SUBAGENT_USAGE_UNAVAILABLE] += len(self.notes.child_threads) + len(unexposed)
        gaps[coverage.SUBAGENT_UNIDENTIFIED] += self.scope.turns.unnamed
        gaps[coverage.CORRELATION_LIMIT] += self.scope.turns.refused
        # Every request the CLI settles writes one `token_usage_record` beside the `token_count` reporting it, so a
        # record beyond its branch's reports whose sums rose is usage this collection cannot observe.
        awaiting = [
            len(branch.pending) + branch.unkept
            for branch in self.requests.branches.values()
        ]
        gaps[coverage.UNSUPPORTED_USAGE_SOURCE] += sum(awaiting)
        gaps[coverage.NO_TERMINAL_RESULT] += self.scope.turns.unclosed
        gaps[coverage.OVERSIZE_METADATA] += self.scope.metadata.oversize
        gaps[coverage.MALFORMED_METADATA] += self.scope.metadata.malformed
        settled = +gaps
        if not settled and self.requests.branches[None].unreconciled(self.requests.samples):
            settled[coverage.UNRECONCILED_USAGE] += 1
        return settled

    def _record(self, line: native.Line) -> None:
        """Note a usage record on the branch of the turn the scope settles it in.

        No request is read off a record, but its shape is evidence: a payload that is no object is a malformed
        envelope, a usage block naming no counter malformed usage, and the invocation's counter no whole count, or its
        own parts contradict, an invalid or conflicting one. Each is still a request settled, so it is a record all the
        same, in the innermost open turn where it names none -- one left before the boundary leaves the running sum
        behind like any. A record the scope settles in no turn, one in a child turn naming no id, and one in a turn
        whose parentage is unproven have no branch, which is never guessed: the invocation's own such turn is a gap
        already, or the report after it is, while an earlier invocation's is answered by no report, since none can be
        shown to be its own, so no report of the invocation's giving counters it could repeat is proven new on any
        branch.
        """
        payload = line.event.get(native.PAYLOAD)
        if not isinstance(payload, dict):
            self.notes.gaps[coverage.MALFORMED_ENVELOPES] += line.own
        elif line.own:
            # A record's usage is judged as any request usage is, though no sample is ever read off it.
            self.requests.gaps.update(usage_gaps({LAST_USAGE: payload.get(_USAGE)}))
        turn = line.settled
        if turn is UNPLACED or (turn is not None and (turn.unnamed_child or turn.unplaced)):
            branch = None
        else:
            branch = self.requests.branch(None if turn is None else turn.branch)
        _hold(self.requests, branch, line.own, payload)

    def _line(self, line: native.Line, envelope: native.Envelope) -> None:
        marker = _MARKED.get(envelope.kind)
        if marker is not None:
            self.notes.mark(line, marker)
            self.requests.branches[None].compacted = True
        elif envelope.kind == native.TURN_CONTEXT:
            self._turn_context(line, envelope.payload)
        elif envelope.kind == native.SESSION_META and line.position == 0:
            self.requests.version = self.scope.timeline.writer_version(envelope.payload, self.scope.metadata)

    def _event(self, line: native.Line, envelope: native.Envelope) -> None:
        name = envelope.name or ""
        if name == native.TOKEN_COUNT:
            self._token_count(line, envelope.payload.get("info"))
        elif name in _EVENT_MARKERS:
            # A reset is a boundary no repeat of an earlier report crosses.
            self.notes.noted(line, name, envelope.payload)
            self.requests.branches[None].last_own = None
        else:
            self.notes.noted(line, name, envelope.payload)

    def _token_count(self, line: native.Line, token_info: Any) -> None:
        """Hand a `token_count` to its requests, in the turn the scope settled it in.

        An `info` of null is a notification carrying no usage, such as a rate-limit update, so it is nothing. A report
        the scope settles in no turn is guessed into none: past the child turn bound the invocation's is a
        `correlation-limit` gap; otherwise nothing told which of several open turns it is, or which turns are open, and
        the invocation's is a `conversation-ambiguous` gap. Either way, an earlier invocation's included, it could have
        moved any branch on, or be repeated in whatever turn is open later, so no branch's running sum is proven past
        it, nor the first report of a branch opened after it.
        """
        if token_info is None:
            return
        turn = line.settled
        if turn is not UNPLACED:
            self.requests.report(line, token_info, turn)
            return
        if line.own:
            # A report no branch takes is evidence all the same.
            self.notes.gaps.update(detached_gaps(token_info, self.scope.metadata))
        if self.scope.turns.overflowed:
            self.notes.gaps[coverage.CORRELATION_LIMIT] += line.own
        else:
            self.notes.gaps[coverage.CONVERSATION_AMBIGUOUS] += line.own
        self.requests.lose_track()

    def _turn_context(self, line: native.Line, payload: dict[str, Any]) -> None:
        """Set the model the open turn a `turn_context` names runs on: a child turn's own, or the thread's root turn's.

        A context naming no open turn -- or, of the invocation's, one it did not open -- sets no model, since nothing
        places it, and the invocation's is a `conversation-ambiguous` gap. A model naming another than the one its
        branch last ran on is a `model-change` of that branch -- a child turn's carrying its turn and the turn it was
        started from.
        """
        metadata = self.scope.metadata
        turn = self.scope.turns.named(metadata.text(payload.get(TURN_ID)))
        if turn is None or turn.unplaced or (line.own and not turn.own):
            self.notes.gaps[coverage.CONVERSATION_AMBIGUOUS] += line.own
            return
        branch = self.requests.branch(turn.branch)
        if branch is None:
            return
        model = metadata.text(payload.get("model"))
        if model and branch.model and model != branch.model:
            child = None if turn.parent_turn_id is None else turn
            self.notes.mark(line, request_models.MODEL_CHANGE, (model, branch.model), child)
        branch.model = model or request_scan.REFUSED
