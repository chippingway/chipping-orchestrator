# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex request usage: one observation per request the invocation's native session log settled.

`codex exec --json` prints usage only on `turn.completed`, a running sum of the whole thread -- every request of the
turn, and on `exec resume` every request of the earlier invocations too -- so its stdout holds no request to observe,
and that block is never a sample nor a source a request's size is inferred from. The requests are in the session log
codex-cli 0.167.1 writes beside it under `CODEX_HOME`: one `token_count` per request, as `request_codex_counters`
reads it. `collect` reads that log's lines as its caller hands them over, one at a time, beside the facts of the
launch that place the invocation in it, as a `NativeSession`; it reads nothing else, so it does no I/O of its own.

The trajectory dispatch (`trajectory.parse_agent_request_usage`) calls it for every Codex run, handing it the
`NativeSession` the opt-in trajectory sink's reader built at exit: that reader looks the log up and reads it, bounded,
and observed the launch the invocation's facts come from, so with the sink off nothing calls this collector.

What makes a line this invocation's, and which turn each usage line settles in, is `request_codex_scope`'s to prove --
the log has to be the session's own, a resumed run's lines lie past the count its log held at the launch, no stamp may
contradict that, and the root turns the log opened have to be the ones stdout started -- and what the lines report is
`request_codex_fold`'s to read. A collection handed no session, or only the reason none could be read, is unavailable,
and so is one whose log proves nothing of the invocation; each says why, and attributes nothing rather than guessing
which lines are the invocation's, keeping only how many lines its scan read before it knew.

The log reports no request id, so each request is known by the log line that reported it, and every collection lists
that among its `LIMITATIONS`, beside the cache-write lifetimes the log never reports and the cache-write zero it
cannot tell from an unreported count; a resumed run's log was begun by an earlier process, which is the one its
`session_meta` names the version of, so a resumed run's requests name none.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from orchestrator.observability.usage import request_coverage as coverage, request_models, request_scan
from orchestrator.observability.usage.request_codex_fold import NativeFold, Notes, Requests
from orchestrator.observability.usage.request_codex_scope import Invocation, NativeScope

LIMITATIONS = (
    "no-request-ids",
    "no-cache-write-lifetimes",
    "ambiguous-zero-cache-writes",
)
_NO_VERSION = "no-source-version"
_NO_TIMESTAMPS = "no-source-timestamps"
_NO_CAPACITY = "no-context-capacity"


@dataclass(frozen=True)
class NativeSession:
    """One invocation's native session log as its caller hands it over, or why the caller could hand over none.

    `lines` yields each line of the log, numbered by its place in it, one at a time, so no more of the log than one line
    need be held at once -- the newline ending the last line opens none after it, and a line of whitespace alone is one
    the log holds, malformed. A reader holding its own bounds on what it reads records in `scan` -- shared with this
    collection, which decodes the lines into it -- the lines it could not read and any bound that stopped it; with no
    `scan` handed over, the collection decodes into one of its own. `unavailable` is the reason no line was read at all.
    """

    invocation: Invocation
    lines: Iterable[tuple[int, str]] = ()
    scan: request_scan.EventScan | None = None
    unavailable: str | None = None


def _limitations(version: str | None, samples: Sequence[request_models.RequestObservation]) -> tuple[str, ...]:
    """What the source never reported for this collection: `LIMITATIONS`, and what its samples leave out."""
    found = list(LIMITATIONS)
    if version is None:
        found.append(_NO_VERSION)
    if any(sample.source_timestamp is None for sample in samples):
        found.append(_NO_TIMESTAMPS)
    if any(sample.attribution.context_capacity is None for sample in samples):
        found.append(_NO_CAPACITY)
    return tuple(found)


def _unavailable(reason: str, scan: request_scan.EventScan | None) -> coverage.RequestUsage:
    """A collection attributing nothing, beside why, and how many lines it read before it knew."""
    return coverage.RequestUsage(coverage.CollectionCoverage(
        reasons=MappingProxyType({reason: 1}),
        limitations=_limitations(None, ()),
        scanned_lines=0 if scan is None else scan.scanned_lines,
        skipped_lines=0 if scan is None else scan.skipped_lines,
    ))


def _fold(invocation: Invocation, scan: request_scan.EventScan | None, fallback_model: str | None) -> NativeFold:
    """A fold over `invocation`'s log, its scope decoding into the `scan` the reader shares, or into one of its own."""
    scope = NativeScope.of(invocation, scan)
    metadata = scope.metadata
    session_id = metadata.text(invocation.session_id)
    limits = scope.scan.limits
    requests = Requests(
        session_id,
        scope.scan,
        metadata,
        metadata.text(fallback_model),
        checkpoints=deque(maxlen=limits.checkpoints),
    )
    return NativeFold(scope, requests, Notes(session_id, limits, metadata))


def _checkpoints(requests: Requests, bound: int) -> tuple[request_models.UsageCheckpoint, ...]:
    """The baseline the invocation began from, then the last running sums it advanced, kept together within `bound`."""
    opening = () if requests.baseline is None else (requests.baseline,)
    baseline = opening[:bound]
    advanced = tuple(requests.checkpoints)
    dropped = len(advanced) + len(baseline) - bound
    return (*baseline, *advanced[max(dropped, 0):])


def _collected(fold: NativeFold, reasons: Mapping[str, int]) -> coverage.RequestUsage:
    """The requests, markers, and checkpoints the invocation's lines left."""
    requests = fold.requests
    scan = fold.scope.scan
    return coverage.RequestUsage(
        coverage.CollectionCoverage(
            reasons=MappingProxyType(dict(reasons)),
            limitations=_limitations(requests.version, requests.samples),
            scanned_lines=scan.scanned_lines,
            skipped_lines=scan.skipped_lines,
            observed_checkpoints=requests.observed_checkpoints,
        ),
        observations=tuple(requests.samples),
        markers=tuple(fold.notes.markers),
        checkpoints=_checkpoints(requests, scan.limits.checkpoints),
    )


def collect(stdout: str, session: NativeSession | None, fallback_model: str | None = None) -> coverage.RequestUsage:
    """Collect the request usage one Codex invocation's native session log reports, within the collection bounds.

    `stdout` is the invocation's own, read only to count the turns it started; `session` none is an invocation whose
    launch was not observed, so nothing places it in any log.
    """
    if session is None:
        return _unavailable(coverage.NO_LAUNCH_OBSERVATION, None)
    if session.unavailable is not None:
        return _unavailable(session.unavailable, session.scan)
    fold = _fold(session.invocation, session.scan, fallback_model)
    for position, line in session.lines:
        fold.feed(position, line)
    reasons = fold.reasons()
    refusal = fold.scope.refusal(stdout)
    if refusal is not None:
        return _unavailable(refusal, fold.scope.scan)
    return _collected(fold, reasons)
