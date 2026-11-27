# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reply the workflow reads where a task snapshot was asked for, and the framing the recorder is handed.

An attachment line is one the snapshot's reader counts: a line opening on
`ANALYTICS:` that no code fence may enclose (`report_fences`), so a fenced
example -- one a report quotes -- is the report's own text and stays where it
is. Every attachment line is kept out of the reply the workflow reads
(`workflow_reply`), so no park, notice, or published report carries one, and
how it is kept out never moves the reply's framing:

* a reply with no report marker line has each one taken out whole, its line
  break with it, so a reply that says nothing else reads as silent and an
  acknowledgement or a question reads as it would without it -- no marker
  line is made or lost by taking a line out;
* a READY report has each one inside its block taken out whole, so the report
  the workflow publishes, and the digest it is identified by, are the ones
  the reply without it would have, and a block holding nothing else is the
  empty block the report reader refuses;
* every other one -- above an outcome, past it, or beside a marker that does
  not read -- is replaced by `PLACEHOLDER` at its own indentation, so every
  line of the reply stays a line of the same kind: a fence opens and closes
  where it did, text past an outcome is still text past it, and a malformed
  outcome stays malformed.

The verdict the workflow reaches is the report reader's reading of that
reply, and so is the one the recorder is told (`framing`): where the
outcome begins in the reply as written, which lines a fence may enclose, and
what the reply the workflow reads ends on -- `ready`, `verified`, or the
refusal's own spelling. The recorder asks it inside its own failure boundary.

A reply those readers fail on is never read as written. With one warning,
its attachment lines are found by a pattern of this owner's own -- every line
opening on `ANALYTICS:` that no fence the fence reader could read may enclose
-- and kept out by the marker lines alone, which the report reader's pattern
finds without parsing anything: taken out whole where the reply has no marker
line, and between its first and last, which is where a READY block's report
sits; replaced by `PLACEHOLDER` everywhere else. The fences are the whole
reply's where they read; where they do not, the report body's alone -- the
text between those markers, which holds every fence of a READY report, since
one open at either marker would leave the outcome unreadable -- every line
outside the body then read as no code. So a READY report reads as written
without the lines, its digest with it, a block holding nothing else stays the
empty block the report reader refuses, and a fenced example stays. Taking a
line out between the markers of an outcome that does not read changes no
marker, fence, or acknowledgement line, so no outcome the report reader
refuses is made one it accepts.

Where neither the reply's fences nor the body's read and the body holds a
prefixed line, which of its lines are code is unknown, so no report is
published on that reading: every prefixed line is replaced by `PLACEHOLDER`
and `UNREAD_REPORT` is added after the outcome, text past it the report
reader refuses whatever else it reads. No attachment text reaches a report,
a digest, or a notice on any reading.
"""
from __future__ import annotations

import contextlib
import logging
import re
from types import MappingProxyType

from orchestrator.observability.analytics.observations import attachments as _attachments, recorder as _recorder
from orchestrator.workflow.engine import (
    report_fences as _fences,
    report_outcome_models as _report_models,
    report_outcomes as _outcomes,
)

log = logging.getLogger("orchestrator.workflow")

# What a notice shows in place of an attachment line the reply's framing keeps a line for.
PLACEHOLDER = "(analytics attachment line taken out)"

# What follows a reply whose report body could not be told from its attachment lines, so no report is read off it.
UNREAD_REPORT = "(analytics attachment lines could not be told from code in this report, so it is not published)"

# What an outcome the report reader accepts is read as.
_OUTCOME_KINDS = MappingProxyType({_report_models._ReadyReport: "ready", _report_models._VerifiedReport: "verified"})

# The break that ends a line taken out whole, and the indentation a placeholder keeps.
_BREAK_RE = re.compile(r"\r?\n")
_INDENT_RE = re.compile("[ \t]*")

# Every line opening on the attachment prefix, whatever encloses it, framed as
# the attachment reader frames a line: to the next line feed, the carriage
# return before it the break's.
_ANY_PREFIXED_LINE_RE = re.compile(
    rf"^[ \t]*{re.escape(_attachments.PREFIX)}[^\n]*?(?=\r?\n|\Z)", re.MULTILINE,
)

# Where a line sits in a reply: `(start, end)`, its break aside.
_Span = tuple[int, int]


def workflow_reply(message: str) -> str:
    """`message` as the workflow reads it; kept out by the marker lines alone where its readers fail."""
    try:
        return _read_as(message, _fences._fenced_line_starts(message))
    except Exception as error:  # noqa: BLE001 - a reply its readers fail on is kept out by its marker lines instead
        log.warning(
            "could not read a developer reply's task snapshot attachment lines (%s); "
            "keeping them out by the reply's marker lines alone",
            type(error).__name__,
        )
        return _MarkerReading(message).held()


def framing(message: str) -> _recorder.Framing:
    """Where `message`'s report outcome begins, what the workflow reads that outcome as, and the lines fences hold."""
    fenced = _fences._fenced_line_starts(message)
    outcome = _outcomes._parse_report_outcome(_read_as(message, fenced))
    kind = _OUTCOME_KINDS.get(type(outcome)) or outcome.value
    return _recorder.Framing(_outcome_start(message), kind, fenced)


def _outcome_start(message: str) -> int:
    """Where `message`'s report outcome begins: its first line opening on the report prefix, else its end."""
    marker = _outcomes._MARKER_LINE_RE.search(message)
    return len(message) if marker is None else marker.start()


def _read_as(message: str, fenced: frozenset[int]) -> str:
    """`message` with every attachment line kept out of it, its framing as it was written."""
    lines = _attachments.attachment_lines(message, fenced)
    if not lines:
        return message
    outcome = _outcomes._parse_report_outcome(message)
    if outcome is _report_models._ReportRefusal.NO_MARKER:
        return _rewritten(message, lines, frozenset(lines))
    if not isinstance(outcome, _report_models._ReadyReport):
        return _rewritten(message, lines, frozenset())
    return _rewritten(message, lines, _in_the_block(message, lines))


class _MarkerReading:
    """A reply its readers failed on, its attachment lines kept out by the marker lines alone (`workflow_reply`).

    Its lines are those opening on the prefix that may be no code, read the
    best way the fence reader answers, the later reading replacing the earlier
    where it does: the report body's own fences -- between the first and last
    marker lines -- every line outside it read as no code; the whole reply's
    fences. Where neither reads, every prefixed line is held by the
    placeholder, and a report body holding one is refused (`UNREAD_REPORT`).
    """

    def __init__(self, message: str) -> None:
        self._message = message
        self._markers = tuple(_outcomes._MARKER_LINE_RE.finditer(message))
        self._prefixed = tuple(line.span() for line in _ANY_PREFIXED_LINE_RE.finditer(message))

    def held(self) -> str:
        """The reply, its lines taken out with no marker line or between the markers, held by the placeholder else."""
        code = self._code()
        lines = self._outside(code or frozenset())
        if not self._markers:
            return _rewritten(self._message, lines, frozenset(lines))
        block = _in_the_block(self._message, lines)
        if code is None and block:
            return f"{_rewritten(self._message, lines, frozenset())}\n{UNREAD_REPORT}"
        return _rewritten(self._message, lines, block)

    def _outside(self, code: frozenset[int]) -> tuple[_Span, ...]:
        """The prefixed lines `code` holds none of."""
        return tuple(line for line in self._prefixed if line[0] not in code)

    def _code(self) -> frozenset[int] | None:
        """The start of every line that may be code, in the best reading the fence reader answers; None for none."""
        code = None
        with contextlib.suppress(Exception):
            code = self._body_fences()
        with contextlib.suppress(Exception):
            code = _fences._fenced_line_starts(self._message)
        return code

    def _body_fences(self) -> frozenset[int]:
        """The fences of the report body read alone, at the offsets the reply holds them; none without a marker line."""
        if not self._markers:
            return frozenset()
        opening = self._markers[0].end()
        closing = self._markers[-1].start()
        fenced = _fences._fenced_line_starts(self._message[opening:closing])
        return frozenset(opening + start for start in fenced)


def _in_the_block(message: str, lines: tuple[_Span, ...]) -> frozenset[_Span]:
    """Which of `lines` sit between `message`'s first and last marker lines: inside the READY block it ends on."""
    markers = tuple(_outcomes._MARKER_LINE_RE.finditer(message))
    opening = markers[0].end()
    closing = markers[-1].start()
    return frozenset(line for line in lines if opening < line[0] < closing)


def _rewritten(message: str, lines: tuple[_Span, ...], taken_out: frozenset[_Span]) -> str:
    """`message` with each of `lines` taken out whole where `taken_out` holds it, the placeholder in its place else.

    A line taken out takes its break with it; the placeholder keeps the
    line's own indentation and its break.
    """
    pieces = []
    cursor = 0
    for start, end in lines:
        pieces.append(message[cursor:start])
        cursor = end
        if (start, end) in taken_out:
            ended = _BREAK_RE.match(message, end)
            cursor = end if ended is None else ended.end()
        else:
            pieces.extend((_INDENT_RE.match(message, start, end).group(), PLACEHOLDER))
    pieces.append(message[cursor:])
    return "".join(pieces)
