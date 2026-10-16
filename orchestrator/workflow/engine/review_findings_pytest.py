# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What pytest's output says beside its short summary: the sections it printed, for `review_findings_failures`.

pytest closes a run on a short summary naming each failure on a line of its
own, and above it prints a section for each, titled between underscores --
as few as one each side where the title is long: a failed test's section by
the test's name, one whose fixture failed by `ERROR at setup of` or `ERROR at
teardown of` and that name, and one pytest failed collecting by `ERROR
collecting` and what it collected. A test's name is its node ID past the
path, a dot parting each class from what it holds, the parameters as written
(`PytestOutput.name`). Inside a section a line of underscores and blanks
alone parts a traceback's frames, titling nothing, and a line of equals
signs, a heading inside or not, opens the summary.

A section marks the exception it shows with `E` (`Section`). An assertion's
explanation, a diff hint, or a syntax error's source sets its lines out
further than the exception, and a chained exception marks each exception in
turn, the last the one raised; so a section's exception is the first line set
out least in its last run of marked lines. A section marking no line holds
Python's own traceback, as `--tb=native` prints one and as pytest prints an
exception group -- several fixture finalizers failing, say -- in any mode, and
its exception is the first line at the margin below the traceback's last
header: for a group, the margin its rail sets, past which each exception it
holds stands further in.

With `--tb=line` a failed test has no section: under the failures heading,
pytest prints the file and line it crashed at -- the test's, or a helper's --
and its exception on one line, and each such line is a section titled by
nothing (`PytestOutput.take` reads it for a summary line naming a test).

Tests in different modules may share a name, and their sections a title, so
each summary line takes a section of its own (`PytestOutput.take`). pytest
prints the sections and the summary lines in one order, so a line takes the
first section it may be that no line before it took -- the one whose
exception the line's own error opens, where it gives one.
"""
from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator, Sequence
from dataclasses import dataclass
from itertools import chain, groupby, takewhile

# A section's title, and a line that opens a section: a title, or the
# summary's line of equals signs.
_TITLE_RE = re.compile(r"[ \t]*_+ (?P<title>(?=.*[^_ ]).+?) _+[ \t\r]*")
_SECTION_RE = re.compile(r"[ \t]*(?:_+ (?=.*[^_ ]).+ _+|=+(?: .+ =+)?)[ \t\r]*")

# A line a section marks with `E`, how far it sets out what it says, and what
# it says -- nothing, on a line marked blank.
_MARKED_RE = re.compile(r"[ \t]*E(?:(?P<indent>[ \t]+)(?P<error>.*?))?[ \t\r]*")

# A heading of equals signs, and the one the failures stand under. With
# `--tb=line` a failure has no section of its own there: pytest prints the
# file and line it crashed at, and its exception, on one line.
_HEADING_RE = re.compile(r"[ \t]*=+ (?P<heading>.+?) =+[ \t\r]*")
_FAILURES = "FAILURES"
_LINE_TRACEBACK_RE = re.compile(r"[ \t]*[^\s:]+:\d+: (?P<raised>\S.*?)[ \t\r]*")
_UNTITLED = ""

# The header of a traceback in Python's own form, which `--tb=native` prints
# with no line marked, as pytest prints an exception group in any mode: the
# exception stands on the first line at the margin below the last such header
# -- for a group, the margin its rail sets, `| ` where its header has `+ `,
# below which each exception it holds is set further in, a traceback of its own.
_NATIVE_HEADER_RE = re.compile(
    r"(?P<rail>[ \t]*(?:\+ )?)(?:Exception Group )?Traceback \(most recent call last\):[ \t\r]*",
)
_GROUP_HEADER_RAIL = "+"
_GROUP_RAIL = "|"

_PHASES = ("setup", "teardown")
_IN_PHASE = "ERROR at {phase} of {name}"
_PHASE_TITLE_RE = re.compile(r"ERROR at (?:setup|teardown) of (?P<name>.+)")
_COLLECTING_TITLE_RE = re.compile(r"ERROR collecting (?P<subject>.+)")
_INTERRUPTED_RE = re.compile(r"Interrupted: \d+ errors? during collection")

# What parts a node ID's path from its test and each class from what it
# holds, what opens its parameters, and what parts a class in a test's name.
_NODE_SEPARATOR = "::"
_OPENING_BRACKET = "["
_NAME_SEPARATOR = "."

# pytest's mark of a message it cut short.
_ELLIPSIS = "..."

_UNPHASED = ("", "")


@dataclass(frozen=True)
class Section:
    """One section pytest printed: its title, and the exception it shows, "" for none."""

    title: str
    raised: str

    @classmethod
    def read(cls, title: str, lines: Iterable[str]) -> Section:
        """The section titled `title` that holds `lines`: what its marked lines show, else its native traceback."""
        held = list(lines)
        return cls(title, cls._marked(held) or cls._native(held))

    @classmethod
    def _marked(cls, lines: Sequence[str]) -> str:
        """The exception the last run of lines marked `E` among `lines` shows; "" for none."""
        grouped = groupby(map(_MARKED_RE.fullmatch, lines), key=bool)
        runs = [list(run) for marking, run in grouped if marking]
        return cls._raised(runs[-1]) if runs else ""

    @classmethod
    def _native(cls, lines: Sequence[str]) -> str:
        """The exception the last traceback in Python's own form among `lines` ends on; "" for none."""
        raised = ""
        margin: str | None = None
        for line in lines:
            header = _NATIVE_HEADER_RE.fullmatch(line)
            if header is not None:
                margin = header.group("rail").replace(_GROUP_HEADER_RAIL, _GROUP_RAIL)
                continue
            said = cls._past(line, margin)
            if said[:1].strip():
                raised = said.rstrip()
                margin = None
        return raised

    @classmethod
    def _past(cls, line: str, margin: str | None) -> str:
        """What `line` says past `margin`; "" where no margin is open, or the line stands on another."""
        if margin is None or not line.startswith(margin):
            return ""
        return line[len(margin):]

    @classmethod
    def _raised(cls, run: Sequence[re.Match[str]]) -> str:
        """The first line set out least of the marked lines `run` that say anything."""
        said = [found for found in run if found.group("error")]
        if not said:
            return ""
        widths = [len(found.group("indent").expandtabs()) for found in said]
        return said[widths.index(min(widths))].group("error")


class PytestOutput:
    """A check's output read for the sections pytest printed, each taken by one summary line at most."""

    def __init__(self, lines: Sequence[str]) -> None:
        self.lines = lines
        self._sections = tuple(self._read())
        titles = frozenset(section.title for section in self._sections)
        phased = filter(None, map(_PHASE_TITLE_RE.fullmatch, titles))
        self._sectioned = titles.union(found.group("name") for found in phased)
        self._collected = _collections(self._sections)
        self._interrupted = any(map(_INTERRUPTED_RE.search, lines))
        self._taken: set[int] = set()

    def sectioned(self, node: str) -> bool:
        """Whether pytest printed a section for the test `node` names: its failure's, or its fixture's."""
        name = self.name(node)
        return bool(name) and name in self._sectioned

    def take(self, titles: Collection[str], error: str) -> Section | None:
        """The section titled one of `titles` a summary line giving `error` reports; None for none.

        It is the first such section no line took before, the one whose
        exception `error` opens -- pytest's ellipsis aside -- where one does,
        and is taken.
        """
        untaken = [
            index for index, section in enumerate(self._sections)
            if section.title in titles and index not in self._taken
        ]
        shown = error.removesuffix(_ELLIPSIS)
        opened = [index for index in untaken if _opens(self._sections[index], shown)]
        index = next(chain(opened, untaken), None)
        if index is None:
            return None
        self._taken.add(index)
        return self._sections[index]

    def phase(self, node: str, error: str) -> tuple[str, str]:
        """The phase of the test `node` names whose section a summary line giving `error` reports, and its exception.

        A test may fail in its setup and its teardown both, each with a
        section and a summary line of its own. Both are "" where no section is
        left for the line.
        """
        name = self.name(node)
        titles = {_IN_PHASE.format(phase=phase, name=name): phase for phase in _PHASES}
        section = self.take(titles, error)
        return _UNPHASED if section is None else (titles[section.title], section.raised)

    def collection(self, node: str) -> tuple[str, str] | None:
        """What pytest failed collecting for `node`, and its section's exception; None where nothing says so.

        That is `node` itself, or the path holding it, where a section says
        pytest failed collecting it; the path where collection was
        interrupted; and a path always, pytest's summary naming one for its
        collection alone.
        """
        path = node.partition(_NODE_SEPARATOR)[0]
        titled = [subject for subject in (node, path) if subject in self._collected]
        implied = self._interrupted or path == node
        subject = next(iter(titled), path if implied else None)
        if subject is None:
            return None
        return subject, self._collected.get(subject, "")

    @classmethod
    def name(cls, node: str) -> str:
        """The name pytest titles the section of the test `node` names by.

        That is the ID past its path, a dot parting each class from what it
        holds; the parameters stay as they are, separators they hold too.
        """
        scope, bracket, ids = node.partition(_NODE_SEPARATOR)[2].partition(_OPENING_BRACKET)
        return f"{scope.replace(_NODE_SEPARATOR, _NAME_SEPARATOR)}{bracket}{ids}"

    def _read(self) -> Iterator[Section]:
        """Each section the output holds, in order: each titled one, and each failure `--tb=line` printed untitled.

        A line traceback stands under the failures heading and outside any
        titled section, and is a section with no title of its own.
        """
        traced = False
        for number, line in enumerate(self.lines):
            titled = _TITLE_RE.fullmatch(line)
            if titled is not None:
                yield Section.read(titled.group("title"), _held_below(self.lines, number))
            traced = _traced_below(line, traced and titled is None)
            lined = _LINE_TRACEBACK_RE.fullmatch(line) if traced else None
            if lined is not None:
                yield Section(_UNTITLED, lined.group("raised"))


def _collections(sections: Iterable[Section]) -> dict[str, str]:
    """What each section titled as a collection pytest failed collected, with its exception; the first of a subject."""
    collected: dict[str, str] = {}
    for section in sections:
        found = _COLLECTING_TITLE_RE.fullmatch(section.title)
        if found is not None:
            collected.setdefault(found.group("subject"), section.raised)
    return collected


def _opens(section: Section, shown: str) -> bool:
    """Whether a summary line giving the error `shown` opens on the exception `section` shows."""
    return bool(shown) and section.raised.startswith(shown)


def _traced_below(line: str, traced: bool) -> bool:
    """Whether a line traceback may stand below `line`, where `traced` says whether one may above it.

    One may from the failures heading to the next heading -- or the next title,
    which the caller has `traced` say.
    """
    heading = _HEADING_RE.fullmatch(line)
    return traced if heading is None else heading.group("heading") == _FAILURES


def _held_below(lines: Sequence[str], number: int) -> Iterator[str]:
    """The lines the section line `number` of `lines` opens holds: those up to the next that opens one."""
    below = lines[number + 1:]
    return takewhile(lambda line: _SECTION_RE.fullmatch(line) is None, below)
