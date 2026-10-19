# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What pytest's output says beside its short summary: the sections it printed, for `review_findings_failures`.

pytest closes a run on a short summary naming each failure on a line of its
own, and above it prints a section for each, titled between underscores -- as
few as one each side where the title is long: a failed test's section by the
test's name, one whose fixture failed by `ERROR at setup of` or `ERROR at
teardown of` and that name, and one pytest failed collecting by `ERROR
collecting` and what it collected. A test's name is its node ID past the path,
a dot parting each class from what it holds, the parameters as written
(`PytestOutput.name`). Inside a section a line of underscores and blanks alone
parts a traceback's frames, titling nothing, and a line of equals signs, a
heading inside or not, opens the summary. A run may fail before running any
test -- a conftest pytest could not load, its traceback below the line saying
so, or a plugin it could not import, the last line of its traceback -- and
each is read as a section of its own, titled by the line saying so
(`Section.failed`).

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
closes it. pytest pads every title, rule, and heading of a run to its
terminal's width, so a line of a section's or a heading's shape narrower than
the last heading pytest printed is one a test printed, and stays captured; any
other ends what is read as captured there, being one pytest might print next.
Below a heading reporting what did not fail -- tests that passed (`-rP`),
passed unexpectedly, or failed as expected (`--xfail-tb`) -- every line reads
as captured up to the next heading, its sections titled as a failure's are.
pytest prints one short summary for a run, last, so of the summary headings in
one run only the last is pytest's, any above it one a test printed. Outside
anything captured a run opens on its opening, or, with `-q`, where a run
reporting no progress -- one failing collection alone -- opens: on the errors
or failures heading, which pytest prints before a run's summary, standing in
the summary of the run before it; and on any heading or title below the line
of statistics closing a run, below which pytest prints nothing of that run's
-- with `-q -s` a run's progress letters carry no percentage to open it by.

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
each summary line takes a section of its own (`PytestOutput.take`): one of
its own run -- a run printed with `--tb=no` has none, and borrows none of the
next run's -- and of those the first no line before it took, since pytest
prints the sections and the summary lines in one order, the one whose
exception the line's own error opens where it gives one. A collection's
section names its path relative to pytest's root directory, and its summary
line relative to where pytest ran, so the line takes a section either
spelling of which ends on the other at a directory's boundary
(`PytestOutput.collection`); and a run says collection was interrupted below
its own summary lines, of them alone.
"""
from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import accumulate, chain, compress, count, groupby, takewhile
from types import MappingProxyType

# A section's title, and a line that opens a section: a title, a rule
# titling what pytest captured below its traceback, or a line of equals signs
# -- a heading, where it titles anything. pytest pads each to its terminal's
# width -- one too long for it set off by a character each side, wider still.
_TITLE_RE = re.compile(r"[ \t]*_+ (?P<title>(?=.*[^_ ]).+?) _+[ \t\r]*")
_SECTION_RE = re.compile(
    r"[ \t]*(?P<line>_+ (?=.*[^_ ]).+ _+|(?P<rule>-+ (?=.*[^- ]).+ -+)"
    r"|(?P<equals>=+)(?: (?P<heading>.+?) =+)?)[ \t\r]*",
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

# The headings pytest reports what did not fail under -- tests that passed
# (`-rP`), passed unexpectedly, or failed as expected (`--xfail-tb`) -- each
# with sections titled as a failure's are: nothing under them is read.
_UNFAILED = frozenset(("PASSES", "XPASSES", "XFAILURES"))

# What opens a run of pytest's: its session's heading, or, with `-q`, the
# progress line its first tests report on, by percentage or count, a letter
# for each outcome -- a subtest's `u`, `y`, or `-` among them; and the line of
# statistics closing it, a heading or, with `-q`, not, each count naming its
# outcome in a word or more -- `1 subtests passed` too.
_STARTED_RE = re.compile(
    r"[ \t]*(?:=+ test session starts =+|[.FEsxXRuy-]+[ \t]+\[(?:[ \t]*\d+%|\d+/\d+)\])[ \t\r]*",
)
_COUNT = r"\d+ \w+(?: \w+)*"
_STATS_RE = re.compile(
    rf"[ \t]*(?:=+ )?(?:no tests ran|{_COUNT}(?:, {_COUNT})*) in \d+\.\d+s(?: \([\d:]+\))?(?: =+)?[ \t\r]*",
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
_PHASE_TITLE_RE = re.compile(r"ERROR at (?P<phase>setup|teardown) of (?P<name>.+)")
_COLLECTING_TITLE_RE = re.compile(r"ERROR collecting (?P<subject>.+)")
COLLECTION = "collection"

# What may make up a blank, a CRLF line's carriage return included.
_BLANKS = " \t\r"

# What pytest prints failing before it runs any test: a conftest it could not
# load, its traceback below the line saying so; and a plugin it could not
# import, the last line of its traceback.
_LOADING_RE = re.compile(r"ImportError while loading conftest '(?P<subject>.+)'\.")
_IMPORTING_RE = re.compile(r'ImportError: Error importing plugin "(?P<subject>.+?)": .+')
CONFTEST = "conftest"
PLUGIN = "plugin"

# What a section says failed where its title says nothing of a phase: the
# test it names, or -- untitled -- nothing.
_IN_TEST = ""
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

# A line of a short summary, and the run the summary closes, by its count of
# runs opened above it (`_Where.run`).
_Summarised = tuple[str, int]


@dataclass(frozen=True)
class _Where:
    """Where a line of the output stands: its region, and whether in what pytest captured below a rule.

    `nested` says the line stands in a run a test printed, which `nests`
    says may be read; `shown` is the exception the last marked line outside
    anything captured above it shows; `run` counts the session headings at or
    above the line outside anything captured, and `summaries` the short
    summary headings; `closed` says a line of statistics closed the run
    above the line, no section or heading opening since; `width` is that of
    the last heading pytest printed, 0 before any; and `heading` that
    heading's title, "" for none -- the line stands as captured below one
    reporting what did not fail.
    """

    region: str = _ELSEWHERE
    captured: bool = False
    nested: bool = False
    shown: str = ""
    run: int = 0
    summaries: int = 0
    nests: bool = True
    closed: bool = False
    width: int = 0
    heading: str = ""

    @classmethod
    def of(cls, lines: Sequence[str]) -> tuple[_Where, ...]:
        """Where each of `lines` stands, in turn.

        Where a run a test printed is closed by no line of statistics but the
        output's last -- the run's own -- or by none, the test cut it short,
        and the output is read as if no run were nested, lest that hide the
        run's own summary.
        """
        wheres = tuple(accumulate(lines, cls.below, initial=cls()))
        # A nested run is unclosed where it runs on into the output's last
        # line of statistics, or its end; the first of `wheres` stands above
        # the lines.
        stats = [number for number, line in enumerate(lines) if _STATS_RE.fullmatch(line)]
        last = stats[-1] if stats else len(lines)
        if wheres[last].nested or wheres[-1].nested:
            wheres = tuple(accumulate(lines, cls.below, initial=cls(nests=False)))
        return wheres[1:]

    @classmethod
    def summary(cls, lines: Sequence[str], wheres: Sequence[_Where]) -> list[_Summarised]:
        """Those of `lines` standing, by `wheres`, in the last short summary of their run, each with that run.

        pytest prints a run's short summary last, so a summary heading above
        another in one run is one a test printed. None stand where no summary
        does.
        """
        last = {where.run: where.summaries for where in wheres if where.region == _SUMMARISED}
        return [
            (line, where.run)
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
        run of pytest's own, which its line of statistics closes -- a heading
        or not -- ending its short summary too.
        """
        if self.nested:
            return replace(self, nested=_STATS_RE.fullmatch(line) is None)
        opened = self._opened(line)
        if opened is not None:
            return opened
        if self.captured:
            lined = _LINE_TRACEBACK_RE.fullmatch(line)
            crashed = lined is not None and lined.group("raised") == self.shown
            return replace(self, captured=not crashed)
        marked = _MARKED_RE.fullmatch(line)
        error = None if marked is None else marked.group("error")
        return replace(self, shown=error or self.shown)

    def _opened(self, line: str) -> _Where | None:
        """Where `line` stands where it opens or closes a run, or opens a section; None where it does none of those.

        A run's opening in what was captured opens a run a test printed, where
        such a run may be read, and outside it stands first in its own run;
        a line of statistics outside anything captured closes its run, and
        that run's short summary with it; and a line opening a section opens
        what `_opening` says -- in what was captured, only one as wide as the
        last heading pytest printed, one narrower being a test's.
        """
        started = _STARTED_RE.fullmatch(line) is not None
        if started and self.captured and self.nests:
            return replace(self, nested=True)
        if started and not self.captured:
            return _Where(
                run=self.run + 1, summaries=self.summaries,
                nests=self.nests, width=self.width,
            )
        if _STATS_RE.fullmatch(line) and not self.captured:
            return replace(self, region=_ELSEWHERE, closed=True)
        section = _SECTION_RE.fullmatch(line)
        if section is None:
            return None
        narrower = len(section.group("line")) < self.width
        return None if self.captured and narrower else self._opening(section)

    def _opening(self, opened: re.Match[str]) -> _Where:
        """Where the line `opened` reads as opening a section stands: in what pytest captured, or the region it opens.

        A line of statistics closes a run -- printed as a heading or, with
        `-q`, not -- and pytest prints nothing of a run's below it, so any
        heading or title below one opens a run of its own: a run's progress
        letters, printed with `-q -s`, carry no percentage to open it by. So
        does the errors or failures heading where it stands in a short
        summary, which pytest prints below it in any one run. Below a heading
        reporting what did not fail, every section -- its title among them --
        reads as captured, up to the next heading.
        """
        if opened.group("rule"):
            return replace(self, captured=True)
        named = opened.group("heading") or ""
        region = _HEADED.get(named, _ELSEWHERE)
        heading = named if opened.group("equals") else self.heading
        reopens = self.closed or (named in _SUMMARISED_BELOW and self.stands(_SUMMARISED))
        return _Where(
            region,
            captured=heading in _UNFAILED,
            shown=self.shown,
            run=self.run + int(reopens),
            summaries=self.summaries + int(region == _SUMMARISED),
            nests=self.nests,
            closed=_STATS_RE.fullmatch(opened.string) is not None,
            width=len(opened.group("line")) if opened.group("equals") else self.width,
            heading=heading,
        )


@dataclass(frozen=True)
class Section:
    """One section pytest printed: its title, the exception it shows, "" for none, and the run it stands in."""

    title: str
    raised: str
    run: int

    @classmethod
    def read(cls, title: str, lines: Iterable[str], run: int) -> Section:
        """The section of `run` titled `title` holding `lines`, its exception read off its marked lines or traceback."""
        held = list(lines)
        return cls(title, cls._marked(held) or cls._native(held), run)

    @property
    def failed(self) -> tuple[str, str]:
        """What this section says failed, by its title: the phase, and what failed in it.

        A collection pytest failed is said with the path it collected, a
        fixture's setup or teardown with the name of its test, a conftest or
        a plugin pytest could not load before running any test with its path
        or name, and a test's own failure with its name and no phase ("") --
        one `--tb=line` printed untitled names nothing.
        """
        collecting = _COLLECTING_TITLE_RE.fullmatch(self.title)
        phased = _PHASE_TITLE_RE.fullmatch(self.title)
        loading = _LOADING_RE.fullmatch(self.title)
        importing = _IMPORTING_RE.fullmatch(self.title)
        if collecting is not None:
            return COLLECTION, collecting.group("subject")
        if phased is not None:
            return phased.group("phase", "name")
        if loading is not None:
            return CONFTEST, loading.group("subject")
        if importing is not None:
            return PLUGIN, importing.group("subject")
        return _IN_TEST, self.title

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
    """A check's output read for the sections pytest printed, each taken by one summary line at most.

    `sections` are those sections, in order, a failure pytest printed before
    running any test first; and `titled` what each says failed
    (`Section.failed`) -- the name of each test pytest printed one for, its
    failure's or its fixture's, among them -- with the run it stands in, a
    run's summary lines naming only its own.
    """

    def __init__(self, lines: Sequence[str]) -> None:
        self.lines = lines
        self._wheres = _Where.of(lines)
        unstarted = _unstarted(lines, self._wheres)
        self.sections = tuple(chain(unstarted, self._read()))
        failed = ((section.failed[1], section.run) for section in self.sections)
        self.titled = frozenset(failed)
        # The lines pytest's short summary lines may stand on, each with the
        # run it closes. The summary's heading stands in it, so none does
        # only where the output holds none.
        self.summary = (
            _Where.summary(lines, self._wheres) or _uncaptured(lines, self._wheres)
        )
        interrupted = (run for line, run in self.summary if _INTERRUPTED_RE.search(line))
        self._interrupted = frozenset(interrupted)
        self._taken: set[int] = set()

    def showing(self, node: str, error: str, run: int) -> int | None:
        """The number of the first section of `run` no line took yet showing what `error` opens; None for none.

        It is a section pytest printed for the test `node` names -- its
        failure's or its fixture's -- or a failure `--tb=line` printed
        untitled, which names no test, whose exception the `error` a summary
        line of `run` gives after `node` opens, pytest's ellipsis aside. The
        first, since pytest prints its sections and its summary lines in one
        order.
        """
        name = self.name(node)
        shown = error.removesuffix(_ELLIPSIS)
        shows = (
            section.run == run
            and section.failed[1] in {name, _UNTITLED}
            and section.opens(shown)
            for section in self.sections
        )
        untaken = (number for number in compress(count(), shows) if number not in self._taken)
        return next(untaken, None) if name else None

    def take(self, titles: Collection[str], error: str, run: int) -> Section | None:
        """The section titled one of `titles` a summary line of `run` giving `error` reports; None for none.

        It is the first such section of the line's run no line took before,
        the one whose exception `error` opens -- pytest's ellipsis aside --
        where one does, and is taken.
        """
        untaken = [
            index for index, section in enumerate(self.sections)
            if section.title in titles and section.run == run and index not in self._taken
        ]
        shown = error.removesuffix(_ELLIPSIS)
        opened = [index for index in untaken if self.sections[index].opens(shown)]
        index = next(chain(opened, untaken), None)
        if index is None:
            return None
        self._taken.add(index)
        return self.sections[index]

    def phase(self, node: str, error: str, run: int) -> tuple[str, str]:
        """The phase of the test `node` names whose section a line of `run` giving `error` reports, and its exception.

        A test may fail in its setup and its teardown both, each with a
        section and a summary line of its own. Both are "" where no section is
        left for the line.
        """
        name = self.name(node)
        titles = {_IN_PHASE.format(phase=phase, name=name): phase for phase in _PHASES}
        section = self.take(titles, error, run)
        return _UNPHASED if section is None else (titles[section.title], section.raised)

    def collection(self, node: str, error: str, run: int) -> str | None:
        """The exception pytest failed collecting `node` with, "" for none; None where nothing says it failed to.

        pytest failed collecting `node` itself, or the path holding it, where
        a section says so -- the one a summary line of `run` giving `error`
        reports (`take`), whatever the path's shape -- and where that run says
        collection was interrupted.
        """
        path = node.partition(_NODE_SEPARATOR)[0]
        titles = {
            section.title for section in self.sections
            if _collects(section, (node, path))
        }
        section = self.take(titles, error, run)
        if section is not None:
            return section.raised
        return "" if run in self._interrupted else None

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
        for number, where in enumerate(self._wheres):
            line = self.lines[number]
            titled = None if where.captured else _TITLE_RE.fullmatch(line)
            if titled is not None:
                yield Section.read(
                    titled["title"], _held_below(self.lines, number), where.run,
                )
            lined = _LINE_TRACEBACK_RE.fullmatch(line) if where.stands(_TRACED) else None
            if lined is not None:
                yield Section(_UNTITLED, lined["raised"], where.run)


def _collects(section: Section, subjects: Iterable[str]) -> bool:
    """Whether `section` says pytest failed collecting one of `subjects`.

    pytest titles it by a path relative to its root directory, and its summary
    line names one relative to where it ran, so either spelling may end on the
    other at a directory's boundary. A section saying nothing of a collection
    says it of none.
    """
    phase, collected = section.failed
    titled = f"/{collected}" if phase == COLLECTION else ""
    rooted = (f"/{subject}" for subject in subjects)
    alike = (titled.endswith(spelled) or spelled.endswith(titled) for spelled in rooted)
    return bool(titled) and any(alike)


def _uncaptured(lines: Sequence[str], wheres: Sequence[_Where]) -> list[_Summarised]:
    """Those of `lines` standing, by `wheres`, outside anything captured, each with the run it stands in."""
    return [
        (line, where.run)
        for line, where in zip(lines, wheres, strict=True)
        if not where.captured
    ]


def _unstarted(lines: Sequence[str], wheres: Sequence[_Where]) -> Iterator[Section]:
    """Each failure pytest printed before it ran any test, outside anything captured, as a section of its own.

    A conftest it could not load is titled by the line saying so, its
    exception the one the traceback below it shows; a plugin it could not
    import by the last line of its traceback, which is its exception too.
    """
    for number, where in enumerate(wheres):
        line = "" if where.captured else lines[number].strip(_BLANKS)
        loading = _LOADING_RE.fullmatch(line)
        importing = _IMPORTING_RE.fullmatch(line)
        if loading is not None:
            yield Section.read(line, _held_below(lines, number), where.run)
        if importing is not None:
            yield Section(line, line, where.run)


def _held_below(lines: Sequence[str], number: int) -> Iterator[str]:
    """The lines the section line `number` of `lines` opens holds: those up to the next that opens one."""
    below = lines[number + 1:]
    return takewhile(lambda line: _SECTION_RE.fullmatch(line) is None, below)
