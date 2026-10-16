# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What leads each check a reviewer's findings show failing: the failures it records, by name.

`review_findings` keeps each check a declaration does not show passing as the
diagnostic a developer acts on, and leads it with the lines written here
(`lead`), so the developer reads what failed before the command that ran it
and how it ended, which follow as supporting details over the output quoted.

A check's output names its failures where pytest's short summary reports them:
a `FAILED` line names a test by its exact node ID, parameters included, and an
`ERROR` line a node by its ID, or a path. A path names a collection that
failed before any test in it ran -- the check that failed, not a test. A node
ID names the setup or teardown of a test where a section pytest printed says
that failed; a collection where a section says pytest failed collecting the
node or its path, or the run says collection was interrupted, since a class
pytest could not collect is reported by its ID; and, nothing saying which, an
error outside any test body, in one of the three. A parameter may hold the
very dash that parts an ID from its message, and even text of a message's
shape after it (`_Reported._end`), so the ID is the longest an entry of the
findings names whole, or pytest titled a section by; where nothing names one,
it ends on the last split leaving a message of the shape pytest gives -- a
rewritten assertion's `assert`, or the name of the exception, a colon after it
unless it says nothing more -- and where none does, on the first. Each failure
leads with its name and the error the line gives; for a collection error,
which pytest's summary may give none for, the last exception line of the
traceback pytest printed collecting it; or else the error of the reviewer's
entry naming it. Where none is found the lead says so. No name is
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
from itertools import chain, compress, islice, takewhile

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

# The title of a section pytest prints a traceback in, what opens a section,
# and the lines it marks as the exception. A failed test's section is titled
# by its name -- the node ID past its path, classes parted by dots -- one that
# errored in a fixture by that name after `ERROR at setup of` or `ERROR at
# teardown of`, and one it failed collecting by `ERROR collecting` and what it
# collected; a run collection stopped says it was interrupted.
_TITLE_RE = re.compile(r"[ \t]*_{3,} (?P<title>.+?) _{3,}[ \t\r]*")
_SECTION_RE = re.compile(r"[ \t]*(?:_{3,}|={3,})")
_EXCEPTION_RE = re.compile(r"[ \t]*E[ \t]+(?P<error>\S.*?)[ \t\r]*")
_PHASE_TITLE_RE = re.compile(r"ERROR at (?P<phase>setup|teardown) of (?P<name>.+)")
_COLLECTING_TITLE_RE = re.compile(r"ERROR collecting (?P<subject>.+)")
_COLLECTING = "ERROR collecting {subject}"
_INTERRUPTED_RE = re.compile(r"Interrupted: \d+ errors? during collection")
_NAME_SEPARATOR = "."

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

_ERRED = "{node}, which errored outside any test body: in its collection, setup, or teardown"

_PHASE_FAILED = "{node}, whose {phase} failed"

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
        """Each failure a summary line of `output` reports, read beside the findings' `entries`."""
        read = _Output(output.split("\n"), entries)
        for summary in filter(None, map(_SUMMARY_RE.fullmatch, read.lines)):
            reported = cls._summarised(summary, read)
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
    def _summarised(cls, summary: re.Match[str], read: _Output) -> _Reported | None:
        """The failure the summary line `summary` of `read` reports, if it is pytest's; None where not.

        A failed test is named by its node ID, its error the summary line's,
        or else that of the entry naming it.
        """
        reported = summary.group("reported")
        end = cls._end(reported, read)
        if end is None:
            return None
        node = reported[:end]
        error = reported[end:].removeprefix(_DELIMITER)
        named = _entries.FailureEntry.error_naming(read.entries, node)
        if summary.group("outcome") != _FAILED:
            return cls._erred(node, error, named, read)
        return cls(span(node), error or named) if _NODE_SEPARATOR in node else None

    @classmethod
    def _erred(cls, node: str, error: str, named: str, read: _Output) -> _Reported | None:
        """The failure an `ERROR` summary line of `read` reports of `node`; None where it is not pytest's.

        `error` is what follows the ID on the line, and `named` the error of
        the entry naming the failure.

        A path names a collection. A node ID names the setup or teardown its
        section says failed; or a collection, where pytest says it failed
        collecting the node or its path, or that collection was interrupted;
        or else an error in one of the three, nothing saying which. A
        collection's error is the summary line's, else the last exception
        line of the traceback pytest printed collecting it; and either's, the
        entry naming the failure's where neither gives one.
        """
        separated = _NODE_SEPARATOR in node
        phase = read.phase(node) if separated else ""
        if phase:
            failed = _PHASE_FAILED.format(node=span(node), phase=phase)
            return cls(failed, error or named)
        collected = read.collection(node) if separated else node
        if collected is None:
            return cls(_ERRED.format(node=span(node)), error or named)
        if not (separated or _PATH_RE.fullmatch(node)):
            return None
        quoted = error or read.traceback(collected) or named
        return cls(_UNCOLLECTED.format(path=span(node)), quoted)

    @classmethod
    def _end(cls, reported: str, read: _Output) -> int | None:
        """Where the node ID a summary line of `read` reports as `reported` ends; None where it holds none.

        A parameter may hold the very dash that parts a node ID from its
        message, and even text of a message's shape after it, so the ID is the
        longest an entry names whole, or pytest printed a section for. Where
        nothing names one, it ends on the last split leaving a message of the
        shape pytest gives, and where none does, on the first.
        """
        ends = cls._ends(reported)
        named = [end for end in ends if read.names(reported[:end])]
        messages = [reported[end:].removeprefix(_DELIMITER) for end in ends]
        shaped = list(compress(ends, map(_MESSAGE_RE.match, messages)))
        return next(chain(reversed(named), reversed(shaped), ends), None)

    @classmethod
    def _ends(cls, reported: str) -> list[int]:
        """Where in `reported` a node ID may end: its path's end, or each closing bracket of its parameters."""
        path = _NODE_PATH_RE.match(reported)
        if path is None:
            return []
        if reported.startswith(_OPENING_BRACKET, path.end()):
            return [found.end() for found in _PARAMETERS_END_RE.finditer(reported, path.end())]
        return [path.end()] if _NODE_END_RE.match(reported, path.end()) else []


class _Output:
    """A check's output read as pytest's, beside the findings' entries: what tells a summary line's failure apart.

    `lines` are the output's; `entries` the findings'. The titles of the
    sections pytest printed name the tests that failed or errored and what
    it failed collecting.
    """

    def __init__(self, lines: Sequence[str], entries: _Entries) -> None:
        self.lines = lines
        self.entries = entries
        self._titles = {title: number for number, title in self._titled(lines)}
        phased = filter(None, map(_PHASE_TITLE_RE.fullmatch, self._titles))
        self._phases = dict(found.group("name", "phase") for found in phased)
        self._sectioned = frozenset(self._titles).union(self._phases)
        collecting = map(_COLLECTING_TITLE_RE.fullmatch, self._titles)
        self._collected = frozenset(found.group("subject") for found in collecting if found)
        self._interrupted = any(map(_INTERRUPTED_RE.search, lines))

    def names(self, node: str) -> bool:
        """Whether an entry names `node` whole, or pytest printed a section for the test it names."""
        name = self._name(node)
        sectioned = bool(name) and name in self._sectioned
        return sectioned or bool(_entries.FailureEntry.naming(self.entries, node))

    def phase(self, node: str) -> str:
        """The phase of the test `node` names that pytest printed a section for as failing; "" for none."""
        return self._phases.get(self._name(node), "")

    def collection(self, node: str) -> str | None:
        """What pytest failed collecting for `node` -- itself, or the path holding it; None where nothing says.

        A run collection stopped failed collecting whatever its summary names.
        """
        path = node.partition(_NODE_SEPARATOR)[0]
        subjects = [subject for subject in (node, path) if subject in self._collected]
        return next(iter(subjects), path if self._interrupted else None)

    def traceback(self, subject: str) -> str:
        """The last exception line of the traceback pytest printed collecting `subject`; "" for none."""
        number = self._titles.get(_COLLECTING.format(subject=subject))
        if number is None:
            return ""
        below = self.lines[number + 1:]
        section = takewhile(lambda line: _SECTION_RE.match(line) is None, below)
        errors = [found.group("error") for found in map(_EXCEPTION_RE.fullmatch, section) if found]
        return errors[-1] if errors else ""

    @classmethod
    def _name(cls, node: str) -> str:
        """The name pytest titles the section of the test `node` names by: past its path, classes parted by dots."""
        return node.partition(_NODE_SEPARATOR)[2].replace(_NODE_SEPARATOR, _NAME_SEPARATOR)

    @classmethod
    def _titled(cls, lines: Sequence[str]) -> Iterator[tuple[int, str]]:
        """The title of each section `lines` open, by the number of the line opening it."""
        for number, title in enumerate(map(_TITLE_RE.fullmatch, lines)):
            if title is not None:
                yield number, title.group("title")


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
