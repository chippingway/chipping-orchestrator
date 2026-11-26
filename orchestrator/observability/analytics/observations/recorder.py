# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Record one reply's task snapshot, best-effort, behind one failure boundary.

Where the sink is (`sink_path`) is read first, behind a guard of its own: a
lookup that fails is warned of once and records nothing, so a caller that
asks it before anything else -- the snapshot's grounding follows the same
sink -- is never handed an error. The whole path a reply then takes to the
analytics sink runs inside one guard: framing it -- where its report outcome
begins, the verdict the workflow reaches on it, and which lines a code fence
may enclose, which the workflow answers through the callable it hands over
-- reading its attachment, redacting and bounding the telemetry copy,
serializing the records, and appending them. The sink's own
`append_jsonl_record` catches only a filesystem error, and only around the
file -- a serialization error before it would reach the caller -- so this
path writes its lines itself (`sink.write_jsonl_lines`) and catches
everything. A step that fails before the append is named by the step --
`parse_failed`, `redaction_failed`, or `serialization_failed` -- and recorded
as a diagnostic of its own; where that write fails too, or the append itself
is what failed -- the snapshot or a refused reply's diagnostic lost with it --
the loss is logged once on the `orchestrator.analytics` channel, as
`append_failed` where the append was refused, and nothing is written or tried
again.

The attachment is read off the reply exactly as the agent wrote it, so
nothing the telemetry copy needs can repair or reshape the framing it is
validated against. Only what a record carries is redacted, and before it is
made storable, cut, or serialized (`redaction`): the decoded description, and
each refused line's excerpt with every credential the whole reply holds
masked, written raw or JSON-escaped. A failed redaction leaves no text to
excerpt, so its diagnostic carries none.

A diagnostic's `counts` say how far the reading got: the attachment lines
`found`, and how many were `readable` as a snapshot. They never claim a
write: a reply's one record is one append, and a diagnostic of a failed step
lands only where that record did not.

Collection follows the analytics sink alone: with `ANALYTICS_LOG_PATH` off,
nothing is framed, read, redacted, or written. It needs no usage parse, no
trajectory sink, and no database; nothing reads an observation back, and a
lost one -- a refused append, a crash between a run and its record -- is
lost: no export, checkpoint, or agent run is owed for it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import NamedTuple

from orchestrator.observability.analytics import config as analytics_config, sink
from orchestrator.observability.analytics.observations import attachments, bounds, records, redaction


class Step(StrEnum):
    """The steps one reply's recording passes through, each spelled as the category its failure is diagnosed as."""

    PARSE = "parse_failed"
    REDACTION = "redaction_failed"
    SERIALIZATION = "serialization_failed"
    APPEND = "append_failed"


class Framing(NamedTuple):
    """Where a reply's report outcome begins -- its length where it has none -- and what that outcome reads as.

    `fenced` is the start of every line of the reply a code fence may
    enclose, none of which is an attachment line.
    """

    outcome_at: int
    report_outcome: str
    fenced: frozenset[int] = attachments.NOTHING_FENCED


@dataclass(frozen=True)
class ObservedReply:
    """A returned reply, and how the workflow's report reader frames it.

    `framing` is asked inside the recorder's boundary, so a reading that
    fails is a failed parse rather than an error in the caller's run, and a
    sink that is off asks it nothing.
    """

    message: str
    framing: Callable[[str], Framing]


def sink_path() -> Path | None:
    """The file observations are written to: None where the analytics sink is off, or where that cannot be read.

    Raises nothing: a lookup that fails is warned of once, and nothing is
    recorded behind it.
    """
    try:
        return analytics_config.live_settings().log_path
    except Exception as error:  # noqa: BLE001 - an observation is lost, never the run that returned it
        sink.log.warning(
            "analytics: could not read where observations are written (%s); recording none", type(error).__name__,
        )
        return None


def record_task_snapshot(run: records.ObservedRun, reply: ObservedReply, path: Path | None) -> None:
    """Record the task snapshot `reply` carries, or the problem that leaves it none, on the sink at `path`.

    `path` is what `sink_path` read; None records nothing and asks the reply
    nothing. Returns nothing and raises nothing: a recording that fails is a
    diagnostic, or a warning where the diagnostic cannot be written.
    """
    if path is None:
        return
    _Recording(run, path).record(reply)


class _Recording:
    """One reply's recording: the step it is in, and the counts it has reached."""

    def __init__(self, run: records.ObservedRun, path: Path) -> None:
        self._run = run
        self._path = path
        self._step = Step.PARSE
        self._counts: dict = {}

    def record(self, reply: ObservedReply) -> None:
        """Record `reply`, diagnosing whatever step fails."""
        try:
            self._recorded(reply)
        except Exception as error:  # noqa: BLE001 - an observation is lost, never the run that returned it
            self._diagnose(error)

    def _recorded(self, reply: ObservedReply) -> None:
        self._step = Step.PARSE
        framing = reply.framing(reply.message)
        self._run = replace(self._run, report_outcome=framing.report_outcome)
        reading = attachments.read_task_snapshot(reply.message, framing.outcome_at, framing.fenced)
        self._counts = {"found": reading.found, "readable": int(reading.description is not None)}
        self._step = Step.REDACTION
        telemetry = redaction.sanitized(reply.message, reading)
        self._step = Step.SERIALIZATION
        lines = self._lines(reading, telemetry)
        self._step = Step.APPEND
        sink.write_jsonl_lines(self._path, sink.ANALYTICS_FILE_LOCK, lines)

    def _lines(self, reading: attachments.SnapshotReading, telemetry: redaction.Telemetry) -> list[str]:
        """The snapshot's record where it read, else the diagnostic of the one problem that refused it, serialized."""
        if telemetry.description is not None:
            described = bounds.bounded(telemetry.description, bounds.DESCRIPTION_CHARS)
            return [records.serialized(records.task_snapshot_record(self._run, described))]
        return [
            records.serialized(records.diagnostic_record(
                self._run,
                problem.category.value,
                self._counts,
                excerpt=None if excerpt is None else bounds.bounded(excerpt, bounds.EXCERPT_CHARS),
            ))
            for problem, excerpt in zip(reading.problems, telemetry.excerpts, strict=True)
        ]

    def _diagnose(self, error: Exception) -> None:
        """Write the diagnostic a failed step earns; warn once, and only, where nothing more can be written.

        A refused append is that already: whatever it carried -- the snapshot
        or the diagnostic of a refused reply -- is lost, and a second append
        would be the retry nothing owes, so it is warned of and nothing else.
        """
        if self._step is Step.APPEND:
            self._warn(error, "nothing more was written")
            return
        try:
            self._write_diagnostic(error)
        except Exception as lost:  # noqa: BLE001 - the one warning a lost observation earns
            self._warn(error, f"its diagnostic could not be written either ({type(lost).__name__})")

    def _warn(self, error: Exception, rest: str) -> None:
        invocation = self._run.invocation
        sink.log.warning(
            "issue=#%d analytics: lost the task snapshot of invocation %d/%s to %s (%s); %s",
            invocation.issue, invocation.ordinal, invocation.nonce, self._step.value, type(error).__name__, rest,
        )

    def _write_diagnostic(self, error: Exception) -> None:
        diagnostic = records.diagnostic_record(
            self._run, self._step.value, self._counts, error=type(error).__name__,
        )
        sink.write_jsonl_lines(self._path, sink.ANALYTICS_FILE_LOCK, (records.serialized(diagnostic),))
