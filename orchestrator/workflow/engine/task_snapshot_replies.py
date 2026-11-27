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

A reply those readers fail on is never read as written: with one warning,
every line opening on `ANALYTICS:` -- fenced or not, since which lines a fence
encloses is what could not be read -- is replaced by `PLACEHOLDER` at its own
indentation, by a pattern no reader is asked for. Every
line stays a line of the same kind, so the framing is as written and no
attachment text reaches a report, its digest, or a notice; a READY report
then carries the placeholder wherever such a line stood, a fenced example's
included.
"""
from __future__ import annotations

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

# What an outcome the report reader accepts is read as.
_OUTCOME_KINDS = MappingProxyType({_report_models._ReadyReport: "ready", _report_models._VerifiedReport: "verified"})

# The break that ends a line taken out whole, and the indentation a placeholder keeps.
_BREAK_RE = re.compile(r"\r?\n")
_INDENT_RE = re.compile("[ \t]*")

# Every line opening on the attachment prefix, whatever encloses it, framed as
# the attachment reader frames a line: to the next line feed, the carriage
# return before it the break's.
_ANY_PREFIXED_LINE_RE = re.compile(
    rf"^(?P<indent>[ \t]*){re.escape(_attachments.PREFIX)}[^\n]*?(?=\r?\n|\Z)", re.MULTILINE,
)

# What stands in such a line's place: the placeholder, at the line's own indentation.
_HELD = rf"\g<indent>{PLACEHOLDER}"

# Where a line sits in a reply: `(start, end)`, its break aside.
_Span = tuple[int, int]


def workflow_reply(message: str) -> str:
    """`message` as the workflow reads it; every prefixed line held by the placeholder where its readers fail."""
    try:
        return _read_as(message, _fences._fenced_line_starts(message))
    except Exception as error:  # noqa: BLE001 - a reply its readers fail on is held line by line instead
        log.warning(
            "could not read a developer reply's task snapshot attachment lines (%s); "
            "holding every line opening on their prefix",
            type(error).__name__,
        )
        return _ANY_PREFIXED_LINE_RE.sub(_HELD, message)


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


def _in_the_block(message: str, lines: tuple[_Span, ...]) -> frozenset[_Span]:
    """Which of `lines` sit inside the READY block `message` ends on, between its two marker lines."""
    markers = tuple(_outcomes._MARKER_LINE_RE.finditer(message))
    opening = markers[0].end()
    closing = markers[-1].start()
    return frozenset(line for line in lines if opening < line[0] < closing)


def _rewritten(message: str, lines: tuple[_Span, ...], taken_out: frozenset[_Span]) -> str:
    """`message` with each of `lines` taken out whole where `taken_out` holds it, the placeholder in its place else."""
    pieces = []
    cursor = 0
    for line in lines:
        pieces.append(message[cursor:line[0]])
        shown, cursor = _in_place_of(message, line, taken_out)
        pieces.append(shown)
    pieces.append(message[cursor:])
    return "".join(pieces)


def _in_place_of(message: str, line: _Span, taken_out: frozenset[_Span]) -> tuple[str, int]:
    """What stands where `line` of `message` was, and where the text after it resumes.

    Nothing, past the line's break, where `taken_out` holds it; the
    placeholder at the line's own indentation otherwise.
    """
    start, end = line
    if line in taken_out:
        ended = _BREAK_RE.match(message, end)
        return "", end if ended is None else ended.end()
    indentation = _INDENT_RE.match(message, start, end)
    return f"{indentation.group()}{PLACEHOLDER}", end
