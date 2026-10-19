# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A line of pytest's short summary, read for the failure it reports, for `review_findings_failures`.

pytest's short summary reports each failure on a line of its own: its outcome
-- `FAILED` for a test, `ERROR` for an error outside any test body, and
`SUBFAILED` for a subtest that failed, the subtest's description right after
it, its message in brackets and its parameters in parentheses -- then the
node ID, or the path whose collection failed, and the message after a dash
where pytest gives one (`SummaryLine`).

A parameter may hold the very dash that parts a node ID from its message, and
even text of a message's shape after it, while a message may hold a bracket
and a dash of its own; so where the ID ends is read beside what names one. It
is the longest whose section -- one of the line's run pytest printed for that
test, or a failure `--tb=line` printed untitled, the first no line took yet --
shows the exception the message after it opens, since one test's ID may run on
into another's where parameters overlap; else the longest an entry of the
findings names whole, or pytest titled a section of the line's run by. Where
nothing names one, it ends on the first split leaving a message of the shape
pytest gives -- a rewritten assertion's `assert`, or the name of the
exception, a colon after it unless it says nothing more -- so the message is
never cut short, and where a later split leaves one too the line says so
(`SummaryLine.unsure`): the ID may run on into what is read as its message.
Where no split leaves one, it ends on the last, pytest having given no
message.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import chain, compress

# A subtest's description as pytest writes it: its message in brackets, its
# parameters in parentheses, or the one and then the other. It runs to the
# first closing bracket or parenthesis a node ID free of blanks follows. Where
# none does, the node ID holds blanks -- its path the dash, maybe -- and the
# description, which never holds the dash parting the line's message, so
# never runs into it, runs to the last closing bracket of its message, a
# message holding brackets of its own, then to the first closing parenthesis
# of its parameters, that a node ID follows.
_UNDASHED = r"(?:(?! - ).)"
_BLANK_FREE_NODE = r"(?= [^ ]*::)"
_SPACED_NODE = r"(?=(?! - ) .*?::)"
_DESCRIBED = (
    rf"[\[(].*?[\])]{_BLANK_FREE_NODE}"
    rf"|(?:\[{_UNDASHED}*\](?: \({_UNDASHED}*?\))?|\({_UNDASHED}*?\)){_SPACED_NODE}"
)

# A failure pytest's short summary reports: the outcome, or a subtest's with
# its description, then the node ID or the path whose collection failed, and
# the message after a dash where pytest gives one. A node ID's path, which may
# hold blanks, brackets, and the dash too whatever file it names, as a
# doctest's text file or a module in a directory named with them may, runs to
# one of the test separators the line holds; its test, which may hold blanks
# too, as a doctest's named by its text file does, runs to the bracket
# opening its parameters, the dash, or the line's end. Only a test has
# parameters, which may hold blanks, dashes, and brackets, and end on a
# closing bracket that the dash or the line's end follows. An error may report
# a path alone, whose collection failed, ending on the dash or the line's end
# short of any separator. A message pytest gives opens on a rewritten
# assertion's `assert`, or on the name of the exception it reports, a colon
# after it -- never a test's separator -- unless it says nothing more.
_SUMMARY_RE = re.compile(
    rf"[ \t]*(?:(?P<outcome>FAILED|ERROR)|SUBFAILED(?P<subtest>{_DESCRIBED}))"
    r" (?P<reported>\S.*?)[ \t\r]*",
)
# A run pytest refused before running any test: the error it prints for a
# usage it refuses -- `ERROR:` and the message, its usage line aside -- or
# for an argument it cannot parse, on the line its parser prints naming it.
# Such a line reports no node.
_REFUSED_RE = re.compile(r"[ \t]*(?:ERROR: (?!usage: )|[^:]*pytest[^:]*: error: )(?P<message>\S.*?)[ \t\r]*")
_NODE_SEPARATOR = "::"
_SEPARATOR_RE = re.compile(_NODE_SEPARATOR)
_TEST_RE = re.compile(r"::(?:(?! - |\[).)+?(?=\[| - |\Z)")
_PATH_END_RE = re.compile(r"(?= - )|\Z")
_PARAMETERS_END_RE = re.compile(r"\](?= - |\Z)")
_OPENING_BRACKET = "["
_DELIMITER = " - "
_MESSAGE_RE = re.compile(r"assert\b|[A-Za-z_][\w.]*(?::(?!:)|(?<!\.py)\Z)")

_ERRORED = "ERROR"

# Where a node ID ends, and whether a later split could end it as well.
_End = tuple[int, bool]

# How surely a node ID is a summary line's, given the message after it: a
# key, the greatest surest, empty where nothing names it.
_Naming = Callable[[str, str], tuple[int, ...]]


@dataclass(frozen=True)
class SummaryLine:
    """A failure a line of pytest's short summary reports.

    `node` is the node ID, or the path whose collection failed, and `error`
    what follows it on the line, "" where pytest gives nothing. `errored` says
    the line reports an error outside any test body; `subtest` is the
    description of the subtest it reports, "" for none; and `unsure` says
    nothing named the ID and a later split could have ended it too. A line
    saying pytest refused the run before running any test reports no node,
    "", its message the error.
    """

    node: str
    error: str
    errored: bool = False
    subtest: str = ""
    unsure: bool = False

    @classmethod
    def read(cls, line: str, named: _Naming) -> SummaryLine | None:
        """The failure `line` reports, if it is a summary line of pytest's; None where not.

        `named` says how surely a node ID is the line's, given the message
        after it: by a section pytest printed for it showing that message's
        exception -- the first such no line took yet -- or by its title, or by
        an entry of the findings naming it whole.
        """
        summary = _SUMMARY_RE.fullmatch(line)
        if summary is None:
            return cls._refused(line)
        reported = summary.group("reported")
        found = cls._end(reported, named, summary.group("outcome") == _ERRORED)
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
    def _refused(cls, line: str) -> SummaryLine | None:
        """The run `line` says pytest refused before running any test, with its error; None where it says none."""
        refused = _REFUSED_RE.fullmatch(line)
        if refused is None:
            return None
        return cls("", refused.group("message"), errored=True)

    @classmethod
    def _end(cls, reported: str, named: _Naming, errored: bool) -> _End | None:
        """Where the node ID `reported` opens on ends, and whether that is unsure; None where it holds none.

        An error's may be a path alone, as `errored` says the line reports.

        The ID is the longest of those `named` is surest of, where it names
        any; else it ends on the first split leaving a message of the shape
        pytest gives -- unsure where a later one leaves one too -- and where
        none does, on the last: pytest gave no message.
        """
        ends = cls._ends(reported, errored)
        nodes = [reported[:end] for end in ends]
        messages = [reported[end:].removeprefix(_DELIMITER) for end in ends]
        sure = list(map(named, nodes, messages))
        shaped = list(compress(ends, map(_MESSAGE_RE.match, messages)))
        if any(sure):
            return max(zip(sure, ends, strict=True))[1], False
        if shaped:
            return shaped[0], len(shaped) > 1
        return (ends[-1], False) if ends else None

    @classmethod
    def _ends(cls, reported: str, errored: bool) -> list[int]:
        """Where in `reported` a node ID may end, in order.

        Its path may end at any separator the line holds, and the ID past the
        test after it, or on a closing bracket of its parameters; where the
        line reports an error (`errored`), the ID may be a path alone too.
        """
        separators = (found.start() for found in _SEPARATOR_RE.finditer(reported))
        tested = chain.from_iterable(cls._tested(reported, separator) for separator in separators)
        alone = cls._alone(reported) if errored else []
        return sorted({*tested, *alone})

    @classmethod
    def _tested(cls, reported: str, separator: int) -> list[int]:
        """Where the node ID whose path ends on the separator at `separator` may end: past its test or parameters."""
        test = _TEST_RE.match(reported, separator) if separator else None
        if test is None:
            return []
        if reported.startswith(_OPENING_BRACKET, test.end()):
            return [found.end() for found in _PARAMETERS_END_RE.finditer(reported, test.end())]
        return [test.end()]

    @classmethod
    def _alone(cls, reported: str) -> list[int]:
        """Where a path alone may end in `reported`: on the dash or the line's end, short of any separator."""
        bound = reported.find(_NODE_SEPARATOR)
        ends = (found.start() for found in _PATH_END_RE.finditer(reported))
        return [end for end in ends if end and (bound < 0 or end < bound)]
