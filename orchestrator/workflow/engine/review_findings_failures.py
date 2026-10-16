# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What leads each check a reviewer's findings show failing: the failures it records, by name.

`review_findings` keeps each check a declaration does not show passing as the
diagnostic a developer acts on, and leads it with the lines written here
(`lead`), so the developer reads what failed before the command that ran it
and how it ended, which follow as supporting details over the output quoted.

A check's output names its failures where pytest's short summary reports them:
a `FAILED` line names a test by its exact node ID, parameters included, and an
`ERROR` line either a test that errored outside its own body, or, with no test
in its ID, the path whose collection failed before any test in it ran -- the
check that failed, not a test. A parameter may hold the very dash and bracket
that part an ID from its message (`_SummaryLine`), so the ID ends where a
message of the shape pytest gives begins: a rewritten assertion's `assert`,
or the name of the exception, a colon after it unless it says nothing more.
Where no split leaves such a message, the ID ends at the first. Each failure
leads with its name and the error the line gives; for a collection error,
which pytest's summary gives none for, the last exception line of the
traceback pytest printed collecting that path; or else the error of the
reviewer's entry naming it. Where none is found the lead says so. No name is
ever made up: a check pytest's summary names nothing in is led by the failure
entries (`review_findings_entries`) the reviewer wrote for it in the findings,
each named as the reviewer named it, or by a line saying nothing names it. An
entry is a check's where the check's output shows the entry's error -- never
because the two name one command, since one stdin command, such as
`.venv/bin/python -`, may run several scenarios, each a check of its own. A
lead says too where the check quoted no output to show an error by, and where
its command reads its code from stdin and no entry it backs gives the snippet
it read, as a code block below its `Reproduce:` line: such a command
reproduces nothing alone, however an entry names it. A check naming more
failures than a lead lists leaves the rest to its output, which is quoted
whole below it.

The reviewer's own text is shown through here too (`said`): each entry with
what it leaves out said, and each check the concise layout before leads
showed (`_Unled`) led as a check read off a declaration is. That layout's
feedback, persisted or posted before leads, holds no declaration to read its
checks from again, so each is read off the paragraph it stands as, frozen as
that layout spelled it: a sentence naming its command -- a code span -- or
saying it named none, then how it ended, opening a paragraph at the margin
outside any code block, and closing it on a period where the check quoted no
output, or otherwise on a colon over a bare backtick fence holding the output,
one blank line between. The lead goes right above the sentence, so the
paragraph no longer opens on it and showing it again leads nothing twice.

Every line of a lead opens on a label of the reviewer's entry layout --
`Failure:`, `Error:`, `Reproduce:` -- and never on a declaration keyword, so
what is shown still declares nothing; the names and errors it takes from
output stand in code spans their own backticks cannot close, so Markdown
shows them as the output spelled them. Reading entries decides nothing
either: what is shown is read from the text alone.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import chain, dropwhile, islice, takewhile

from orchestrator.workflow.engine import (
    review_findings_entries as _entries,
    review_findings_fences as _markdown,
)

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

# A failure pytest's short summary reports: the outcome, then the node ID or
# the path whose collection failed, and the message after a dash where pytest
# gives one. A node ID's path runs to its first blank or bracket; parameters,
# which may hold blanks, dashes, and brackets, end on a closing bracket that
# the dash or the line's end follows. A message pytest gives opens on a
# rewritten assertion's `assert`, or on the name of the exception it reports,
# a colon after it unless it says nothing more.
_SUMMARY_RE = re.compile(r"[ \t]*(?P<outcome>FAILED|ERROR) (?P<reported>\S.*?)[ \t\r]*")
_NODE_PATH_RE = re.compile(r"[^\s\[]+")
_NODE_END_RE = re.compile(r"(?= - |\Z)")
_PARAMETERS_END_RE = re.compile(r"\](?= - |\Z)")
_OPENING_BRACKET = "["
_DELIMITER = " - "
_MESSAGE_RE = re.compile(r"assert\b|[A-Za-z_][\w.]*(?::|\Z)")

_FAILED = "FAILED"

# What separates a node ID's path from the test it names. An ID without it
# names no test: pytest's summary reports such an ID only for a path it failed
# to collect, so a word that reads as no path is no failure of pytest's.
_NODE_SEPARATOR = "::"
_PATH_RE = re.compile(r".*(?:/.*|\.py)")

# The header of the section pytest prints the traceback of an error collecting
# `path` in, what opens the section after it, and the lines it marks as the
# exception.
_COLLECTING = r"[ \t]*_{{3,}} ERROR collecting {path} _{{3,}}[ \t\r]*"
_SECTION_RE = re.compile(r"[ \t]*(?:_{3,}|={3,})")
_EXCEPTION_RE = re.compile(r"[ \t]*E[ \t]+(?P<error>\S.*?)[ \t\r]*")

# The bare fence the layout before leads quoted a check's output in, below its
# sentence (`review_findings_entries.CHECK_SENTENCE_RE`), which closes on a
# period where the check quoted no output.
_BARE_FENCE_RE = re.compile(f"{_BACKTICK}{{3,}}")
_NO_OUTPUT_CLOSE = "."

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

_Entries = Sequence[_entries.FailureEntry]

# A lead, by the number of the line it goes above.
_Lead = tuple[int, tuple[str, ...]]


def lead(command: str, output: str, entries: _Entries) -> tuple[str, ...]:
    """The lines leading the failing check that ran `command` and quoted `output`, given the findings' `entries`."""
    reported = tuple(dict.fromkeys(_Reported.of(output, entries)))
    if reported:
        return _Reported.leading(reported)
    backed = [entry for entry in entries if entry.backs(output)]
    names = dict.fromkeys(entry.name for entry in backed if entry.name)
    said = [f"{_NAME}: {name}" for name in names] or [_UNNAMED]
    if not output:
        said.append(_NO_OUTPUT)
    snippet = any(entry.snippet for entry in backed)
    if not snippet and _STDIN in command.split():
        said.append(_UNREPRODUCED.format(command=span(command)))
    return tuple(said)


def said(text: str, entries: _Entries) -> str:
    """The reviewer's `text` as shown: what each entry leaves out said, and each check left unled, led.

    `entries` are those of the findings `text` stands among, read before
    anything is said of them.
    """
    annotated = _entries.FailureEntry.annotated(text)
    return _Unled(annotated.split("\n")).led(entries)


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
    def of(cls, output: str, entries: _Entries) -> Iterator[_Reported]:
        """Each failure a summary line of `output` reports, the findings' `entries` giving an error it lacks."""
        lines = output.split("\n")
        for summary in filter(None, map(_SummaryLine.read, lines)):
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
        cls, summary: _SummaryLine, lines: Sequence[str], entries: _Entries,
    ) -> _Reported | None:
        """The failure the `summary` line of the output `lines` reports, if it is pytest's; None where not.

        A test is named by its node ID; a path, by its collection. Where the
        summary line gives no error, a collection's traceback gives it, or
        else the entry naming the failure.
        """
        node = summary.node
        named = _entries.FailureEntry.error_naming(entries, node)
        if _NODE_SEPARATOR in node:
            erred = summary.outcome != _FAILED
            name = _ERRED.format(node=span(node)) if erred else span(node)
            return cls(name, summary.error or named)
        if summary.outcome == _FAILED or not _PATH_RE.fullmatch(node):
            return None
        error = summary.error or cls._collecting(lines, node) or named
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


@dataclass(frozen=True)
class _SummaryLine:
    """A line of pytest's short summary: its outcome, the node ID or path it reports, and the message after it or ""."""

    outcome: str
    node: str
    error: str

    @classmethod
    def read(cls, line: str) -> _SummaryLine | None:
        """`line` read as a summary line; None where it reads as none."""
        summary = _SUMMARY_RE.fullmatch(line)
        if summary is None:
            return None
        reported = summary.group("reported")
        end = cls._end(reported)
        if end is None:
            return None
        message = reported[end:].removeprefix(_DELIMITER)
        return cls(summary.group("outcome"), reported[:end], message)

    @classmethod
    def _end(cls, reported: str) -> int | None:
        """Where in `reported` its node ID ends; None where it holds none.

        A parameter may hold the very dash that parts a node ID from its
        message, so of the closing brackets that dash or the line's end
        follows, the ID ends on the first that leaves a message pytest would
        give -- and only where none does, on the first, since a message of
        another shape is likelier than a parameter holding that dash.
        """
        ends = cls._ends(reported)
        given = [end for end in ends if cls._gives(reported[end:])]
        return next(iter(given or ends), None)

    @classmethod
    def _ends(cls, reported: str) -> list[int]:
        """Where in `reported` a node ID may end: its path's end, or each closing bracket of its parameters."""
        path = _NODE_PATH_RE.match(reported)
        if path is None:
            return []
        if reported.startswith(_OPENING_BRACKET, path.end()):
            return [found.end() for found in _PARAMETERS_END_RE.finditer(reported, path.end())]
        return [path.end()] if _NODE_END_RE.match(reported, path.end()) else []

    @classmethod
    def _gives(cls, rest: str) -> bool:
        """Whether `rest`, what follows a node ID, opens a message pytest would give."""
        return _MESSAGE_RE.match(rest.removeprefix(_DELIMITER)) is not None


class _Unled:
    """Findings text read for the checks the concise layout before leads showed with nothing leading them."""

    def __init__(self, lines: Sequence[str]) -> None:
        self._lines = lines
        self._blocks = {block.start: block for block in _markdown.markdown_code_blocks(lines)}
        spans = (range(block.start, block.end) for block in self._blocks.values())
        self._held = frozenset(chain.from_iterable(spans))

    def led(self, entries: _Entries) -> str:
        """The text, each unled check's lead right above its sentence."""
        leads = dict(self._leads(entries))
        shown: list[str] = []
        for number, line in enumerate(self._lines):
            shown.extend(leads.get(number, ()))
            shown.append(line)
        return "\n".join(shown)

    def _leads(self, entries: _Entries) -> Iterator[_Lead]:
        """Each unled check's lead, by the number of the line its sentence stands on."""
        for number, line in enumerate(self._lines):
            sentence = self._sentence(number, line)
            if sentence is None:
                continue
            output = self._output(number, sentence.group("close"))
            if output is not None:
                yield number, lead(self._command(sentence), output, entries)

    def _sentence(self, number: int, line: str) -> re.Match[str] | None:
        """`line`, line `number`, read as an unled check's sentence: opening a paragraph, outside any code block."""
        opens = number not in self._held and self._blank(number - 1)
        return _entries.CHECK_SENTENCE_RE.fullmatch(line) if opens else None

    def _output(self, number: int, close: str) -> str | None:
        """The output the check whose sentence, closing on `close`, stands on line `number` quoted; None for no check.

        A period closes a paragraph of its own; a colon stands over a bare
        fence, a blank line between, that closes the paragraph too.
        """
        after = number + 1
        if close == _NO_OUTPUT_CLOSE:
            return "" if self._blank(after) else None
        block = self._blocks.get(after + 1)
        if block is None or not block.closing:
            return None
        fence = self._lines[block.start]
        closing = self._lines[block.end - 1]
        bare = closing == fence and _BARE_FENCE_RE.fullmatch(fence)
        if not (bare and self._blank(after) and self._blank(block.end)):
            return None
        return "\n".join(self._lines[block.held_start:block.held_end])

    def _blank(self, number: int) -> bool:
        """Whether line `number` is blank, or stands outside the text."""
        inside = 0 <= number < len(self._lines)
        return not inside or not self._lines[number].strip(_BLANKS)

    @classmethod
    def _command(cls, sentence: re.Match[str]) -> str:
        """The command `sentence` names, its code span's padding aside; "" where it names none."""
        command = sentence.group("command") or ""
        edges = command[:1] + command[-1:]
        padded = edges == "  " and bool(command.strip(" "))
        return command[1:-1] if padded else command
