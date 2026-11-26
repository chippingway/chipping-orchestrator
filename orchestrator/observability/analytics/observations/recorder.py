# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Record one reply's task snapshot, best-effort, behind one failure boundary.

The whole path a reply takes to the analytics sink runs inside one guard:
finding the report outcome in it, redacting it, reading its attachment,
redacting what the attachment decodes to, bounding and serializing the
records, and appending them. The sink's own `append_jsonl_record` catches
only a filesystem error, and only around the file -- a serialization error
before it would reach the caller -- so this path writes its lines itself
(`sink.write_jsonl_lines`) and catches everything. Whatever fails is named by
the step it failed in -- `parse_failed`, `redaction_failed`,
`serialization_failed`, or `append_failed` -- and recorded as a diagnostic of
its own; where that write fails too, the failure is logged once on the
`orchestrator.analytics` channel and nothing is tried again.

Redaction comes before anything reads the text. The credential redactor
(`config.credentials.redact_secrets`) replaces each secret's literal value,
so it runs over the raw reply, where a secret spanning lines is still one
string, and again over the decoded description, where a secret the JSON
escaped is one again -- in both cases before a text is cut, so no secret is
kept as a fragment the redactor no longer recognizes, and before it is
serialized, which would escape its line breaks. A failed redaction leaves
no text to excerpt, so its diagnostic carries none.

Collection follows the analytics sink alone: with `ANALYTICS_LOG_PATH` off,
nothing is read, redacted, or written. It needs no usage parse, no
trajectory sink, and no database; nothing reads an observation back, and a
lost one -- a refused append, a crash between a run and its record -- is
lost: no export, checkpoint, or agent run is owed for it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from orchestrator.observability.analytics import config as analytics_config, sink
from orchestrator.observability.analytics.observations import attachments, bounds, records


class Step(StrEnum):
    """The steps one reply's recording passes through, each spelled as the category its failure is diagnosed as."""

    PARSE = "parse_failed"
    REDACTION = "redaction_failed"
    SERIALIZATION = "serialization_failed"
    APPEND = "append_failed"


@dataclass(frozen=True)
class ObservedReply:
    """A returned reply, and where its report outcome begins.

    `outcome_at` is the workflow report reader's own answer to where the
    outcome starts in `message` -- its length where there is none -- asked
    inside the recorder's boundary, so a reading that fails is a failed parse
    rather than an error in the caller's run.
    """

    message: str
    outcome_at: Callable[[str], int]


def record_task_snapshot(run: records.ObservedRun, reply: ObservedReply) -> None:
    """Record the task snapshot `reply` carries, and every problem with it, on the analytics sink.

    Returns nothing and raises nothing: a recording that fails is a
    diagnostic, or a warning where the diagnostic cannot be written.
    """
    path = analytics_config.live_settings().log_path
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
        halves = _split(reply)
        self._step = Step.REDACTION
        halves = tuple(_redacted(half) for half in halves)
        self._step = Step.PARSE
        reading = attachments.read_task_snapshot(*halves)
        self._counts = {"found": reading.found, "recorded": int(reading.description is not None)}
        self._step = Step.REDACTION
        description = None if reading.description is None else _redacted(reading.description)
        self._step = Step.SERIALIZATION
        lines = self._lines(reading, description)
        self._step = Step.APPEND
        sink.write_jsonl_lines(self._path, sink.ANALYTICS_FILE_LOCK, lines)

    def _lines(self, reading: attachments.SnapshotReading, description: str | None) -> list[str]:
        """The snapshot's record, where there is one, and one diagnostic per problem, serialized."""
        written = [
            records.diagnostic_record(
                self._run,
                problem.category.value,
                self._counts,
                excerpt=None if problem.line is None else bounds.bounded(problem.line, bounds.EXCERPT_CHARS),
            )
            for problem in reading.problems
        ]
        if description is not None:
            written.insert(0, records.task_snapshot_record(
                self._run, bounds.bounded(description, bounds.DESCRIPTION_CHARS),
            ))
        return [records.serialized(record) for record in written]

    def _diagnose(self, error: Exception) -> None:
        """Write the diagnostic a failed step earns; warn once, and only, where that write fails too."""
        try:
            self._write_diagnostic(error)
        except Exception as lost:  # noqa: BLE001 - the one warning a lost observation earns
            invocation = self._run.invocation
            sink.log.warning(
                "issue=#%d analytics: lost the task snapshot of invocation %d/%s to %s (%s); "
                "its diagnostic could not be written either (%s)",
                invocation.issue, invocation.ordinal, invocation.nonce, self._step.value,
                type(error).__name__, type(lost).__name__,
            )

    def _write_diagnostic(self, error: Exception) -> None:
        diagnostic = records.diagnostic_record(
            self._run, self._step.value, self._counts, error=type(error).__name__,
        )
        sink.write_jsonl_lines(self._path, sink.ANALYTICS_FILE_LOCK, (records.serialized(diagnostic),))


def _split(reply: ObservedReply) -> tuple[str, str]:
    """The reply above its report outcome, and the outcome with everything after it."""
    outcome_at = reply.outcome_at(reply.message)
    return reply.message[:outcome_at], reply.message[outcome_at:]


def _redacted(text: str) -> str:
    """`text` with every credential the process holds masked.

    The redactor is reached inside the call, as the trajectory writer reaches
    it: it is the one thing this owner needs from outside the observability
    tree, and a producer importing the recorder pays for it only once a
    record is written.
    """
    from orchestrator.config import credentials

    return credentials.redact_secrets(text)
