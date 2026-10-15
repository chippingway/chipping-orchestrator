# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What leads each check a reviewer's findings show failing: the failures it records, by name.

`review_findings` keeps each check a declaration does not show passing as the
diagnostic a developer acts on, and leads it with the lines written here
(`lead`), so the developer reads what failed before the command that ran it
and how it ended, which follow as supporting details over the output quoted.

A check's output names its failures where pytest's short summary reports
them: a `FAILED` line names a test by its exact node ID, parameters included,
and an `ERROR` line either a test that errored outside its own body, or, with
no test in its ID, the path whose collection failed before any test in it ran
-- the check that failed, not a test. Each leads with that name and the error
the line gives; for a collection error, which pytest's summary gives none
for, the last exception line of the traceback pytest printed collecting that
path; or else the error of the reviewer's entry naming it. Where none is
found the lead says so. No name is ever made up: a check pytest's summary
names nothing in is led by the failure entries (`FailureEntry`) the reviewer
wrote for it in the findings, each named as the reviewer named it, or by a
line saying nothing names it. An entry is a check's where the check's output
shows the entry's error -- never because the two name one command, since one
stdin command, such as `.venv/bin/python -`, may run several scenarios, each
a check of its own. A lead says too where the check quoted no output to show
an error by, and where its command reads its code from stdin and no entry it
backs says how to reproduce it, since such a command reproduces nothing
alone. A check naming more failures than a lead lists leaves the rest to its
output, which is quoted whole below it.

Every line of a lead opens on a label of the reviewer's entry layout --
`Failure:`, `Error:`, `Reproduce:` -- and never on a declaration keyword, so
what is shown still declares nothing; the names and errors it takes from
output stand in code spans their own backticks cannot close, so Markdown
shows them as the output spelled them. Reading entries decides nothing
either: the findings are shown as written, and only the leads cite them.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from itertools import chain, dropwhile, islice, takewhile

from orchestrator.workflow.engine import review_findings_fences as _markdown

# What may make up a blank line, a CRLF line's carriage return included.
_BLANKS = " \t\r"

_BACKTICK = "`"

_BACKTICK_RUNS_RE = re.compile(f"{_BACKTICK}+")

# A code span needs a run its content never repeats.
_SPAN_RUN = 1

# The labels a lead's lines open on, those of the entry layout reviewers are
# taught (`review_evidence_prompts`).
_NAME = "Failure"
_ERROR = "Error"
_REPRODUCTION = "Reproduce"

# A line of the findings opening on one of those labels, bulleted or not, and
# such a line beside its number.
_LABEL_RE = re.compile(rf"[ \t]*(?:[-+*][ \t]+)?(?P<label>{_NAME}|{_ERROR}|{_REPRODUCTION}):(?P<given>.*)")
_Labeled = tuple[int, re.Match[str]]

# A failure pytest's short summary reports: the outcome, the node ID or the
# path whose collection failed, then the message after a dash where pytest
# gives one. A node ID's parameters may hold spaces and dashes, so the ID
# runs to the first closing bracket that a dash or the line's end follows.
_SUMMARY_RE = re.compile(
    r"[ \t]*(?P<outcome>FAILED|ERROR) (?P<node>[^\s\[]+(?:\[.*?\])?)(?: - (?P<error>.*?))?[ \t\r]*",
)

_FAILED = "FAILED"

# What separates a node ID's path from the test it names. An ID without it
# names no test: pytest's summary reports such an ID only for a path it failed
# to collect, so a word that reads as no path is no failure of pytest's.
_NODE_SEPARATOR = "::"
_PATH_RE = re.compile(r".*(?:/.*|\.py)")

# A node ID standing whole in an entry's name, as a word or a code span: a
# longer ID holding it, or one its path alone opens, is another failure's.
_WHOLE_NODE = r"(?<![^\s`(]){node}(?![^\s`),;])"

# The header of the section pytest prints the traceback of an error collecting
# `path` in, what opens the section after it, and the lines it marks as the
# exception.
_COLLECTING = r"[ \t]*_{{3,}} ERROR collecting {path} _{{3,}}[ \t\r]*"
_SECTION_RE = re.compile(r"[ \t]*(?:_{3,}|={3,})")
_EXCEPTION_RE = re.compile(r"[ \t]*E[ \t]+(?P<error>\S.*?)[ \t\r]*")

# The argument a command reads the code it runs from stdin by.
_STDIN = "-"

# As many failures as one lead names; the output quoted below it names the rest.
_NAMED_AT_MOST = 10

_UNNAMED = f"{_NAME}: not named; no test ID or scenario name was recorded for this check"

_NO_OUTPUT = f"{_ERROR}: not recorded; the check quoted no output"

_UNSTATED = f"{_ERROR}: not on pytest's summary line; see the output below"

_UNREPRODUCED = f"{_REPRODUCTION}: not recorded; {{command}} reads its code from stdin, and no snippet was given"

_UNCOLLECTED = "collection of {path}, before any test in it ran"

_ERRED = "{node}, which errored outside the test itself"

_MORE = f"{_NAME}: {{count}} more, named in the output below"


@dataclass(frozen=True)
class FailureEntry:
    """One failure the reviewer entered in the findings, under a line opening on `Failure:`.

    `name` is what that line names it; `error` what its `Error:` line gives,
    code-span backticks aside, or, where that line gives nothing, the last
    line of the code block below it; `reproduced` whether a `Reproduce:` line
    gives anything, on the line or as a code block below it.
    """

    name: str
    error: str = ""
    reproduced: bool = False

    @classmethod
    def read(cls, findings: str) -> tuple[FailureEntry, ...]:
        """Every entry `findings` hold, in order; a line a code block holds is the block's, never a label."""
        return tuple(_EntryReading(findings.split("\n")).entries())

    def backs(self, output: str) -> bool:
        """Whether the check that quoted `output` is this failure's: that output shows its error."""
        return bool(self.error) and self.error in output

    @classmethod
    def error_naming(cls, entries: Sequence[FailureEntry], node: str) -> str:
        """The error of the first of `entries` whose name holds `node`, an ID pytest reported, whole; "" for none."""
        whole = re.compile(_WHOLE_NODE.format(node=re.escape(node)))
        errors = (entry.error for entry in entries if whole.search(entry.name))
        return next(filter(None, errors), "")


def lead(command: str, output: str, entries: Sequence[FailureEntry]) -> tuple[str, ...]:
    """The lines leading the failing check that ran `command` and quoted `output`, given the findings' `entries`."""
    reported = tuple(dict.fromkeys(_Reported.of(output, entries)))
    if reported:
        return _Reported.leading(reported)
    backed = [entry for entry in entries if entry.backs(output)]
    names = dict.fromkeys(entry.name for entry in backed if entry.name)
    said = [f"{_NAME}: {name}" for name in names] or [_UNNAMED]
    if not output:
        said.append(_NO_OUTPUT)
    reproduced = any(entry.reproduced for entry in backed)
    if not reproduced and _STDIN in command.split():
        said.append(_UNREPRODUCED.format(command=span(command)))
    return tuple(said)


def span(text: str) -> str:
    """`text` as a code span its own backticks cannot close."""
    run = backticks(text, _SPAN_RUN)
    touching = text.startswith(_BACKTICK) or text.endswith(_BACKTICK)
    padding = " " if touching else ""
    return f"{run}{padding}{text}{padding}{run}"


def backticks(text: str, shortest: int) -> str:
    """A backtick run at least `shortest` long that is longer than any in `text`."""
    longest = max(map(len, _BACKTICK_RUNS_RE.findall(text)), default=0)
    return _BACKTICK * max(shortest, longest + 1)


@dataclass(frozen=True)
class _Reported:
    """A failure pytest's short summary reports in a check's output: how a lead names it, and its error or ""."""

    name: str
    error: str

    @classmethod
    def of(cls, output: str, entries: Sequence[FailureEntry]) -> Iterator[_Reported]:
        """Each failure a summary line of `output` reports, the findings' `entries` giving an error it lacks."""
        lines = output.split("\n")
        for summary in filter(None, map(_SUMMARY_RE.fullmatch, lines)):
            reported = cls._summarised(summary, lines, entries)
            if reported is not None:
                yield reported

    @classmethod
    def leading(cls, reported: Sequence[_Reported]) -> tuple[str, ...]:
        """The lines naming each of `reported`, as many as a lead names, then how many more the output names."""
        said = [line for failure in islice(reported, _NAMED_AT_MOST) for line in failure.lines()]
        rest = len(reported) - _NAMED_AT_MOST
        if rest > 0:
            said.append(_MORE.format(count=rest))
        return tuple(said)

    def lines(self) -> tuple[str, str]:
        """This failure's name, then its error."""
        error = f"{_ERROR}: {span(self.error)}" if self.error else _UNSTATED
        return f"{_NAME}: {self.name}", error

    @classmethod
    def _summarised(
        cls, summary: re.Match[str], lines: Sequence[str], entries: Sequence[FailureEntry],
    ) -> _Reported | None:
        """The failure the `summary` line of the output `lines` reports, if it is pytest's; None where not.

        A test is named by its node ID; a path, by its collection. Where the
        summary line gives no error, a collection's traceback gives it, or
        else the entry naming the failure.
        """
        node = summary.group("node")
        named = FailureEntry.error_naming(entries, node)
        if _NODE_SEPARATOR in node:
            erred = summary.group("outcome") != _FAILED
            name = _ERRED.format(node=span(node)) if erred else span(node)
            return cls(name, summary.group("error") or named)
        if summary.group("outcome") == _FAILED or not _PATH_RE.fullmatch(node):
            return None
        error = summary.group("error") or cls._collecting(lines, node) or named
        return cls(_UNCOLLECTED.format(path=span(node)), error)

    @classmethod
    def _collecting(cls, lines: Sequence[str], path: str) -> str:
        """The last exception line of the traceback pytest printed collecting `path` in `lines`; "" for none."""
        header = re.compile(_COLLECTING.format(path=re.escape(path)))
        opened = dropwhile(lambda line: header.fullmatch(line) is None, lines)
        if next(opened, None) is None:
            return ""
        section = takewhile(lambda line: _SECTION_RE.match(line) is None, opened)
        errors = [found.group("error") for found in map(_EXCEPTION_RE.fullmatch, section) if found]
        return errors[-1] if errors else ""


class _EntryReading:
    """The lines of the findings, read for the failure entries they hold."""

    def __init__(self, lines: Sequence[str]) -> None:
        self._lines = lines
        self._blocks = {block.start: block for block in _markdown.markdown_code_blocks(lines)}

    def entries(self) -> Iterator[FailureEntry]:
        """Each entry, from the line naming it to the next such line: the labels between are its own."""
        entry: FailureEntry | None = None
        for number, labeled in self._labeled():
            given = labeled.group("given").strip(_BLANKS)
            if labeled.group("label") == _NAME:
                if entry is not None:
                    yield entry
                entry = FailureEntry(given)
            elif entry is not None:
                entry = self._given(entry, labeled.group("label"), given, number)
        if entry is not None:
            yield entry

    def _labeled(self) -> Iterator[_Labeled]:
        """Each line no code block holds that opens on a label, by its number."""
        spans = (range(block.start, block.end) for block in self._blocks.values())
        held = frozenset(chain.from_iterable(spans))
        for number, line in enumerate(self._lines):
            labeled = None if number in held else _LABEL_RE.fullmatch(line)
            if labeled is not None:
                yield number, labeled

    def _given(self, entry: FailureEntry, label: str, given: str, number: int) -> FailureEntry:
        """`entry` once the line `number`, giving `given` under `label`, is read into it."""
        below = self._block_below(number)
        if label == _REPRODUCTION:
            return replace(entry, reproduced=bool(given) or below is not None)
        error = given.strip(_BACKTICK).strip(_BLANKS)
        if not error and below is not None:
            quoted = self._lines[below.held_start:below.held_end]
            held = [line.strip(_BLANKS) for line in quoted]
            error = next(filter(None, reversed(held)), "")
        return replace(entry, error=error)

    def _block_below(self, number: int) -> _markdown.CodeBlock | None:
        """The code block opening on the first non-blank line below line `number`, if one does."""
        below = number + 1
        for line in self._lines[below:]:
            if line.strip(_BLANKS):
                break
            below += 1
        return self._blocks.get(below)
