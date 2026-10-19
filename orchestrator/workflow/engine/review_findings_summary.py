# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A line of pytest's short summary, read for the failure it reports.

Dormant: no production road reads a summary line yet. It is written for the
lead that is to name, above each check a reviewer's findings show failing, the
failures the check's output reports; that lead reads the output through here
and through `review_findings_pytest`, which reads the rest of pytest's output
for the sections a line reports on.

pytest's short summary reports each failure on a line of its own: its outcome
-- `FAILED` for a test, `ERROR` for an error outside any test body, and
`SUBFAILED` for a subtest that failed, the subtest's description right after
it, its message in brackets and its parameters in parentheses -- then the
node ID, or the path whose collection failed, and the message after a dash
where pytest gives one (`SummaryLine`).

A subtest's message and parameters may hold anything -- brackets,
parentheses, blanks, and the very dash that parts the line's message -- and
its node ID's path blanks, so the description may end on any closing bracket
or parenthesis a blank follows. Of each way the line parts a description from
a node ID after it, the one read is that whose ID the caller names surest
(below), then one whose message and parameters each close the bracket or
parenthesis pytest wrote around them nowhere before their own end, and of
those the longest, so the parameters go with the description rather than the
path.

A parameter may hold the very dash that parts a node ID from its message, and
even text of a message's shape after it, while a message may hold a bracket
and a dash of its own; so where the ID ends is read beside what names one. The
caller says that: handed each ID the line may end on and the message that
would follow it, its naming callback answers how surely the ID is the line's,
as a key the greatest of which is surest, empty where nothing names it -- as a
section of the line's run showing the exception the message opens, the first
no line took yet (`PytestOutput.showing`), since one test's ID may run on into
another's where parameters overlap, or a title pytest gave a section of that
run (`PytestOutput.titled`), would. The ID is the longest of those named
surest, a doctest's offered too where its test, repeating its text file's
name, holds the dash. Where nothing names one, a doctest's ends past that
name, no other test's name repeating its file's; any other ends on the first
split leaving a message of the shape pytest gives -- a rewritten assertion's
`assert`, the name of the exception, a colon after it unless it says nothing
more, its class's name then opening on a capital as no file's suffix does, the
repr of the one exception a group holds, or the `[XPASS(strict)]` of a test
that passed though strictly expected to fail -- so the message is never cut
short, and where a later split leaves one too the line says so
(`SummaryLine.unsure`): the ID may run on into what is read as its message.
Where no split leaves one, it ends on the last, pytest having given no
message.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from itertools import chain, compress, starmap
from operator import attrgetter

# A subtest's description as pytest writes it: its message in brackets, its
# parameters in parentheses, or the one and then the other, a blank between;
# and where one may end, on a closing bracket or parenthesis a blank and more
# of the line follow.
_DESCRIBED_RE = re.compile(r"(?P<message>\[.*\])(?: (?P<parameters>\(.*\)))?|(?P<alone>\(.*\))")
_DESCRIBED_END_RE = re.compile(r"(?<=[\])]) (?=\S)")

# A failure pytest's short summary reports: the outcome -- a subtest's right
# before its description -- then the node ID or the path whose collection
# failed, and the message after a dash where pytest gives one. A node ID's
# path, which may hold blanks, brackets, and the dash too whatever file it
# names, as a doctest's text file or a module in a directory named with them
# may, runs to one of the test separators the line holds; its test, which may
# hold blanks too, as a doctest's named by its text file does, runs to the bracket
# opening its parameters, the dash, or the line's end -- a doctest's past the
# file's name it repeats, though that hold the dash. Only a test has
# parameters, which may hold blanks, dashes, and brackets, and end on a
# closing bracket that the dash or the line's end follows. An error may report
# a path alone, whose collection failed, ending on the dash or the line's end
# short of any separator. A message pytest gives opens on a rewritten
# assertion's `assert`, or on the name of the exception it reports, a colon
# after it -- never a test's separator -- unless it says nothing more, when
# the name's last part, its class's, opens on a capital, as a file's suffix
# -- a doctest's `.txt`, a module's `.py` -- does not; on the repr of the one
# exception a group holds, that class's name and the parenthesis opening its
# arguments, the group's name after it; or on the mark of a test that passed
# though strictly expected to fail, `[XPASS(strict)]`, its reason after it.
_SUMMARY_RE = re.compile(r"[ \t]*(?:(?P<outcome>FAILED|ERROR) |SUBFAILED(?=[\[(]))(?P<reported>\S.*?)[ \t\r]*")
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
_MESSAGE_RE = re.compile(r"assert\b|\[XPASS\(strict\)\]|[A-Za-z_][\w.]*:(?!:)|(?:[A-Za-z_]\w*\.)*[A-Z]\w*(?:\Z|\()")

_ERRORED = "ERROR"

# How surely a node ID is a summary line's, given the message after it: a
# key, the greatest surest, empty where nothing names it.
_Key = tuple[int, ...]
_Naming = Callable[[str, str], _Key]


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

        `named` is handed each node ID the line may end on and the message
        after it, and says how surely that ID is the line's: a key, the
        greatest surest, empty where nothing names it. A subtest's line is
        read the likeliest way it parts its description from its node ID
        (`_Reading.rank`).
        """
        summary = _SUMMARY_RE.fullmatch(line)
        if summary is None:
            return cls.refused(line)
        errored = summary.group("outcome") == _ERRORED
        reading = partial(_Reading.of, named=named, errored=errored)
        readings = filter(None, starmap(reading, cls._splits(summary)))
        found = max(readings, key=attrgetter("rank"), default=None)
        if found is None:
            return None
        return cls(
            found.reported[:found.end],
            found.reported[found.end:].removeprefix(_DELIMITER),
            errored=errored,
            subtest=found.subtest,
            unsure=found.unsure,
        )

    @classmethod
    def refused(cls, line: str) -> SummaryLine | None:
        """The run `line` says pytest refused before running any test, with its error; None where it says none.

        pytest prints that line outside its short summary, which a run it
        refused has none of, so beside the summary lines it is read wherever
        it stands outside every section and capture (`review_findings_pytest`).
        """
        refused = _REFUSED_RE.fullmatch(line)
        if refused is None:
            return None
        return cls("", refused.group("message"), errored=True)

    @classmethod
    def _splits(cls, summary: re.Match[str]) -> list[tuple[str, str]]:
        """Each way the line `summary` read parts a subtest's description from what follows it; for a test's, none.

        A test's or an error's line parts nothing off what it reports.
        """
        reported = summary.group("reported")
        if summary.group("outcome"):
            return [("", reported)]
        splits: list[tuple[str, str]] = []
        for found in _DESCRIBED_END_RE.finditer(reported):
            subtest = reported[:found.start()]
            if _DESCRIBED_RE.fullmatch(subtest):
                splits.append((subtest, reported[found.end():]))
        return splits


@dataclass(frozen=True)
class _Reading:
    """One way to read what a summary line reports past its outcome.

    `subtest` is the description it parts off, "" for none, and `reported`
    what follows it; `named` is how surely the caller named the node ID that
    opens on, `end` where that ends, and `unsure` says a later split could
    end it as well.
    """

    subtest: str
    reported: str
    named: _Key
    end: int
    unsure: bool = False

    @classmethod
    def of(cls, subtest: str, reported: str, named: _Naming, errored: bool) -> _Reading | None:
        """`reported`, past the description `subtest`, read for where its node ID ends; None where it holds none.

        An error's may be a path alone, as `errored` says the line reports.

        The ID is the longest of those `named` is surest of, where it names
        any; else it is read as nothing names it (`_unnamed`).
        """
        ends = cls._ends(reported, errored)
        messages = [reported[end:].removeprefix(_DELIMITER) for end in ends]
        nodes = [reported[:end] for end in ends]
        sure = list(map(named, nodes, messages))
        if any(sure):
            return cls(subtest, reported, *max(zip(sure, ends, strict=True)))
        return cls._unnamed(subtest, reported, ends)

    @property
    def rank(self) -> tuple[_Key, bool, int]:
        """How likely this is the way pytest wrote the line, the greatest likeliest.

        The caller's naming of the node ID decides first; then a description
        written as pytest writes one (`_grouped`) -- a message or parameters
        holding a closing bracket or parenthesis of their own that ends their
        group early read so only where no other way is; then the longest, its
        parameters going with it rather than with the path.
        """
        return self.named, _grouped(self.subtest), len(self.subtest)

    @classmethod
    def _ends(cls, reported: str, errored: bool) -> list[int]:
        """Where in `reported` a node ID may end, in order.

        Its path may end at any separator the line holds, and the ID past the
        test after it, or on a closing bracket of its parameters, or past the
        name of the file a doctest repeats (`_doctests`); where the line
        reports an error (`errored`), the ID may be a path alone too.
        """
        separators = (found.start() for found in _SEPARATOR_RE.finditer(reported))
        tested = chain.from_iterable(cls._tested(reported, separator) for separator in separators)
        alone = cls._alone(reported) if errored else []
        return sorted({*tested, *alone, *cls._doctests(reported)})

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
    def _doctests(cls, reported: str) -> list[int]:
        """Where a doctest's node ID may end in `reported`: past its text file's name, repeated after a separator.

        pytest names a text file's doctest by the file, so the test may hold
        the dash, which ends no other test's name; it ends where that name
        does, on the dash or the line's end.
        """
        ends: list[int] = []
        for found in _SEPARATOR_RE.finditer(reported):
            named = reported[:found.start()].rpartition("/")[2]
            end = found.end() + len(named)
            repeated = reported.startswith(named, found.end())
            if named and repeated and _PATH_END_RE.match(reported, end):
                ends.append(end)
        return ends

    @classmethod
    def _alone(cls, reported: str) -> list[int]:
        """Where a path alone may end in `reported`: on the dash or the line's end, short of any separator."""
        bound = reported.find(_NODE_SEPARATOR)
        ends = (found.start() for found in _PATH_END_RE.finditer(reported))
        return [end for end in ends if end and (bound < 0 or end < bound)]

    @classmethod
    def _unnamed(cls, subtest: str, reported: str, ends: list[int]) -> _Reading | None:
        """`reported`, past `subtest`, read where nothing names its node ID, `ends` where that may end.

        A doctest's ends past its text file's name it repeats, no other test's
        name repeating its file's (`_doctests`); else the ID ends on the first
        split leaving a message of the shape pytest gives -- unsure where a
        later one leaves one too -- and where none does, on the last: pytest
        gave no message.
        """
        doctests = cls._doctests(reported)
        messages = (reported[end:].removeprefix(_DELIMITER) for end in ends)
        shaped = list(compress(ends, map(_MESSAGE_RE.match, messages)))
        if doctests:
            return cls(subtest, reported, (), doctests[0])
        if shaped:
            return cls(subtest, reported, (), shaped[0], len(shaped) > 1)
        return cls(subtest, reported, (), ends[-1]) if ends else None


def _grouped(subtest: str) -> bool:
    """Whether the description `subtest` reads as pytest writes one: no group closing before its own end.

    pytest writes a subtest's message in brackets and its parameters in
    parentheses, so the bracket or parenthesis opening each group closes
    nowhere before that group's end, however many it holds within. No
    description, a test's or an error's, reads so too.
    """
    described = _DESCRIBED_RE.fullmatch(subtest)
    groups = described.groups() if described else ()
    return all(_closes(group) for group in groups if group)


def _closes(group: str) -> bool:
    """Whether the bracket or parenthesis opening `group` stays open up to its last character."""
    opening, closing = group[0], group[-1]
    depth = 0
    for char in group[:-1]:
        depth += int(char == opening) - int(char == closing)
        if not depth:
            return False
    return True
