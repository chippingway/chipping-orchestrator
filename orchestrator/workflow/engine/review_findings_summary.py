# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A line of pytest's short summary, read for the failure it reports, for `review_findings_failures`.

pytest's short summary reports each failure on a line of its own: its outcome
-- `FAILED` for a test, `ERROR` for an error outside any test body, and
`SUBFAILED` for a subtest that failed, the subtest's description right after
it, its message in brackets and its parameters in parentheses -- then the
node ID, or the path whose collection failed, and the message after a dash
where pytest gives one (`SummaryLine`).

A parameter may hold the very dash that parts a node ID from its message,
and even text of a message's shape after it, while a message may hold a
bracket and a dash of its own; so where the ID ends is read beside what
names one. It is the longest an entry of the findings names whole, or pytest
titled a section by. Where nothing names one, it ends on the first split
leaving a message of the shape pytest gives -- a rewritten assertion's
`assert`, or the name of the exception, a colon after it unless it says
nothing more -- so the message is never cut short, and where a later split
leaves one too the line says so (`SummaryLine.unsure`): the ID may run on
into what is read as its message. Where no split leaves one, it ends on the
first.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import compress

# A failure pytest's short summary reports: the outcome, or a subtest's with
# its description -- read up to the first closing bracket or parenthesis a
# node ID follows -- then the node ID or the path whose collection failed, and
# the message after a dash where pytest gives one. A node ID's path, which may
# hold blanks whatever file it names, as a doctest's text file may, runs to
# its test's separator, its parameters' bracket, the dash, or the line's end,
# whichever comes first; its test, which may hold blanks too, as a doctest's
# named by its text file does, runs to the bracket, the dash, or the line's
# end. Parameters, which may hold blanks, dashes, and brackets, end on a
# closing bracket that the dash or the line's end follows. A message pytest
# gives opens on a rewritten assertion's `assert`, or on the name of the
# exception it reports, a colon after it unless it says nothing more.
_SUMMARY_RE = re.compile(
    r"[ \t]*(?:(?P<outcome>FAILED|ERROR)|SUBFAILED(?P<subtest>[\[(].*?[\])])(?= [^ ]*::))"
    r" (?P<reported>\S.*?)[ \t\r]*",
)
_NODE_PATH_RE = re.compile(r"(?:(?! - |::|\[).)+?(?=::|\[| - |\Z)(?:::(?:(?! - |\[).)+?(?=\[| - |\Z))?")
_NODE_END_RE = re.compile(r"(?= - |\Z)")
_PARAMETERS_END_RE = re.compile(r"\](?= - |\Z)")
_OPENING_BRACKET = "["
_DELIMITER = " - "
_MESSAGE_RE = re.compile(r"assert\b|[A-Za-z_][\w.]*(?::|\Z)")

_ERRORED = "ERROR"

# Where a node ID ends, and whether a later split could end it as well.
_End = tuple[int, bool]


@dataclass(frozen=True)
class SummaryLine:
    """A failure a line of pytest's short summary reports.

    `node` is the node ID, or the path whose collection failed, and `error`
    what follows it on the line, "" where pytest gives nothing. `errored` says
    the line reports an error outside any test body; `subtest` is the
    description of the subtest it reports, "" for none; and `unsure` says
    nothing named the ID and a later split could have ended it too.
    """

    node: str
    error: str
    errored: bool = False
    subtest: str = ""
    unsure: bool = False

    @classmethod
    def read(cls, line: str, named: Callable[[str], bool]) -> SummaryLine | None:
        """The failure `line` reports, if it is a summary line of pytest's; None where not.

        `named` says whether an entry of the findings, or a section pytest
        printed, names a node ID whole.
        """
        summary = _SUMMARY_RE.fullmatch(line)
        if summary is None:
            return None
        reported = summary.group("reported")
        found = cls._end(reported, named)
        if found is None:
            return None
        end, unsure = found
        return cls(
            reported[:end],
            reported[end:].removeprefix(_DELIMITER),
            errored=summary.group("outcome") == _ERRORED,
            subtest=summary.group("subtest") or "",
            unsure=unsure,
        )

    @classmethod
    def _end(cls, reported: str, named: Callable[[str], bool]) -> _End | None:
        """Where the node ID `reported` opens on ends, and whether that is unsure; None where it holds none.

        The ID is the longest `named` names whole; else it ends on the first
        split leaving a message of the shape pytest gives -- unsure where a
        later one leaves one too -- and where none does, on the first split.
        """
        ends = cls._ends(reported)
        whole = [end for end in ends if named(reported[:end])]
        messages = [reported[end:].removeprefix(_DELIMITER) for end in ends]
        shaped = list(compress(ends, map(_MESSAGE_RE.match, messages)))
        if whole:
            return whole[-1], False
        if shaped:
            return shaped[0], len(shaped) > 1
        return (ends[0], False) if ends else None

    @classmethod
    def _ends(cls, reported: str) -> list[int]:
        """Where in `reported` a node ID may end: its path's end, or each closing bracket of its parameters."""
        path = _NODE_PATH_RE.match(reported)
        if path is None:
            return []
        if reported.startswith(_OPENING_BRACKET, path.end()):
            return [found.end() for found in _PARAMETERS_END_RE.finditer(reported, path.end())]
        return [path.end()] if _NODE_END_RE.match(reported, path.end()) else []
