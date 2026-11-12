# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Codex request usage: one observation per request the invocation's native session log settled.

`codex exec --json` prints usage only on `turn.completed`, a running sum of the whole thread -- every request of the
turn, and on `exec resume` every request of the earlier invocations too -- so its stdout holds no request to observe,
and that block is never a sample nor a source a request's size is inferred from. The requests are in the session log
codex-cli 0.167.1 writes beside it under `CODEX_HOME`: one `token_count` per request, as `request_codex_counters`
reads it. `collect` reads that log's lines as its caller hands them over, one at a time, beside the facts of the
launch that place the invocation in it, as a `NativeSession`; it reads nothing else, so it does no I/O of its own.

The collector is dormant: the trajectory dispatch does not call it yet, so a Codex trajectory record still collects
no request usage, and only a direct caller -- its tests -- reads a log through it.

What makes a line this invocation's is `request_codex_scope`'s to prove -- the log has to be the session's own, a
resumed run's lines lie past the count its log held at the launch, and no stamp may contradict that -- and what the
lines report is `request_codex_fold`'s to read. A collection handed no session, or only the reason none could be
read, is unavailable, and so is one whose log proves nothing of the invocation; each says why, and attributes nothing
rather than guessing which lines are the invocation's.

The log reports no request id, so each request is known by the log line that reported it, and every collection lists
that among its `LIMITATIONS`, beside the cache-write lifetimes the log never reports and the cache-write zero it
cannot tell from an unreported count; a resumed run's log was begun by an earlier process, which is the one its
`session_meta` names the version of, so a resumed run's requests name none.
"""

from __future__ import annotations

from collections import Counter, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from orchestrator.observability.usage import request_coverage as coverage, request_models, request_scan
from orchestrator.observability.usage.request_codex_fold import NativeFold, Notes, Requests
from orchestrator.observability.usage.request_codex_scope import Invocation, Timeline, Turns, stdout_turns

LIMITATIONS = (
    "no-request-ids",
    "no-cache-write-lifetimes",
    "ambiguous-zero-cache-writes",
)
_NO_VERSION = "no-source-version"
_NO_TIMESTAMPS = "no-source-timestamps"
_NO_CAPACITY = "no-context-capacity"
# The gaps that leave a read short of the whole log, so the turns it found are not all the invocation opened, and the
# lines it reached are not all the log holds -- a reader passing an overlong line over hands it to no one, so a last one
# goes uncounted.
_CUT = frozenset((coverage.SCAN_LIMIT, coverage.NATIVE_READ_INTERRUPTED, coverage.OVERSIZE_LINES))


@dataclass(frozen=True)
class NativeSession:
    """One invocation's native session log as its caller hands it over, or why the caller could hand over none.

    `lines` yields each line of the log, numbered by its place in it, one at a time, so no more of the log than one
    line need be held at once. A reader holding its own bounds on what it reads records in `scan` -- shared with this
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


def _folded(session: NativeSession, scan: request_scan.EventScan, fallback_model: str | None) -> NativeFold:
    """Every line the reader hands over, decoded and folded in the order the log holds them."""
    metadata = request_scan.Metadata(scan.limits.metadata_chars)
    requests = Requests(
        metadata.text(session.invocation.session_id),
        scan,
        metadata,
        metadata.text(fallback_model),
        checkpoints=deque(maxlen=scan.limits.checkpoints),
    )
    fold = NativeFold(
        timeline=Timeline(session.invocation),
        turns=Turns(scan.limits, metadata),
        requests=requests,
        notes=Notes(requests.session_id, scan.limits, metadata),
        metadata=metadata,
    )
    for position, line in session.lines:
        fold.timeline.extent = max(fold.timeline.extent, position + 1)
        fold.feed(position, scan.counted(line))
    return fold


def _refusal(fold: NativeFold, stdout: str, scan: request_scan.EventScan, reasons: Counter[str]) -> str | None:
    """Why nothing in the log can be attributed to the invocation, stdout's turns compared where both were read whole.

    A read cut short proves nothing about the turns or the lines past the cut, and a line the scan could not read
    could have opened a turn, so neither holds the log to the turns stdout started -- none included.
    """
    partial = bool(reasons.keys() & _CUT)
    turns = None if partial or scan.unread_lines else stdout_turns(stdout, scan.limits)
    return fold.timeline.refusal(fold.turns, turns, partial)


def _collected(fold: NativeFold, scan: request_scan.EventScan, reasons: Counter[str]) -> coverage.RequestUsage:
    """The requests, markers, and checkpoints the invocation's lines left, with the baseline it began from first."""
    requests = fold.requests
    baseline = () if requests.baseline is None else (requests.baseline,)
    advanced = tuple(requests.checkpoints)
    kept = len(advanced) + len(baseline)
    room = max(kept - scan.limits.checkpoints, 0)
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
        checkpoints=(*baseline, *advanced[room:]),
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
    scan = session.scan
    if scan is None:
        scan = request_scan.EventScan(request_scan.current_limits())
    fold = _folded(session, scan, fallback_model)
    reasons = fold.reasons()
    refusal = _refusal(fold, stdout, scan, reasons)
    if refusal is not None:
        return _unavailable(refusal, scan)
    return _collected(fold, scan, reasons)
