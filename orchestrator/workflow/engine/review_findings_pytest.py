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

Below a section's traceback, pytest prints what it captured from the test --
its output, its log -- and what a plugin added to its report, each under a
rule of dashes titling it, up to the next line that opens a section. A test
may print anything there, lines of a traceback's or a summary's shape too, so
no line there is read as pytest's own: a section's exception is read from its
traceback alone, and the summary lines from below the short summary's heading
(`PytestOutput.summary`) -- or, in output quoting the summary lines alone,
from any line nothing captured holds. A test may print a whole run of
pytest's: below a rule, where pytest itself never opens a run, a run's opening
-- its session's heading, or the progress line its first tests report on with
`-q` -- opens one a test printed, captured up to the line of statistics that
closes it. Any other line of a section's or a heading's shape a test prints
ends what is read as captured there, being one pytest might print next; but
pytest prints one short summary for a run, last, so of the summary headings
in one run only the last is pytest's, any above it one a test printed. Outside
anything captured a run opens on its opening, or, with `-q`, where a run
reporting no progress -- one failing collection alone -- opens: on the errors
or failures heading, which pytest prints before a run's summary, standing in
the summary of the run before it.

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
nothing (`PytestOutput.take` reads it for a summary line naming a test). It
prints that line last, below the failure's marked lines and anything it
captured, and the exception it gives is the one the last of those marked
lines shows; so below a rule only a line giving that exception is one, and
it closes what was captured (`_Where`).

Tests in different modules may share a name, and their sections a title, so
each summary line takes a section of its own (`PytestOutput.take`). pytest
prints the sections and the summary lines in one order, so a line takes the
first section it may be that no line before it took -- the one whose
exception the line's own error opens, where it gives one -- and so takes its
own run's. A collection's section names its path relative to pytest's root
directory, and its summary line relative to where pytest ran, so the line
takes a section either spelling of which ends on the other at a directory's
boundary (`PytestOutput.collection`); and a run says collection was
interrupted below its own summary lines, of them alone.
"""
from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import accumulate, chain, compress, groupby, takewhile
from types import MappingProxyType

# A section's title, and a line that opens a section: a title, a rule
# titling what pytest captured below its traceback, or a line of equals signs
# -- a heading, where it titles anything.
_TITLE_RE = re.compile(r"[ \t]*_+ (?P<title>(?=.*[^_ ]).+?) _+[ \t\r]*")
_SECTION_RE = re.compile(
    r"[ \t]*(?:_+ (?=.*[^_ ]).+ _+|(?P<rule>-+ (?=.*[^- ]).+ -+)|=+(?: (?P<heading>.+?) =+)?)[ \t\r]*",
)

# A line a section marks with `E`, how far it sets out what it says, and what
# it says -- nothing, on a line marked blank. `--showlocals` prints each local
# below the traceback as its name padded to ten, ` = `, and its value, so the
# line of a local named `E` is no marked line.
_MARKED_RE = re.compile(r"[ \t]*E(?! {10}= )(?:(?P<indent>[ \t]+)(?P<error>.*?))?[ \t\r]*")

# The headings the failures and the short summary stand under. With
# `--tb=line` a failure has no section of its own under the first: pytest
# prints the file and line it crashed at, and its exception, on one line --
# the file's path holding blanks or not, and the line no marked one.
_FAILURES = "FAILURES"
_SUMMARY = "short test summary info"

# The headings a run reporting no progress opens on with `-q`, those pytest
# prints above its short summary.
_SUMMARISED_BELOW = frozenset((_FAILURES, "ERRORS"))

# What opens a run of pytest's: its session's heading, or, with `-q`, the
# progress line its first tests report on, by percentage or count; and the
# line of statistics closing it, a heading or, with `-q`, not.
_STARTED_RE = re.compile(r"[ \t]*(?:=+ test session starts =+|[.FEsxXR]+[ \t]+\[(?:[ \t]*\d+%|\d+/\d+)\])[ \t\r]*")
_STATS_RE = re.compile(
    r"[ \t]*(?:=+ )?(?:no tests ran|\d+ \w+(?:, \d+ \w+)*) in \d+\.\d+s(?: \([\d:]+\))?(?: =+)?[ \t\r]*",
)
_LINE_TRACEBACK_RE = re.compile(r"[ \t]*(?!E[ \t])[^\s:][^:]*?:\d+: (?P<raised>\S.*?)[ \t\r]*")
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

# Where in the output a line stands: under the failures heading, outside any
# titled section, where `--tb=line` prints each failure's line traceback; in
# the short summary below its heading; or elsewhere -- by the heading opening
# the region.
_TRACED = "traced"
_SUMMARISED = "summarised"
_ELSEWHERE = ""
_HEADED = MappingProxyType({_FAILURES: _TRACED, _SUMMARY: _SUMMARISED})

# A line of a short summary, and whether pytest says it interrupted
# collecting the run the summary closes.
_Summarised = tuple[str, bool]


@dataclass(frozen=True)
class _Where:
    """Where a line of the output stands: its region, and whether in what pytest captured below a rule.

    `nested` says the line stands in a run a test printed, which `nests`
    says may be read; `shown` is the exception the last marked line outside
    anything captured above it shows; `run` counts the session headings at or
    above the line outside anything captured, and `summaries` the short
    summary headings.
    """

    region: str = _ELSEWHERE
    captured: bool = False
    nested: bool = False
    shown: str = ""
    run: int = 0
    summaries: int = 0
    nests: bool = True

    @classmethod
    def of(cls, lines: Sequence[str]) -> tuple[_Where, ...]:
        """Where each of `lines` stands, in turn.

        Where a run a test printed is closed by no line of statistics but the
        output's last -- the run's own -- or by none, the test cut it short,
        and the output is read as if no run were nested, lest that hide the
        run's own summary.
        """
        wheres = tuple(accumulate(lines, cls.below, initial=cls()))
        if _unclosed(lines, wheres):
            wheres = tuple(accumulate(lines, cls.below, initial=cls(nests=False)))
        return wheres[1:]

    @classmethod
    def summary(cls, lines: Sequence[str], wheres: Sequence[_Where]) -> list[_Summarised]:
        """Those of `lines` standing, by `wheres`, in the last short summary of their run; none where none stands.

        pytest prints a run's short summary last, so a summary heading above
        another in one run is one a test printed. Each line goes with whether
        its summary says pytest interrupted that run's collection.
        """
        last = {where.run: where.summaries for where in wheres if where.region == _SUMMARISED}
        stopped = {
            where.summaries
            for line, where in zip(lines, wheres, strict=True)
            if where.summarises(last) and _INTERRUPTED_RE.search(line)
        }
        return [
            (line, where.summaries in stopped)
            for line, where in zip(lines, wheres, strict=True)
            if where.summarises(last)
        ]

    def stands(self, region: str) -> bool:
        """Whether the line stands in `region`, outside anything captured."""
        return self.region == region and not self.captured

    def summarises(self, last: Mapping[int, int]) -> bool:
        """Whether the line stands in its run's last short summary, `last` counting each run's summary headings."""
        return self.stands(_SUMMARISED) and last[self.run] == self.summaries

    def below(self, line: str) -> _Where:
        """Where `line`, the line below the one this says, stands.

        A heading opens a region, and a title closes it; a rule opens what
        pytest captured, and the next line opening a section closes that --
        as does the line traceback `--tb=line` prints last for a failure,
        below anything it captured, giving the exception its marked lines
        showed. A run's opening in what was captured opens a run a test
        printed, and only its line of statistics closes that; outside it, a
        run of pytest's own.
        """
        if self.nested:
            return replace(self, nested=_STATS_RE.fullmatch(line) is None)
        if _STARTED_RE.fullmatch(line) and (self.nests or not self.captured):
            return self._started()
        opened = _SECTION_RE.fullmatch(line)
        if opened is not None:
            return self._opening(opened)
        if self.captured:
            lined = _LINE_TRACEBACK_RE.fullmatch(line)
            crashed = lined is not None and lined.group("raised") == self.shown
            return replace(self, captured=not crashed)
        marked = _MARKED_RE.fullmatch(line)
        error = None if marked is None else marked.group("error")
        return replace(self, shown=error or self.shown)

    def _started(self) -> _Where:
        """Where a run's opening stands: in a run a test printed, in what was captured; else first in its own run."""
        if self.captured:
            return replace(self, nested=True)
        return _Where(run=self.run + 1, summaries=self.summaries, nests=self.nests)

    def _opening(self, opened: re.Match[str]) -> _Where:
        """Where the line `opened` reads as opening a section stands: in what pytest captured, or the region it opens.

        The errors or failures heading opens a run of its own where it stands
        in a short summary, which pytest prints below it in any one run.
        """
        if opened.group("rule"):
            return replace(self, captured=True)
        named = opened.group("heading") or ""
        region = _HEADED.get(named, _ELSEWHERE)
        reopens = named in _SUMMARISED_BELOW and self.stands(_SUMMARISED)
        run = self.run + 1 if reopens else self.run
        summaries = self.summaries + 1 if region == _SUMMARISED else self.summaries
        return _Where(region, shown=self.shown, run=run, summaries=summaries, nests=self.nests)


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

    def opens(self, shown: str) -> bool:
        """Whether a summary line giving the error `shown` opens on the exception this section shows."""
        return bool(shown) and self.raised.startswith(shown)

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
        self._wheres = _Where.of(lines)
        self._sections = tuple(self._read())
        titles = frozenset(section.title for section in self._sections)
        phased = filter(None, map(_PHASE_TITLE_RE.fullmatch, titles))
        self._sectioned = titles.union(found.group("name") for found in phased)
        uncaptured = _uncaptured(lines, self._wheres)
        interrupted = any(map(_INTERRUPTED_RE.search, uncaptured))
        summarised = _Where.summary(lines, self._wheres)
        # The lines pytest's short summary lines may stand on, each with
        # whether pytest interrupted its run's collection. The summary's
        # heading stands in it, so none does only where the output holds none,
        # read then as one run.
        self.summary = summarised or [(line, interrupted) for line in uncaptured]
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
        opened = [index for index in untaken if self._sections[index].opens(shown)]
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

    def collection(self, node: str, error: str, interrupted: bool) -> str | None:
        """The exception pytest failed collecting `node` with, "" for none; None where nothing says it failed to.

        pytest failed collecting `node` itself, or the path holding it, where
        a section says so: the one a summary line giving `error` reports
        (`take`), so a line takes its own run's; where the line's run says
        collection was `interrupted`; and always where `node` is a path,
        pytest's summary naming one for its collection alone.
        """
        path = node.partition(_NODE_SEPARATOR)[0]
        titles = {
            section.title for section in self._sections
            if _collects(section.title, (node, path))
        }
        section = self.take(titles, error)
        if section is not None:
            return section.raised
        return "" if interrupted or path == node else None

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

        A title stands outside anything captured -- a title a run a test
        printed holds is that run's -- and a line traceback under the failures
        heading, outside any titled section and anything captured, is a
        section with no title of its own.
        """
        for number, line in enumerate(self.lines):
            titled = None if self._wheres[number].captured else _TITLE_RE.fullmatch(line)
            if titled is not None:
                yield Section.read(titled.group("title"), _held_below(self.lines, number))
            traced = self._wheres[number].stands(_TRACED)
            lined = _LINE_TRACEBACK_RE.fullmatch(line) if traced else None
            if lined is not None:
                yield Section(_UNTITLED, lined.group("raised"))


def _collects(title: str, subjects: Iterable[str]) -> bool:
    """Whether the section titled `title` says pytest failed collecting one of `subjects`.

    pytest titles it by a path relative to its root directory, and its summary
    line names one relative to where it ran, so either spelling may end on the
    other at a directory's boundary.
    """
    found = _COLLECTING_TITLE_RE.fullmatch(title)
    titled = "" if found is None else f"/{found.group('subject')}"
    rooted = (f"/{subject}" for subject in subjects)
    alike = (titled.endswith(spelled) or spelled.endswith(titled) for spelled in rooted)
    return bool(titled) and any(alike)


def _uncaptured(lines: Sequence[str], wheres: Iterable[_Where]) -> list[str]:
    """Those of `lines` standing, by `wheres`, outside anything captured."""
    return list(compress(lines, (not where.captured for where in wheres)))


def _unclosed(lines: Sequence[str], wheres: Sequence[_Where]) -> bool:
    """Whether a run a test printed runs on into the output's last line of statistics, or its end.

    `wheres` says where each of `lines` stands, the first where the line above
    them does.
    """
    stats = [number for number, line in enumerate(lines) if _STATS_RE.fullmatch(line)]
    last = stats[-1] if stats else len(lines)
    return wheres[last].nested or wheres[-1].nested


def _held_below(lines: Sequence[str], number: int) -> Iterator[str]:
    """The lines the section line `number` of `lines` opens holds: those up to the next that opens one."""
    below = lines[number + 1:]
    return takewhile(lambda line: _SECTION_RE.fullmatch(line) is None, below)
