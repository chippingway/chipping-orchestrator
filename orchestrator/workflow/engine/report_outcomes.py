# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read a developer report outcome, and only out of a run that completed.

`_report_outcome_of_run` is the reader a stage asks. It refuses a run that
never started, was interrupted, timed out, was refused by its provider, or
exited nonzero before it looks at the message at all, so a partial transcript
or a provider's error text is never read as finished work.
`_parse_report_outcome` is the message half alone, and `_finished_on_a_report`
is that same reading asked as a yes/no by a stage whose other replies are
ordinary answers rather than a contract broken. `_reached_for_a_report` is the
wider question beside it -- did this message use the contract at all, well or
badly -- for the caller whose other readers must not take a reply that reached
for it and missed as one of their own.

The message is read more strictly than the verdict markers beside it. A report
block encloses free prose, so its marker lines are uppercase and whole-line as
the prompts spell them, and the outcome is the ONLY use of them: every line
opening on `REPORT:` must be the outcome's own -- the READY/END pair around the
report, or the single VERIFIED line -- outside any code block, and the outcome
must end the message. A marker quoted earlier, a second block, a report whose
own text opens a line on the prefix, a marker line that may render as code, or
a question written after the outcome leaves the message MALFORMED rather than
letting one reading win. So does an `ACK:` line the `messages` reader would
accept, so a caller that asks this reader first never takes one reply as both
an acknowledgement and a report.

A marker line may render as code when it sits four columns in or behind a tab,
where it can be an indented code block, or where `report_fences` finds a code
fence may enclose it.

A VERIFIED location is a `github.com` pull request URL, optionally anchored at
one of its conversation comments, and its revision a lowercase SHA-256 digest.
Parsing establishes their shape, not their truth.
"""
from __future__ import annotations

import re

from orchestrator.agents import provider_failures as _provider_failures
from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import (
    messages as _messages,
    report_fences as _fences,
    report_outcome_models as _models,
)

# What a message may end on past its outcome without writing anything after
# it: spaces, tabs, and line breaks. A no-break space, like any other
# character, is text Markdown shows.
_TRAILING_BLANKS = " \t\r\n"

# Every line opening on the prefix, whatever follows it: the contract's own
# lines and each near miss of them.
_MARKER_LINE_RE = re.compile(
    rf"^[ \t]*{re.escape(_models._REPORT_MARKER_PREFIX)}[^\r\n]*",
    re.MULTILINE,
)

# Four columns in, or behind a tab, a marker line may be an indented code
# block, so only a shallower indentation is the outcome's own.
_MARKER_INDENT = " {0,3}"

_READY_LINE_RE = re.compile(
    rf"{_MARKER_INDENT}{re.escape(_models._REPORT_READY_MARKER)}[ \t]*",
)

_END_LINE_RE = re.compile(
    rf"{_MARKER_INDENT}{re.escape(_models._REPORT_END_MARKER)}[ \t]*",
)

# A report within its block: from the start of the first line with anything on
# it besides spaces and tabs to the end of the last such line.
_REPORT_SPAN_RE = re.compile(
    r"^[ \t]*[^ \t\r\n](?:[\s\S]*[^ \t\r\n])?[^\r\n]*", re.MULTILINE,
)

# GitHub numbers pull requests and comments with signed 64-bit integers, so no
# real id is wider than nineteen digits. The bound also keeps an absurdly long
# one MALFORMED instead of past the length `int` converts from a string.
_GITHUB_ID = r"[1-9][0-9]{0,18}"

_VERIFIED_LINE_RE = re.compile(
    rf"{_MARKER_INDENT}{re.escape(_models._REPORT_VERIFIED_MARKER)}[ \t]+"
    r"https://github\.com/(?P<slug>[A-Za-z0-9-]+/[A-Za-z0-9._-]+)"
    rf"/pull/(?P<pull>{_GITHUB_ID})(?:#issuecomment-(?P<comment>{_GITHUB_ID}))?"
    rf"[ \t]+{re.escape(_models._REVISION_PREFIX)}(?P<revision>[0-9a-f]{{64}})"
    r"[ \t]*",
)


def _report_outcome_of_run(agent_result: AgentResult) -> _models._ReportOutcome:
    """The report outcome `agent_result` earns, or why it earns none.

    The run is judged before its message: an outcome is only ever read out of
    a run that was invoked and completed on its own terms. Its shortfalls are
    asked in this order because each earlier reading makes the later ones
    meaningless: a launch that never started has no output to judge, and the
    exit code of a killed or timed-out run is the kill's rather than the
    agent's.
    """
    shortfalls = (
        (not agent_result.invoked, _models._ReportRefusal.NOT_INVOKED),
        (agent_result.interrupted, _models._ReportRefusal.INTERRUPTED),
        (agent_result.timed_out, _models._ReportRefusal.TIMED_OUT),
        (
            _provider_failures.is_transient_provider_failure(agent_result),
            _models._ReportRefusal.PROVIDER_FAILURE,
        ),
        (agent_result.exit_code != 0, _models._ReportRefusal.NONZERO_EXIT),
    )
    refusal = next(
        (shortfall for fell_short, shortfall in shortfalls if fell_short), None,
    )
    if refusal is not None:
        return refusal
    return _parse_report_outcome(agent_result.last_message)


def _finished_on_a_report(agent_result: AgentResult) -> bool:
    """Whether this run finished on one of the two report outcomes.

    What it separates is which road a run's disposition belongs on, for the
    routes where a reply carrying NO report is an ordinary answer rather than
    a contract broken. A fix round is exactly that: its `ACK:`, its question,
    its timeout are each a road the stage already has, so the stage settles
    what it delivered on every one of them -- and on a run that really did
    write a report it settles nothing, because that report is a publication
    this tick cannot guarantee and the feedback it answers may not be
    recorded as read until it lands.
    """
    return not isinstance(
        _report_outcome_of_run(agent_result), _models._ReportRefusal,
    )


def _reached_for_a_report(agent_result: AgentResult) -> bool:
    """Whether a completed run's message used the report contract at all.

    True for the two outcomes, and true for a message that reached for the
    markers and MISSED -- an unclosed block, text after the outcome, a stray
    marker line, a marker that may render as code, an `ACK:` beside it.

    What it is for is the caller whose other readers would otherwise take such
    a message as something it is not. A reply carrying both a report marker and
    an acknowledgement is one broken contract, not two answers: read as the
    acknowledgement alone it would hand a pull request back to review over work
    whose report nothing carries, which is the reading the report contract
    exists to prevent. Asked here, that reply reaches no fast path and is left
    for a human like every other reply this workflow cannot act on.

    A run that did not COMPLETE is False, and so is a completed reply that
    never used the contract -- a question, a disagreement, an ordinary `ACK:`.
    Neither reached for anything, so neither is a contract to hold anybody to.
    """
    outcome = _report_outcome_of_run(agent_result)
    if not isinstance(outcome, _models._ReportRefusal):
        return True
    return outcome is _models._ReportRefusal.MALFORMED


def _parse_report_outcome(last_message: str) -> _models._ReportOutcome:
    """The report outcome a completed run's `last_message` closes with.

    `NO_MARKER` when no line opens on the prefix, so the caller's own readers
    decide what the reply is; `MALFORMED` when one does but the message is not
    exactly one well-formed outcome outside any code block with nothing after
    it and no `ACK:` beside it.
    """
    text = (last_message or "").rstrip(_TRAILING_BLANKS)
    markers = tuple(_MARKER_LINE_RE.finditer(text))
    if not markers:
        return _models._ReportRefusal.NO_MARKER
    outcome = _closing_outcome(text, markers)
    if outcome is None or _messages._drift_ack_reason(text) is not None:
        return _models._ReportRefusal.MALFORMED
    return outcome


def _closing_outcome(
    text: str, markers: tuple[re.Match[str], ...],
) -> _models._ReadyReport | _models._VerifiedReport | None:
    """The outcome `markers` form, or None when they form none.

    One marker line can only be the VERIFIED line and two only the READY/END
    pair; either way the last of them has to be the message's last line, and
    none of them may sit where a code fence may enclose it.
    """
    if markers[-1].end() != len(text):
        return None
    fenced = _fences._fenced_line_starts(text)
    if any(marker.start() in fenced for marker in markers):
        return None
    if len(markers) == 1:
        return _verified_report(markers[0].group())
    if len(markers) == 2:
        return _ready_report(text, markers[0], markers[1])
    return None


def _verified_report(line: str) -> _models._VerifiedReport | None:
    verified = _VERIFIED_LINE_RE.fullmatch(line)
    if verified is None:
        return None
    comment_id = verified.group("comment")
    location = _models._ReportLocation(
        slug=verified.group("slug"),
        pull_number=int(verified.group("pull")),
        comment_id=None if comment_id is None else int(comment_id),
    )
    return _models._VerifiedReport(location, verified.group("revision"))


def _ready_report(
    text: str, opening: re.Match[str], closing: re.Match[str],
) -> _models._ReadyReport | None:
    """The report between an opening READY and a closing END line.

    Nothing inside the report's span is trimmed: blank lines at either edge
    only frame it, while its whitespace is Markdown -- a first line four
    columns in is a code block. The block opens on the READY line's own break,
    so no report line starts where the block does. An empty block is no
    report: a closing line with nothing above it proves only that the marker
    was written.
    """
    if _READY_LINE_RE.fullmatch(opening.group()) is None:
        return None
    if _END_LINE_RE.fullmatch(closing.group()) is None:
        return None
    block = text[opening.end():closing.start()]
    span = _REPORT_SPAN_RE.search(block)
    return None if span is None else _models._ReadyReport(span.group())
