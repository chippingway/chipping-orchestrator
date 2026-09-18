# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read a reviewer's verification declaration, and only out of a run that completed.

`_verification_outcome_of_run` is the reader a stage asks. It refuses a run
that never started, was interrupted, timed out, was refused by its provider, or
exited nonzero before it looks at the message at all, so a partial transcript
or a provider's error text is never read as verification anybody finished.
`_parse_verification_outcome` is the message half alone. Nothing calls either
yet: the reviewer round keeps deciding on its `VERDICT:` line alone until its
integration asks for this reading too.

The declaration is read apart from the verdict and as strictly as the
developer report beside it. Its marker lines are uppercase and whole-line as
the models spell them, and the declaration is the ONLY use of them: every line
opening on `VERIFICATION:` must be its own -- the RUN/END pair around a block,
or the single REUSED line -- outside any code block. A marker quoted elsewhere,
a second declaration, a block never closed, or a marker line that may render as
code leaves the message MALFORMED rather than letting one reading win. Unlike
the report, the declaration need not end the message, since the reviewer's
verdict line closes it. The two share no text, though -- a verdict the verdict
reader would accept inside the declaration is MALFORMED, so a command's quoted
output never carries the verdict and the verdict is never read out of evidence.

Inside a RUN block, every step is a `COMMAND:` line followed at once by an
`EXIT:` line, then whatever output the reviewer quoted, up to the next step or
the closing line. A line opening on either keyword anywhere in the block is a
step line, so it must be one in shape and must not sit where a code fence may
enclose it; only blank lines may come before the first step. The command and
the output are kept exactly as written, with only the blank lines framing the
output dropped; the exit status must be a POSIX one.

Shape is settled before truth. A well-formed declaration is STALE when a RUN
block names another commit than the one under review, or a REUSED line names
any revision but the current evidence the reviewer was shown -- including when
it was shown none.

A marker or step line may render as code when it sits four columns in or behind
a tab, where it can be an indented code block, or where `report_fences` finds a
code fence may enclose it.
"""
from __future__ import annotations

import re
from types import MappingProxyType

from orchestrator.agents import provider_failures as _provider_failures
from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import (
    completion_verdicts as _completion_verdicts,
    report_fences as _fences,
    review_verification_models as _models,
)

# Every line opening on the prefix, whatever follows it: the contract's own
# lines and each near miss of them.
_MARKER_LINE_RE = re.compile(
    rf"^[ \t]*{re.escape(_models._VERIFICATION_MARKER_PREFIX)}[^\r\n]*",
    re.MULTILINE,
)

# Every line of a message, without its line break.
_LINE_RE = re.compile(r"^[^\r\n]*", re.MULTILINE)

# Four columns in, or behind a tab, a marker line may be an indented code
# block, so only a shallower indentation is the declaration's own.
_MARKER_INDENT = " {0,3}"

# Git names an object with a full SHA-1 or SHA-256 hex digest; an abbreviated
# one names no commit for certain.
_RUN_LINE_RE = re.compile(
    rf"{_MARKER_INDENT}{re.escape(_models._VERIFICATION_RUN_MARKER)}[ \t]+"
    r"(?P<commit>[0-9a-f]{40}|[0-9a-f]{64})[ \t]*",
)

_END_LINE_RE = re.compile(
    rf"{_MARKER_INDENT}{re.escape(_models._VERIFICATION_END_MARKER)}[ \t]*",
)

_REUSED_LINE_RE = re.compile(
    rf"{_MARKER_INDENT}{re.escape(_models._VERIFICATION_REUSED_MARKER)}[ \t]+"
    rf"{re.escape(_models._REVISION_PREFIX)}(?P<revision>[0-9a-f]{{64}})[ \t]*",
)

# Every line of a block opening on a step keyword, whatever follows it.
_STEP_LINE_RE = re.compile(
    rf"[ \t]*(?P<keyword>{re.escape(_models._COMMAND_PREFIX)}|{re.escape(_models._EXIT_PREFIX)})",
)

_COMMAND_LINE_RE = re.compile(
    rf"{_MARKER_INDENT}{re.escape(_models._COMMAND_PREFIX)}[ \t]+"
    r"(?P<command>[^ \t](?:.*[^ \t])?)[ \t]*",
)

# A POSIX exit status: 0 through 255, spelled without leading zeros.
_EXIT_LINE_RE = re.compile(
    rf"{_MARKER_INDENT}{re.escape(_models._EXIT_PREFIX)}[ \t]+"
    r"(?P<status>25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])[ \t]*",
)

# What a line may hold and still be blank. A no-break space, like any other
# character, is text Markdown shows.
_BLANKS = " \t"

# Each line of a RUN block reads as one letter, so the block's grammar is a
# pattern over them: blank lines, then one or more steps -- a command line, the
# exit line right below it, and whatever blank or output lines follow. A step
# line a code fence may enclose reads as a letter no step admits.
_BLANK_KIND = "b"
_OUTPUT_KIND = "o"
_FENCED_KIND = "f"
_COMMAND_KIND = "c"
_EXIT_KIND = "e"
_STEP_KINDS = MappingProxyType({
    _models._COMMAND_PREFIX: _COMMAND_KIND,
    _models._EXIT_PREFIX: _EXIT_KIND,
})
_STEP_SHAPE_RE = re.compile(f"{_COMMAND_KIND}{_EXIT_KIND}[{_BLANK_KIND}{_OUTPUT_KIND}]*")
_BLOCK_SHAPE_RE = re.compile(f"{_BLANK_KIND}*(?:{_STEP_SHAPE_RE.pattern})+")

# A step's output within its lines: from the start of the first line with
# anything on it besides spaces and tabs to the end of the last such line.
_OUTPUT_SPAN_RE = re.compile(
    r"^[ \t]*[^ \t\r\n](?:[\s\S]*[^ \t\r\n])?[^\r\n]*", re.MULTILINE,
)


def _verification_outcome_of_run(
    agent_result: AgentResult, subject: _models._VerificationSubject,
) -> _models._VerificationOutcome:
    """The verification `agent_result` declares about `subject`, or why none.

    The run is judged before its message, in the developer report reader's
    order: a launch that never started has no output to judge, and the exit
    code of a killed or timed-out run is the kill's rather than the agent's.
    """
    shortfalls = (
        (not agent_result.invoked, _models._VerificationRefusal.NOT_INVOKED),
        (agent_result.interrupted, _models._VerificationRefusal.INTERRUPTED),
        (agent_result.timed_out, _models._VerificationRefusal.TIMED_OUT),
        (
            _provider_failures.is_transient_provider_failure(agent_result),
            _models._VerificationRefusal.PROVIDER_FAILURE,
        ),
        (agent_result.exit_code != 0, _models._VerificationRefusal.NONZERO_EXIT),
    )
    refusal = next(
        (shortfall for fell_short, shortfall in shortfalls if fell_short), None,
    )
    if refusal is not None:
        return refusal
    return _parse_verification_outcome(
        agent_result.last_message, subject, agent_result.session_id,
    )


def _parse_verification_outcome(
    last_message: str,
    subject: _models._VerificationSubject,
    session_id: str | None = None,
) -> _models._VerificationOutcome:
    """The declaration a completed reviewer run's `last_message` makes.

    `MISSING` when no line opens on the prefix; `MALFORMED` when one does but
    the message holds no single well-formed declaration outside any code block;
    `STALE` when it holds one about something other than `subject`. An accepted
    declaration is sourced to `session_id`, the reviewer run that wrote it.
    """
    text = last_message or ""
    markers = tuple(_MARKER_LINE_RE.finditer(text))
    if not markers:
        return _models._VerificationRefusal.MISSING
    fenced = _fences._fenced_line_starts(text)
    if any(marker.start() in fenced for marker in markers):
        return _models._VerificationRefusal.MALFORMED
    source = _models._ReviewerSource(session_id, subject.commit)
    if len(markers) == 1:
        return _reused_verification(markers[0].group(), subject, source)
    if len(markers) == 2:
        return _fresh_verification(text, markers, fenced, source)
    return _models._VerificationRefusal.MALFORMED


def _reused_verification(
    line: str,
    subject: _models._VerificationSubject,
    source: _models._ReviewerSource,
) -> _models._ReusedVerification | _models._VerificationRefusal:
    reused = _REUSED_LINE_RE.fullmatch(line)
    if reused is None:
        return _models._VerificationRefusal.MALFORMED
    revision = reused.group("revision")
    if revision != subject.evidence_revision:
        return _models._VerificationRefusal.STALE
    return _models._ReusedVerification(source, revision)


def _fresh_verification(
    text: str,
    markers: tuple[re.Match[str], ...],
    fenced: frozenset[int],
    source: _models._ReviewerSource,
) -> _models._FreshVerification | _models._VerificationRefusal:
    """The commands a RUN block between the two `markers` lists.

    The block is the lines strictly between the marker lines. One listing no
    command is no verification: a closing line with nothing above it proves
    only that the markers were written.
    """
    opening, closing = markers
    run = _RUN_LINE_RE.fullmatch(opening.group())
    if run is None or _END_LINE_RE.fullmatch(closing.group()) is None:
        return _models._VerificationRefusal.MALFORMED
    if _completion_verdicts._VERDICT_RE.search(text, opening.start(), closing.end()):
        return _models._VerificationRefusal.MALFORMED
    lines = tuple(_LINE_RE.finditer(text, opening.end(), closing.start()))
    commands = _reported_commands(text, lines, fenced)
    if not commands:
        return _models._VerificationRefusal.MALFORMED
    if run.group("commit") != source.commit:
        return _models._VerificationRefusal.STALE
    return _models._FreshVerification(source, commands)


def _reported_commands(
    text: str,
    lines: tuple[re.Match[str], ...],
    fenced: frozenset[int],
) -> tuple[_models._ReportedCommand, ...]:
    """Each step of the block's `lines`, or none when any is out of shape."""
    shape = "".join(_line_kind(line, fenced) for line in lines)
    if _BLOCK_SHAPE_RE.fullmatch(shape) is None:
        return ()
    reported = tuple(
        _reported_command(text, lines[slice(*step.span())])
        for step in _STEP_SHAPE_RE.finditer(shape)
    )
    return () if None in reported else reported


def _line_kind(line: re.Match[str], fenced: frozenset[int]) -> str:
    """The letter a RUN block's `line` reads as in the block's shape."""
    step = _STEP_LINE_RE.match(line.group())
    if step is None:
        return _OUTPUT_KIND if line.group().strip(_BLANKS) else _BLANK_KIND
    if line.start() in fenced:
        return _FENCED_KIND
    return _STEP_KINDS[step.group("keyword")]


def _reported_command(
    text: str, step: tuple[re.Match[str], ...],
) -> _models._ReportedCommand | None:
    """One step read from its command line, its exit line, and the output
    lines below them, or None when either keyed line is out of shape."""
    exit_line, last_line = step[1], step[-1]
    command = _COMMAND_LINE_RE.fullmatch(step[0].group())
    status = _EXIT_LINE_RE.fullmatch(exit_line.group())
    if command is None or status is None:
        return None
    output = _OUTPUT_SPAN_RE.search(text, exit_line.end(), last_line.end())
    return _models._ReportedCommand(
        command.group("command"),
        int(status.group("status")),
        "" if output is None else output.group(),
    )
