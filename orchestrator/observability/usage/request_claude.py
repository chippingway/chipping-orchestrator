# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Claude request usage: one observation per API message the process's stream printed, and one per subagent hand-back.

What a message's frames count is pinned to Claude Code 2.1.295, the captures the run accounting is. A message prints
one `assistant` frame per content block, all under its `message.id`, so its blocks are one observation however many
it has, while two messages reporting equal counts stay two. Its counters are folded on `request_claude_messages`: the
closing `message_delta` settles its output, replacing the count it started with, and one no closing report reached
stays provisional. The run accounting and the trajectory's turns settle through the same `ClaudeTurnUsageBuilder`
the stream fold feeds every event to, so a subagent message is settled through `modelUsage` only where they settle it
-- as the model's sole open message, its input and cache totals matching what the stream printed -- and only where
that settlement sums every request this collection holds and this collection's own counts reproduce it. It records
that provenance, while one that evidence leaves ambiguous keeps its provisional start count. Nothing divides a
`result.usage` or `modelUsage` total among requests or makes one request of it: a stream reporting usage only in
aggregate has no observation and an `aggregate-only-usage` gap.

A subagent prints its messages under the call that launched it but no stream events -- a frame naming its agent
without that call is still the subagent's, on a branch of its agent -- and the message that closes it prints no frame
at all: the lead thread's hand-back for that call carries its usage. That hand-back is an observation
of the closing message's output alone (`request-output` scope, an `output-only-observations` gap), correlated by the
call it answers and the subagent's `agentId`, and numbered after every message turn exactly where the trajectory's
turns number it -- where some closing `message_delta` settled a message at all.

Only this process's stream is read, so a resumed run's observations are its own, and so are an ID-less run's:
attributable to the process that printed them whatever identity the stream left out. A request's model and metadata
come from its own frames, never another's: a lead-thread message naming no model falls back to the process's `init`
model and then the configured `--model`, while a subagent's message or hand-back naming none stays `unestablished`,
and so does any message whose frames named only a model this collection refused -- too long to keep, or no string --
since the model it ran on is unknown rather than unnamed.
The process's session, CLI version, and the context window its last `modelUsage` reports for a request's model are
the process's own, so they hold for every request of it. A request whose frames name no message id is known by its
request id, and failing that by the line first printing it; a hand-back answering no named call by its line. Each
branch -- the lead thread, or one subagent call -- keeps its own order, never ordered against another; a message
naming another model than the previous one on its branch is a `model-change` marker, and a `compact_boundary` frame a
`compaction` one.

The trajectory's turn numbering and its settlement are read only where this collection read every line the
trajectory parse did: a scan a bound cut short, or one skipping a line too long to read, may have missed a frame they
counted, so it links no turn and settles nothing through `modelUsage`. Where the turn builder was dropped at the
correlation bound, the turns it linked before stay, while no hand-back turn is numbered and nothing is settled through
`modelUsage`, both of which need every message the stream printed.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from operator import attrgetter
from types import MappingProxyType

from orchestrator.observability.usage import (
    claude_requests,
    protocol,
    request_coverage as coverage,
    request_models,
)
from orchestrator.observability.usage.request_claude_counters import raw_counts
from orchestrator.observability.usage.request_claude_messages import RequestFold
from orchestrator.observability.usage.request_claude_reports import MODEL_KIND, Process
from orchestrator.observability.usage.request_claude_stream import SettledRows, StreamFold, TurnFeed
from orchestrator.observability.usage.request_scan import REFUSED

# What the stream never reports: it prints no reset of the context.
LIMITATIONS = ("no-reset-markers",)
# The bounds whose gap means the scan may have missed a line the trajectory parse read.
_RENUMBERING_GAPS = frozenset((coverage.SCAN_LIMIT, coverage.OVERSIZE_LINES))
_POSITION = attrgetter("position")
# The `modelUsage` totals a settlement through it reads.
_SETTLEMENT_TOTALS = ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens")
# A request the collection never tracked: no count of it is whole.
_UNSEEN = RequestFold(-1)

# Whether a branch is a subagent's, the call that launched it, and -- where no call is named -- the agent it ran as.
Branch = tuple[bool, str | None, str | None]


@dataclass
class Observations:
    """The observations a fold's requests become, in the order the stream first printed them, each branch's apart.

    `linked` says whether the trajectory's numbering and settlement are read at all; where they are, `reconciled` is
    the output `modelUsage` settled each message key to, and `handback_turns` the turn each hand-back key is numbered.
    """

    fold: StreamFold
    fallback_model: str | None
    linked: bool = False
    reconciled: dict[str, int] = field(default_factory=dict)
    handback_turns: dict[str, int] = field(default_factory=dict)
    kept: list[request_models.RequestObservation] = field(default_factory=list)
    orders: Counter[Branch] = field(default_factory=Counter)
    models: dict[Branch, str] = field(default_factory=dict)
    markers: list[request_models.RequestMarker] = field(default_factory=list)
    gaps: Counter[str] = field(default_factory=Counter)

    @classmethod
    def built(cls, fold: StreamFold, fallback_model: str | None) -> Observations:
        observations = cls(fold, fallback_model, linked=_RENUMBERING_GAPS.isdisjoint(fold.scan.gaps))
        if observations.linked and fold.turns.whole:
            observations.settle(fold.turns)
        # A request is opened on its first frame, so the fold holds them in the order the stream first printed them.
        for request in fold.requests.held.values():
            observations.add(request)
        return observations

    def settle(self, turns: TurnFeed) -> None:
        """Read what the trajectory's own settlement established: `modelUsage` outputs, and the hand-back turns."""
        settlement = turns.builder.settlement
        self.reconciled = _reconciled(self.fold, settlement.settled_by_key(turns.builder.by_key))
        if settlement.final_outputs:
            numbered = enumerate(settlement.handbacks, len(turns.builder.turn_index))
            self.handback_turns = {key: turn for turn, key in numbered}

    def add(self, request: RequestFold) -> None:
        if not request.reported:
            self.gaps[coverage.UNREPORTED_USAGE] += 1
            return
        reconciled = None if request.handback else self.reconciled.get(request.key or "")
        settled = request.usage(reconciled)
        branch = (request.subagent, request.branch, None if request.branch else request.names.agent_id)
        observation = request_models.RequestObservation(
            identity=self._identity(request),
            position=request.position,
            branch_order=self.orders[branch],
            attribution=self._attribution(request),
            usage=settled.normalized(),
            raw=MappingProxyType(raw_counts(settled.raw)),
            status=settled.status,
            settlement=settled.settlement,
            scope=request_models.OUTPUT_SCOPE if request.handback else request_models.REQUEST_SCOPE,
            source_timestamp=request.names.timestamp,
        )
        self.orders[branch] += 1
        self.kept.append(observation)
        self.gaps.update(coverage.observation_gaps(observation, subagent=request.subagent))
        self._changed(branch, request)

    def _identity(self, request: RequestFold) -> request_models.RequestIdentity:
        names = request.names
        process = self.fold.process
        if request.handback:
            turn = self.handback_turns.get(request.key or "")
        elif self.linked and request.turn_key == request.key:
            turn = request.turn
        else:
            # A scan that missed frames links none, and a turn numbered under another key holds no output it settled.
            turn = None
        identity, kind = request.labelled()
        return request_models.RequestIdentity(
            key=identity,
            kind=kind,
            session_id=names.session_id or process.session_id,
            message_id=names.message_id,
            request_id=names.request_id,
            agent_id=names.agent_id,
            parent_tool_use_id=request.branch,
            subagent_type=process.launched.get(request.branch or ""),
            trajectory_turn=turn,
        )

    def _attribution(self, request: RequestFold) -> request_models.RequestAttribution:
        process = self.fold.process
        model, source = self._model(request)
        return request_models.RequestAttribution(model, source, process.capacity(model), process.version)

    def _model(self, request: RequestFold) -> tuple[str | None, str]:
        """The model a request's own frames name; on the lead thread alone, the process's or the configured one.

        A model its frames named that this collection refused leaves it unknown, never one the process named.
        """
        named = request.names.model
        if named:
            return named, request_models.STREAM_MODEL
        if request.subagent or named == REFUSED:
            return None, request_models.UNESTABLISHED
        if self.fold.process.model is not None:
            return self.fold.process.model, request_models.STREAM_MODEL
        fallback = self.fold.process.metadata.text(self.fallback_model)
        if fallback is not None:
            return fallback, request_models.CONFIGURED_FALLBACK
        return None, request_models.UNAVAILABLE

    def _changed(self, branch: Branch, request: RequestFold) -> None:
        """Mark a request naming another model than the previous one its branch named, within the marker bound."""
        model = request.names.model
        previous = self.models.get(branch, model)
        if not model:
            return
        self.models[branch] = model
        if previous == model:
            return
        process = self.fold.process
        kept = len(process.markers) + len(self.markers)
        if kept >= process.limits.markers:
            self.gaps[coverage.CORRELATION_LIMIT] += 1
            return
        self.markers.append(request_models.RequestMarker(
            request_models.MODEL_CHANGE,
            request.position,
            model=model,
            previous_model=previous,
            parent_tool_use_id=request.branch,
        ))


def _model_totals(process: Process, model: str) -> tuple[int, ...] | None:
    """The context input, cache reads, cache writes, and output the last `modelUsage` reports for `model`, as read here.

    None where any total a settlement reads is no whole count here.
    """
    totals = process.model_usage.get(model)
    readings = MODEL_KIND.readings(totals) if isinstance(totals, dict) else {}
    reported = [readings.get(name) for name in _SETTLEMENT_TOTALS]
    if not all(reading is not None and reading.known for reading in reported):
        return None
    counted = tuple(reading.count or 0 for reading in reported if reading is not None)
    return (sum(counted[:-1]), *counted[1:])


def _holds(fold: StreamFold, model: str, settled: SettledRows, output: int) -> bool:
    """Whether the counts this collection reads settle `model`'s open message to `output`, as the accounting did.

    The settlement is recomputed from them: the model's totals must equal what the summed requests' prompts add up to
    class by class, and what its output total leaves beyond the other requests' outputs must be `output`. The
    accounting reads some counters differently -- a fraction truncated, a string-spelled lifetime left out -- so a
    settlement this collection's own counts do not reproduce is evidence it refuses.
    """
    totals = _model_totals(fold.process, model)
    counted = [
        fold.requests.get(key, _UNSEEN).counts(output=sums_output)
        for key, sums_output in fold.turns.summed(model, settled)
    ]
    if totals is None or None in counted:
        return False
    sums = [sum(column) for column in zip(*counted, strict=True)]
    if sums[:-1] != list(totals[:-1]):
        return False
    return totals[-1] - sums[-1] == output


def _reconciled(fold: StreamFold, settled: SettledRows) -> dict[str, int]:
    """The output `modelUsage` settled each message key to, where this collection's own counts reproduce it.

    Only a settlement summing every request this collection tracked settles any: one the stream printed but the
    settlement left out could hold the remainder it found.
    """
    if not fold.turns.sums_all(fold.requests.summable(), settled):
        return {}
    reconciled = {
        key: settled_row
        for key, settled_row in settled.items()
        if settled_row.settlement == claude_requests.SETTLED_BY_MODEL_USAGE
    }
    return {
        key: settled_row.counts.get(protocol.OUTPUT, 0)
        for key, settled_row in reconciled.items()
        if _holds(fold, settled_row.model, settled, settled_row.counts.get(protocol.OUTPUT, 0))
    }


def _reasons(fold: StreamFold, observations: Observations) -> MappingProxyType[str, int]:
    """Every gap the scan, the fold, the process reports, and the observations recorded, each with how often."""
    process = fold.process
    gaps = Counter(fold.scan.gaps)
    for recorded in (fold.gaps, fold.requests.gaps, process.gaps, observations.gaps):
        gaps.update(recorded)
    handbacks = [request for request in fold.requests.held.values() if request.handback]
    unanswered = set(process.launched).difference(request.branch for request in handbacks)
    gaps[coverage.SUBAGENT_USAGE_UNAVAILABLE] += len(unanswered)
    # A subagent's request naming no call it was launched by sits on no established branch.
    gaps[coverage.SUBAGENT_UNIDENTIFIED] += sum(
        request.subagent and request.branch is None for request in fold.requests.held.values()
    )
    gaps[coverage.OVERSIZE_METADATA] += process.metadata.oversize
    gaps[coverage.MALFORMED_METADATA] += process.metadata.malformed
    gaps[coverage.NO_STREAM_EVENTS] += not fold.envelopes
    gaps[coverage.NO_TERMINAL_RESULT] += bool(fold.envelopes) and not process.terminals
    gaps[coverage.AGGREGATE_ONLY_USAGE] += process.aggregate_usage and not observations.kept
    return MappingProxyType(dict(+gaps))


def _limitations(fold: StreamFold, samples: list[request_models.RequestObservation]) -> tuple[str, ...]:
    """What the source never reports, and the identities and metadata this stream left out."""
    identities = [sample.identity for sample in samples]
    subagents = [named for named in identities if named.parent_tool_use_id is not None]
    absent = {
        "no-session-id": not (fold.process.session_id or any(named.session_id for named in identities)),
        "no-message-id": any(named.message_id is None for named in identities),
        "no-agent-id": any(named.agent_id is None for named in subagents),
        "no-source-version": fold.process.version is None,
        "no-source-timestamps": not any(sample.source_timestamp for sample in samples),
        "no-context-capacity": not any(sample.attribution.context_capacity for sample in samples),
    }
    return (*LIMITATIONS, *(code for code, missing in absent.items() if missing))


def collect(stdout: str, fallback_model: str | None = None) -> coverage.RequestUsage:
    """Collect the request usage one Claude process's stdout reports, within the collection bounds."""
    fold = StreamFold.read(stdout)
    observations = Observations.built(fold, fallback_model)
    markers = [*fold.process.markers, *observations.markers]
    markers.sort(key=_POSITION)
    return coverage.RequestUsage(
        coverage.CollectionCoverage(
            reasons=_reasons(fold, observations),
            limitations=_limitations(fold, observations.kept),
            scanned_lines=fold.scan.scanned_lines,
            skipped_lines=fold.scan.skipped_lines,
            observed_checkpoints=fold.process.observed_checkpoints,
        ),
        observations=tuple(observations.kept),
        markers=tuple(markers),
        checkpoints=tuple(fold.process.checkpoints),
    )
