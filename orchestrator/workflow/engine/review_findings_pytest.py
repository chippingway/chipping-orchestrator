# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What pytest's output says beside its short summary: the sections it printed, and where its summary lines stand.

The lead above each check a reviewer's findings show failing
(`review_findings_failures`) reads the output once (`PytestOutput`), each line
that may report a failure with the run it stands in (`PytestOutput.summary`),
and hands each to `review_findings_summary.SummaryLine.read`, naming its ID by the
sections here (`PytestOutput.showing`, `PytestOutput.titled`); then it takes
the section the line reports -- a test's (`PytestOutput.take`), a setup's or a
teardown's (`PytestOutput.phase`), or a collection's
(`PytestOutput.collection`) -- each section going to one line at most, and
finds what no line took by taking each section's own title in turn.

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
(`Section.failed`), where that line stands outside every section, summary, and
capture -- below the statistics closing a run printed with no summary, say: a
test's traceback may end on an exception of either shape.

Below a section's traceback, pytest prints what it captured from the test --
its output, its log -- and what a plugin added to its report, each under a
rule of dashes titling it, up to the next line that opens a section. A test
may print anything there, lines of a traceback's or a summary's shape too, so
no line there is read as pytest's own: a section's exception is read from its
traceback alone, and the summary lines from below the short summary's heading
(`PytestOutput.summary`) -- or, in output quoting the summary lines alone,
from any line nothing captured holds below no heading and no run's opening:
pytest prints a run's summary lines below their heading alone, so in output
holding a run's headings and none of that one -- a run printed with `-rN` -- a
line of their shape is a traceback's, say an exception's message running on
below it. A run pytest refused before running any test -- a path it could not
find, an argument it could not parse -- has no summary: pytest prints the
error refusing it outside any section, so that error is read from any line
standing outside every section, summary, and capture, wherever it falls among
the check's other runs, and from no other line, a section's traceback being
free to print an exception's message of its shape (`_Where.reports`). A test
may print a whole run of pytest's: below a rule, where pytest itself opens a
run only right below a `-q` line of statistics closing its own, a run's
opening -- its session's heading, the progress line its first tests report on
with `-q`, or, with `-q -s`, whose progress letters carry no percentage, a
heading right below a line of them -- opens one a test printed, captured up to
the line of statistics that closes it, and a run that one captured in turn
opens one inside it the same way, closed by its own statistics alone -- one
`-q` progress line right below another going on with its run; where only the
output's last such line, or none, closes it, the test cut it short, and it is
read as no run from its opening on, lest that hide the run's own summary,
every run a test printed above it still read as one. pytest pads every title,
rule, and heading of a run to its terminal's width, so a line of a section's
or a heading's shape narrower than the last heading pytest printed is one a
test printed, and stays captured; any other ends what is read as captured
there, being one pytest might print next. Below a heading reporting what did
not fail -- tests that passed (`-rP`), passed unexpectedly, or failed as
expected (`--xfail-tb`) -- every line reads as captured up to the next
heading, its sections titled as a failure's are; so does every line below a
warnings summary's heading -- the run's, or the final one below its short
summary, for warnings its terminal summary raised -- a warning's text saying
anything. pytest prints one short summary for a run, below every section, so
of the summary headings in one run only the last is pytest's, any above it one
a test printed. Outside anything captured a run opens on its opening, or, with
`-q`, where a run reporting no progress -- one failing collection alone --
opens: on the errors or failures heading, which pytest prints before a run's
summary, standing in the summary of the run before it; and on any heading or
title below the line of statistics closing a run, below which pytest prints
nothing of that run's -- with `-q -s` a run's progress letters carry no
percentage to open it by. A line of statistics standing in a section's text,
or in what pytest captured, closes its run only where nothing of that run can
follow it -- `-q` prints them right below either where a run prints no
summary: the output ends below it, a `-q -s` run's progress letters follow, or
the next line is one pytest prints beginning a run alone -- its opening, the
errors heading, a conftest or a plugin it could not load -- or the error
refusing it; or pytest's banner of a run it stopped early -- its collection
interrupted, say -- stands right above it; or the first line of pytest's own
shapes below it, past any text a runner printed between two runs, is a
heading, as a `-q --tb=no` run reporting no progress opens on, right below a
blank line -- pytest ending its progress line before a run's terminal summary,
a blank one where it printed no progress, and printing that summary's headings
right below a section's text or what it captured -- or a run's opening that
nothing of a run around the one it opens follows below that one's statistics,
as something would a run a test printed below a line of their shape; or the
next line is a heading right below them in a section's text below no traceback
in Python's own form -- a group's aside, its rail setting out every line --
since only such a traceback's message runs on there in lines of their shape, a
marked traceback's in marked lines. A section's text ends there too. Below any
other line it is that text's own, as an exception's message may say it, and
closes nothing (`_Walk`).

A section's exception is the one its last traceback shows (`Section`): the one
below the last line saying another exception was raised handling the one
above, or from it, or the section's only one. In Python's own form, as
`--tb=native` prints a traceback and as pytest prints an exception group --
several fixture finalizers failing, say -- in any mode, its exception is the
first line at the margin below the traceback's last header: for a group, the
margin its rail sets, past which each exception it holds stands further in.
Its message may run on below that in lines of any shape, marked ones too. Any
other traceback marks the exception it shows with `E`: an assertion's
explanation, a diff hint, or a syntax error's source sets its lines out
further than the exception, and a chained exception marks each exception in
turn, the last the one raised; so its exception is the first line set out
least in its last run of marked lines.

With `--tb=line` a failed test has no section: under the failures heading,
pytest prints the file and line it crashed at -- the test's, or a helper's --
and its exception on one line, at the margin of the failure's marked lines
above it, and each such line is a section titled by nothing
(`PytestOutput.take` reads it for a summary line naming a test); one of its
shape set out further is their explanation's, as an assertion's diff may hold
one. It prints that line last, below the failure's marked lines and anything
it captured, and the exception it gives is the one the last of those marked
lines shows -- or, for an exception group, which pytest prints in Python's own
form in any mode, the group's own, or, the group holding one exception, that
exception's repr and the group's name (`Section.says`); so below a rule only a
line giving that exception, at their margin, is one, and it closes what was
captured (`_Where`). A strict XPASS has no crash location, so pytest prints
its mark and reason in that line's stead, cut at fifty characters -- pytest 9
below the same text its report printed above anything it captured, read as
its section, the line repeating it closing the capture and no section of its
own; pytest 8 that line alone, its section. pytest 9 prints no line traceback
of a crash right below the failures heading or another line traceback, its
report standing between, so a run where one stands so is pytest 8's, each
mark in it a failure's own, however alike two in turn (`_Walk.bare`).

Tests in different modules may share a name, and their sections a title, so
each summary line takes a section of its own (`PytestOutput.take`): one of its
own run -- a run printed with `--tb=no` has none, and borrows none of the next
run's -- and of those the first no line before it took, since pytest prints
the sections and the summary lines in one order, the one whose exception the
line's own error opens where it gives one, though pytest gives a rewritten
assertion without the `AssertionError: ` Python's own form keeps. A section
`--tb=line` printed untitled names no test, so a line giving an error takes
one only where that error opens on its exception: a failure whose report is
text alone -- a plugin's, say -- gets in its line traceback's stead that text
cut short, of no shape read here but a strict XPASS's, so its line takes none
rather than the next failure's. A collection's section names its path
relative to pytest's root directory, and its summary line relative to where
pytest ran, so the line takes a section either spelling of which ends on the
other at a directory's boundary (`PytestOutput.collection`); and a run says
collection was interrupted below its own summary lines, of them alone, on
pytest's banner saying so: no exception's message says it there.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Collection, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from functools import cached_property
from itertools import accumulate, chain, compress, count, dropwhile, filterfalse, groupby, takewhile
from operator import gt
from types import MappingProxyType

from orchestrator.workflow.engine import review_findings_summary as _summary

# A section's title, and a line that opens a section: a title, a rule
# titling what pytest captured below its traceback, or a line of equals signs
# -- a heading, where it titles anything. pytest pads each to its terminal's
# width -- one too long for it set off by a character each side, wider still
# -- and a title, or a rule's, says more than its padding, a CRLF line's
# carriage return no word of it; and a line of equals signs alone, titling
# anything or nothing.
_HEADING = r"(?P<equals>=+)(?: (?P<heading>.+?) =+)?"
_TITLE_RE = re.compile(r"[ \t]*_+ (?P<title>(?=.*[^_ \t\r]).+?) _+[ \t\r]*")
_SECTION_RE = re.compile(
    r"[ \t]*(?P<line>_+ (?=.*[^_ \t\r]).+ _+|(?P<rule>-+ (?=.*[^- \t\r]).+ -+)"
    rf"|{_HEADING})[ \t\r]*",
)
_HEADING_RE = re.compile(rf"[ \t]*{_HEADING}[ \t\r]*")

# A line a section marks with `E`, how far it sets out what it says, and what
# it says -- nothing, on a line marked blank. `--showlocals` prints each local
# below the traceback as its name padded to ten, ` = `, and its value, so the
# line of a local named `E` is no marked line.
_MARKED_RE = re.compile(r"(?P<margin>[ \t]*)E(?! {10}= )(?:(?P<indent>[ \t]+)(?P<error>.*?))?[ \t\r]*")

# The headings the failures and the short summary stand under. With
# `--tb=line` a failure has no section of its own under the first: pytest
# prints the file and line it crashed at, and its exception, on one line --
# the file's path holding blanks or colons or neither, though no colon a blank
# follows, as one does the name of an exception, and the line no marked one.
_FAILURES = "FAILURES"
_SUMMARY = "short test summary info"

# The headings a run reporting no progress opens on with `-q`, those pytest
# prints above its short summary; the first of them pytest prints first in a
# run, nothing of the run before it.
_ERRORS = "ERRORS"
_SUMMARISED_BELOW = frozenset((_FAILURES, _ERRORS))
_ERRORS_RE = re.compile(rf"[ \t]*=+ {_ERRORS} =+[ \t\r]*")

# The headings pytest reports what did not fail under -- tests that passed
# (`-rP`), passed unexpectedly, or failed as expected (`--xfail-tb`) -- each
# with sections titled as a failure's are, and the warnings a run raised,
# those its terminal summary raised under a heading of their own below the
# short summary, a warning's text saying anything: nothing under them is read.
_UNFAILED = frozenset(("PASSES", "XPASSES", "XFAILURES", "warnings summary", "warnings summary (final)"))

# What opens a run of pytest's: its session's heading, or, with `-q`, the
# progress line its first tests report on, by percentage or count, a letter
# for each outcome -- a subtest's `u`, `y`, or `-` among them; and the line of
# statistics closing it, a heading or, with `-q`, not, each count naming its
# outcome in a word or more -- `1 subtests passed` too.
_LETTER = r"[.FEsxXRuy-]"
_STARTED_RE = re.compile(
    rf"[ \t]*(?:=+ test session starts =+|{_LETTER}+[ \t]+\[(?:[ \t]*\d+%|\d+/\d+)\])[ \t\r]*",
)
_COUNT = r"\d+ \w+(?: \w+)*"
_STATS_RE = re.compile(
    rf"[ \t]*(?:=+ )?(?:no tests ran|{_COUNT}(?:, {_COUNT})*) in \d+\.\d+s(?: \([\d:]+\))?(?: =+)?[ \t\r]*",
)

# A line of progress letters alone, as `-q -s` prints them with no
# percentage, or a blank one; and such a line of letters, not blank.
_PROGRESS_RE = re.compile(rf"[ \t]*{_LETTER}*[ \t\r]*")
_LETTERED_RE = re.compile(rf"[ \t]*{_LETTER}+[ \t\r]*")

# A run's opening, read below the line above it: its session's heading, the
# first of its `-q` progress lines -- one right below another goes on with its
# run -- or, with `-q -s`, whose progress letters carry no percentage, the
# heading right below a line of them.
_OPENS_RE = re.compile(
    rf"(?!{_STARTED_RE.pattern}\n).*\n{_STARTED_RE.pattern}|{_LETTERED_RE.pattern}\n{_HEADING_RE.pattern}",
)

# A strict XPASS has no crash location, so in its line traceback's stead
# `--tb=line` prints its mark and reason, cut at fifty characters -- pytest 9
# below the same text its report printed above anything it captured.
_XPASS_MARK = "[XPASS(strict)]"
_XPASSED_RE = re.compile(rf"[ \t]*(?P<report>{re.escape(_XPASS_MARK)}.*?)[ \t\r]*")
_CRASHED = r"(?!E[ \t])[^\s:](?:[^:]|:(?! ))*?:\d+: "
_LINE_TRACEBACK_RE = re.compile(
    rf"(?P<margin>[ \t]*)(?:{_CRASHED}|(?={re.escape(_XPASS_MARK)}))(?P<raised>\S.*?)[ \t\r]*",
)

# pytest 9 prints each failure's report above its line traceback -- marked
# lines, a group's traceback, what it captured -- and pytest 8 the line alone:
# a line traceback of a crash right below the failures heading, or another
# line traceback, with the newline ending it, is pytest 8's.
_CRASHED_RE = re.compile(rf"[ \t]*{_CRASHED}\S.*")
_BARED_RE = re.compile(rf"(?:{_LINE_TRACEBACK_RE.pattern}|{_HEADING_RE.pattern})\n")
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

# The line parting one exception's traceback from that of the next, raised
# handling it or from it, in Python's own form and in pytest's alike.
_CHAINED_RE = re.compile(
    r"[ \t]*(?:During handling of the above exception, another exception occurred"
    r"|The above exception was the direct cause of the following exception):[ \t\r]*",
)

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

# What pytest prints beginning a run alone: its opening, the errors heading a
# `-q` run failing collection alone opens on, the line saying a conftest it
# could not load, or a traceback in Python's own form at the margin, as for a
# plugin it could not import.
_BEGINS_RE = re.compile(
    rf"{_STARTED_RE.pattern}|{_ERRORS_RE.pattern}|[ \t]*{_LOADING_RE.pattern}[ \t\r]*"
    r"|Traceback \(most recent call last\):[ \t\r]*",
)

# What ends the text a section holds: a line opening another, or a line of
# statistics closing its run.
_HELD_UNTIL_RE = re.compile(f"{_SECTION_RE.pattern}|{_STATS_RE.pattern}")

# A line of pytest's own that a runner's text between two of its runs is
# none of: one opening a section, a line of statistics, or a run's opening.
_PIVOT_RE = re.compile(f"{_HELD_UNTIL_RE.pattern}|{_STARTED_RE.pattern}")

# What a section says failed where its title says nothing of a phase: the
# test it names, or -- untitled -- nothing.
_IN_TEST = ""

# The banner pytest prints right above a run's statistics where it stopped
# the run early -- collection interrupted, `-x` stopping, a keyboard's
# interrupt -- and that saying collection was interrupted, which no
# exception's message is.
_BANNER_RE = re.compile(r"[ \t]*!{3,} \S.* !{3,}[ \t\r]*")
_INTERRUPTED_RE = re.compile(r"[ \t]*!+ Interrupted: \d+ errors? during collection !+[ \t\r]*")

# What parts a node ID's path from its test and each class from what it
# holds, what opens its parameters, and what parts a class in a test's name.
_NODE_SEPARATOR = "::"
_OPENING_BRACKET = "["
_NAME_SEPARATOR = "."

# pytest's mark of a message it cut short.
_ELLIPSIS = "..."

# What pytest's message for an exception drops that Python's own traceback
# keeps: a rewritten assertion's name. And what it gives for an exception
# group holding one exception: that exception's repr and the group's name,
# where the traceback shows the group holding one.
_ASSERTION = "AssertionError: "
_SINGLE_RE = re.compile(r".+ \[single exception in (?P<group>[\w.]+)\]")
_HOLDING_ONE = "(1 sub-exception)"

_UNPHASED = ("", "")

# Where in the output a line stands: under the failures heading, outside any
# titled section, where `--tb=line` prints each failure's line traceback; in
# the short summary below its heading; in a section a title opens; or
# elsewhere, outside any section -- by the heading or title opening the region.
_TRACED = "traced"
_SUMMARISED = "summarised"
_SECTIONED = "sectioned"
_ELSEWHERE = ""
_HEADED = MappingProxyType({_FAILURES: _TRACED, _SUMMARY: _SUMMARISED})

# How far in a marked line stands where none stands above: any line traceback
# stands at that margin or nearer.
_UNMARGINED = sys.maxsize

# The regions a section's text stands in: a titled section, and the failures
# heading's line tracebacks.
_HELD = frozenset((_SECTIONED, _TRACED))


@dataclass(frozen=True)
class _Where:
    """Where a line of the output stands: its region, and whether in what pytest captured below a rule.

    `nested` counts the runs a test printed that the line stands in, each
    captured in the one around it, which `nests` says may be read, and `above`
    is the line above, as walked, with the newline ending it -- a blank one
    above the first; `shown` is the exception the last marked
    line, traceback in Python's own form, or strict XPASS's report outside
    anything captured above it shows, "" once a line traceback giving it
    closes that failure, and `rail` the margin that form's exception is
    awaited at, None where none is; `run` counts the session headings at or
    above the line outside anything captured, and `summaries` the short
    summary headings; `closed` says a line of statistics closed the run above
    the line, no section or heading opening since; `width` is that of the last
    heading pytest printed, 0 before any; `heading` that heading's title, ""
    for none -- the line stands as captured below one reporting what did not
    fail, or a warning; `margin` how far in the last marked line outside
    anything captured below that heading or title stands, past every line for
    none; `native` says the last traceback there, chaining none below it, is
    in Python's own form and no group's, so its exception's message may run on
    in lines of any shape; and `bare` holds the runs pytest 8 printed the
    failures of, each line traceback alone (`_Walk.bare`).
    """

    region: str = _ELSEWHERE
    captured: bool = False
    nested: int = 0
    shown: str = ""
    run: int = 0
    summaries: int = 0
    nests: bool = True
    closed: bool = False
    width: int = 0
    heading: str = ""
    margin: int = _UNMARGINED
    rail: str | None = None
    native: bool = False
    above: str = "\n"
    bare: frozenset[int] = frozenset()

    def stands(self, region: str) -> bool:
        """Whether the line stands in `region`, outside anything captured."""
        return self.region == region and not self.captured

    def reports(self, line: str, last: Mapping[int, int]) -> bool:
        """Whether `line`, standing here, may report a failure of its run, `last` counting each run's summary headings.

        It stands in its run's last short summary -- pytest prints a run's
        short summary last, so a summary heading above another in one run is
        one a test printed -- or, where the output holds no summary heading
        (`last` empty), quoting the summary lines alone, outside anything
        captured, as a section quoted above them is not, and below no heading
        and no run's opening: below those pytest prints summary lines under
        their heading alone, and a run printed with `-rN` none, so a line of
        their shape there is a traceback's. Or it says pytest
        refused the run before running any test: pytest prints that error
        outside any section, a run it refused having none, nor a summary, so
        a line of its shape in a section or in anything captured is a test's
        or its traceback's, however little else the output holds.
        """
        refused = _summary.SummaryLine.refused(line) is not None
        summarised = self.stands(_SUMMARISED) and last[self.run] == self.summaries
        bare = not (self.run or self.width)
        quoted = bare and not (last or self.captured or refused)
        return summarised or quoted or (refused and self.stands(_ELSEWHERE))

    def below(self, line: str) -> _Where:
        """Where `line`, the line below the one this says, stands, read with this line above it (`_below`)."""
        return replace(self._below(line), above=f"{line}\n")

    def _below(self, line: str) -> _Where:
        """Where `line`, the line below the one this says, stands, all but the line above it.

        A heading opens a region, and a title the region of its section,
        closing the heading's; a rule opens what pytest captured, and the next
        line opening a section closes that -- as does the line traceback
        `--tb=line` prints last for a failure, below anything it captured,
        giving the exception its marked lines, or a strict XPASS's report,
        showed, at their margin -- one of its shape set out further is the
        capture's own -- and that failure shows nothing more. A run's opening
        in what was captured opens a run a test printed -- inside one, a run
        it captured in turn, each closed by its own line of statistics alone;
        outside it, a run of pytest's own, which its line of statistics closes
        -- a heading or not -- ending its short summary, and anything captured,
        too: a line of statistics that closes nothing is walked as none
        (`_Walk`).
        """
        if self.nested:
            deeper = self.nests and _OPENS_RE.fullmatch(self.above + line) is not None
            closes = _STATS_RE.fullmatch(line) is not None
            return replace(self, nested=self.nested + deeper - closes)
        opened = self._opened(line)
        if opened is not None:
            return opened
        lined = _LINE_TRACEBACK_RE.fullmatch(line)
        crashed = lined is not None and len(lined["margin"]) <= self.margin
        if crashed and Section.says(self.shown, lined["raised"]):
            return replace(self, captured=False, shown="")
        return self if self.captured else self._shown(line)

    def _shown(self, line: str) -> _Where:
        """Where `line`, outside anything captured, stands, for the exception it shows.

        A marked line shows what it says, at its margin; a traceback in
        Python's own form -- an exception group's, in any mode -- the first
        line at its header's margin, or its rail's; a strict XPASS's report
        its mark and reason, save in a run pytest 8 printed (`bare`), where
        each mark is a line traceback of its own; and a line chaining another
        traceback leaves the one above it no longer the last.
        """
        marked = _MARKED_RE.fullmatch(line)
        header = _NATIVE_HEADER_RE.fullmatch(line)
        xpassed = None if self.run in self.bare else _XPASSED_RE.fullmatch(line)
        if marked is not None:
            return replace(
                self, shown=marked.group("error") or self.shown,
                margin=len(marked.group("margin")),
            )
        if header is not None:
            rail = header.group("rail").replace(_GROUP_HEADER_RAIL, _GROUP_RAIL)
            return replace(self, rail=rail, native=not rail.strip())
        if _CHAINED_RE.fullmatch(line):
            return replace(self, native=False)
        said = xpassed["report"] if xpassed else Section.past(line, self.rail)
        if not said[:1].strip():
            return self
        return replace(self, shown=said.rstrip(), rail=None)

    def _opened(self, line: str) -> _Where | None:
        """Where `line` stands where it opens or closes a run, or opens a section; None where it does none of those.

        A run's opening in what was captured opens a run a test printed, where
        such a run may be read -- as does a heading right below a `-q -s` run's
        progress letters there, which carry no percentage to open it by -- and
        outside it stands first in its own run; a line opening a section opens
        what `_opening` says, and in what was
        captured only one as wide as the last heading pytest printed does
        anything, one narrower being a test's; and a line of statistics closes
        its run, that run's short summary and anything captured with it --
        `-q` prints them right below a test's captured output.
        """
        started = _STARTED_RE.fullmatch(line) is not None
        opens = _OPENS_RE.fullmatch(self.above + line) is not None
        if opens and self.captured and self.nests:
            return replace(self, nested=1)
        if started and not self.captured:
            return _Where(
                run=self.run + 1, summaries=self.summaries,
                nests=self.nests, width=self.width, bare=self.bare,
            )
        section = _SECTION_RE.fullmatch(line)
        width = self.width if section is None else len(section.group("line"))
        if self.captured and width < self.width:
            return None
        if _STATS_RE.fullmatch(line):
            return replace(self, region=_ELSEWHERE, captured=False, closed=True)
        return None if section is None else self._opening(section)

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
        region = _HEADED.get(named, _ELSEWHERE) if opened.group("equals") else _SECTIONED
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
            bare=self.bare,
        )


@dataclass(frozen=True)
class _Walk:
    """A walk over the output for where each of its lines stands (`_Where`), walked again over what it read wrong.

    `texts` are the numbers of the lines of statistics read as a section's or
    a capture's own text, closing nothing (`_closes`), walked as blank; from
    line `unnested` on, no run's opening in what was captured opens a run a
    test printed; and `bare` are the runs pytest 8 printed the failures of
    with `--tb=line`, a line traceback of a crash standing right below the
    failures heading or another line traceback, where each strict XPASS's
    mark is its own, none repeating its report.
    """

    lines: Sequence[str]
    texts: frozenset[int]
    unnested: int
    bare: frozenset[int] = frozenset()

    @classmethod
    def of(cls, lines: Sequence[str]) -> _Walk:
        """The walk over `lines` that reads none wrong, each walked again until it does not (`settled`)."""
        walk = cls(lines, frozenset(), len(lines))
        settled = walk.settled()
        while settled is not None:
            walk, settled = settled, settled.settled()
        return walk

    @cached_property
    def read(self) -> list[str]:
        """The lines as walked: each of `texts` blank."""
        blank = dict.fromkeys(self.texts, "")
        return [blank.get(number, line) for number, line in enumerate(self.lines)]

    @cached_property
    def wheres(self) -> tuple[_Where, ...]:
        """Where each line walked stands, the first of them above every line."""
        nesting = self.read[:self.unnested]
        unnesting = self.read[self.unnested:]
        head = tuple(accumulate(
            nesting, _Where.below, initial=_Where(bare=self.bare),
        ))
        unnested = replace(head[-1], nests=False)
        tail = tuple(accumulate(unnesting, _Where.below, initial=unnested))
        return head + tail[1:]

    def settled(self) -> _Walk | None:
        """The walk reading what this one read wrong as it is; None where this one read nothing wrong.

        A line of statistics this walk reads closing a run where it closes
        none is read as text (`_closes`); and a run a test printed that no line
        of statistics closes but the output's last -- the run's own -- or none,
        which the test cut short, is read as no run from its opening on, lest
        that hide the run's own summary, every run the test printed above it
        still read as one; and each run pytest 8 printed is read as such
        (`bare`). Each of those only grows, so the walks settle.
        """
        texts = self.texts.union(
            filterfalse(self._closes, compress(count(), map(_STATS_RE.fullmatch, self.read))),
        )
        unnested = self._unnested()
        bare = self.bare.union(
            where.run for line, where in zip(self.read, self.wheres)
            if where.stands(_TRACED) and _CRASHED_RE.fullmatch(line) and _BARED_RE.fullmatch(where.above)
        )
        if texts == self.texts and unnested == self.unnested and bare == self.bare:
            return None
        return replace(self, texts=texts, unnested=unnested, bare=bare)

    def traced(self, number: int) -> str | None:
        """The exception the line traceback `--tb=line` printed on line `number` gives; None for none.

        pytest prints one under the failures heading, outside any titled
        section and anything captured, at the margin of the failure's marked
        lines above it; a line of its shape set out further is their
        explanation's, as an assertion's diff may hold one. A strict XPASS's
        is its mark and reason where its report did not print them above it:
        pytest 9 prints that report first, read as its section in the line's
        stead, and pytest 8 the line alone, in a run each mark of which is a
        failure's own (`bare`).
        """
        before, where = self.wheres[number:number + 2]
        lined = _LINE_TRACEBACK_RE.fullmatch(self.read[number])
        if lined is None or not where.stands(_TRACED):
            return None
        raised = lined["raised"]
        repeated = raised.startswith(_XPASS_MARK) and Section.says(before.shown, raised)
        return None if repeated or len(lined["margin"]) > where.margin else raised

    def _closes(self, number: int) -> bool:
        """Whether line `number`, of statistics, closes its run.

        It does wherever it stands outside a section's text and anything
        captured, a run a test printed closing on its own statistics alone
        (`_Where`). Inside, pytest prints nothing of a run below its statistics
        -- `-q` prints them right below a section's text, or what it captured,
        where a run prints no summary -- but a test may print a line of their
        shape there, or raise an exception saying it, so what stands below
        them says whether they close their run (`_closing`) -- save where
        pytest's banner of a run it stopped early stands right above them, as
        it does above its own alone: a run whose collection was interrupted,
        say, below which the next run may open on its summary's heading
        whatever its traceback's form.
        """
        above = self.wheres[number]
        if above.nested or not (above.captured or above.region in _HELD):
            return True
        if number and _BANNER_RE.fullmatch(self.read[number - 1]):
            return True
        return _closing(self.read[number + 1:], above)

    def _unnested(self) -> int:
        """The line from which no run's opening in what was captured opens a run a test printed.

        It is the opening of the last run a test printed, where no line of
        statistics but the output's last closes it, and `unnested` where that
        stands below or every run a test printed closes above the output's
        last line of statistics.
        """
        stats = list(compress(count(), map(_STATS_RE.fullmatch, self.read)))
        nested = [where.nested for where in self.wheres]
        last = stats[-1] if stats else -1
        if not (nested[last] or nested[-1]):
            return self.unnested
        # The opening is the last line below which a run a test printed is
        # read, the line above it read in none.
        opened = map(gt, nested[1:], nested)
        return min(self.unnested, max(compress(count(), opened)))


@dataclass(frozen=True)
class Section:
    """One section pytest printed: its title, the exception it shows, "" for none, and the run it stands in."""

    title: str
    raised: str
    run: int

    @classmethod
    def read(cls, title: str, lines: Iterable[str], run: int) -> Section:
        """The section of `run` titled `title` above `lines`, its exception the one its last traceback shows.

        It holds the lines up to the next that opens a section, or that closes
        the run with its statistics, as a run printing no summary does right
        below its last section, a conftest it could not load said below that.
        Its last traceback runs below the last line saying another exception
        followed, or from the section's top: one in Python's own form ends on
        its exception (`_native`), its message running on below in lines of
        any shape, marked ones too; any other marks it (`_marked`).
        """
        held = list(takewhile(lambda line: not _HELD_UNTIL_RE.fullmatch(line), lines))
        chained = compress(count(1), map(_CHAINED_RE.fullmatch, held))
        last = held[max(chained, default=0):]
        native = any(map(_NATIVE_HEADER_RE.fullmatch, last))
        raised = cls._native(last) if native else cls._marked(last)
        return cls(title, raised, run)

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

    @classmethod
    def says(cls, raised: str, shown: str) -> bool:
        """Whether the error `shown`, as pytest gives it on a summary line or a line traceback, opens on `raised`.

        `raised` is the exception a traceback shows. pytest gives a rewritten
        assertion without the `AssertionError: ` Python's own form keeps,
        and an exception group holding one exception by that exception's repr
        and the group's name -- which a group's own traceback shows as the
        group, and a `--tb=line` section holds as given.
        """
        single = _SINGLE_RE.fullmatch(shown)
        named = raised.startswith(shown) or raised.removeprefix(_ASSERTION).startswith(shown)
        if named or single is None:
            return bool(shown) and named
        return raised.startswith(f"{single['group']}: ") and raised.endswith(_HOLDING_ONE)

    @classmethod
    def past(cls, line: str, margin: str | None) -> str:
        """What `line` says past `margin`; "" where no margin is open, or the line stands on another."""
        if margin is None or not line.startswith(margin):
            return ""
        return line[len(margin):]

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
            said = cls.past(line, margin)
            if said[:1].strip():
                raised = said.rstrip()
                margin = None
        return raised

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
        self._walk = _Walk.of(lines)
        self._wheres = self._walk.wheres[1:]
        unstarted = _unstarted(self._walk.read, self._wheres)
        self.sections = tuple(chain(unstarted, self._read()))
        self.titled = frozenset(
            (section.failed[1], section.run) for section in self.sections
        )
        # The lines pytest's short summary lines, or the error refusing a
        # run, may stand on, each with the run it reports on: in the last
        # short summary of their run, or -- in output holding no summary
        # heading, quoting the summary lines alone -- outside anything
        # captured and below no heading or run's opening, or saying pytest
        # refused their run before running any test (`_Where.reports`).
        last = {where.run: where.summaries for where in self._wheres if where.region == _SUMMARISED}
        self.summary = [
            (line, where.run)
            for line, where in zip(lines, self._wheres, strict=True)
            if where.reports(line, last)
        ]
        self._interrupted = frozenset(
            run for line, run in self.summary if _INTERRUPTED_RE.fullmatch(line)
        )
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
            and Section.says(section.raised, shown)
            for section in self.sections
        )
        untaken = (number for number in compress(count(), shows) if number not in self._taken)
        return next(untaken, None) if name else None

    def take(self, titles: Collection[str], error: str, run: int) -> Section | None:
        """The section titled one of `titles` a summary line of `run` giving `error` reports; None for none.

        It is the first such section of the line's run no line took before,
        the one whose exception `error` opens -- pytest's ellipsis aside --
        where one does, and is taken. One `--tb=line` printed untitled names
        no test, so it goes to a line giving an error only where that error
        opens on its exception: a failure whose report is text alone -- a
        plugin's, say -- gets a line of no shape read here in its line
        traceback's stead, so its line takes none rather than the next
        failure's.
        """
        shown = error.removesuffix(_ELLIPSIS)
        untaken = [
            index for index, section in enumerate(self.sections)
            if section.title in titles and section.run == run and index not in self._taken
            and (section.title or not shown or Section.says(section.raised, shown))
        ]
        opened = [
            index for index in untaken
            if Section.says(self.sections[index].raised, shown)
        ]
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
                    titled["title"], self._walk.read[number + 1:], where.run,
                )
            raised = self._walk.traced(number)
            if raised is not None:
                yield Section(_UNTITLED, raised, where.run)


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


def _unstarted(lines: Sequence[str], wheres: Sequence[_Where]) -> Iterator[Section]:
    """Each failure pytest printed before it ran any test, as a section of its own.

    A conftest it could not load is titled by the line saying so, its
    exception the one the traceback below it shows; a plugin it could not
    import by the last line of its traceback, which is its exception too.
    pytest prints either outside every section, summary, and capture, so a
    line of their shape anywhere else -- a test's traceback raising such an
    exception, or what pytest captured from a test -- is none.
    """
    for number, where in enumerate(wheres):
        line = lines[number].strip(_BLANKS) if where.stands(_ELSEWHERE) else ""
        loading = _LOADING_RE.fullmatch(line)
        importing = _IMPORTING_RE.fullmatch(line)
        if loading is not None:
            yield Section.read(line, lines[number + 1:], where.run)
        if importing is not None:
            yield Section(line, line, where.run)


def _closing(below: Sequence[str], where: _Where) -> bool:
    """Whether the lines `below` a line of statistics, standing as `where` says, show it closes its run.

    They do where nothing of pytest's own shapes (`_PIVOT_RE`) stands below
    it; where the next line past blank ones is a `-q -s` run's progress
    letters, carrying no percentage, or one pytest prints beginning a run
    alone -- its opening, the errors heading a `-q` run failing collection
    alone opens on, a conftest or a plugin it could not load -- or the error
    refusing it; or where the first line of pytest's shapes below it is a
    heading, as a `-q --tb=no` run reporting no progress opens on: right
    below a blank line, since pytest ends its progress line before a run's
    terminal summary -- a blank one where it printed no progress -- and
    prints that summary's headings right below a section's text or what it
    captured; or right below the statistics, in a section's text below no
    traceback in Python's own form but a group's (`_Where.native`), since
    only such a traceback's message runs on there in lines of their shape, a
    marked traceback's in marked lines. A runner may print text between two
    of pytest's runs, and a test a line of their shape and text above a run
    it printed, so where that first line is a run's opening past text, the
    statistics close their run where nothing of a run around the one it opens
    follows that one's statistics -- read so in turn, as though captured.
    """
    texts = list(takewhile(lambda line: not _PIVOT_RE.fullmatch(line), below))
    following = next((line for line in below if line.strip(_BLANKS)), "")
    if len(texts) == len(below) or _LETTERED_RE.fullmatch(following):
        return True
    if _summary.SummaryLine.refused(following) is not None or _BEGINS_RE.fullmatch(following):
        return True
    pivot = below[len(texts)]
    if _STARTED_RE.fullmatch(pivot):
        # Texts hold no statistics, so the first line of them below closes the
        # run that opening starts, a test's or not.
        ending = list(dropwhile(lambda line: not _STATS_RE.fullmatch(line), below))
        return _closing(ending[1:], replace(where, captured=True))
    spaced = bool(texts) and not texts[-1].strip(_BLANKS)
    return _HEADING_RE.fullmatch(pivot) is not None and (
        spaced or not (texts or where.captured or where.native)
    )
