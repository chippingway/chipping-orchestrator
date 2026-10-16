# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What leads each check a reviewer's findings show failing: the failures it records, by name.

`review_findings` keeps each check a declaration does not show passing as the
diagnostic a developer acts on, and leads it with the lines written here
(`lead`), so the developer reads what failed before the command that ran it
and how it ended, which follow as supporting details over the output quoted.

A check's output names its failures where pytest's short summary reports them
-- below the last summary heading of its run, where the output holds one, and
never in what pytest captured from a test, which may print lines of the
summary's shape or a whole run of pytest's (`review_findings_pytest`), each
line read as `review_findings_summary` reads it: a `FAILED` line names a test
by its exact node ID, parameters included and a file path holding blanks or
brackets, or a test name holding blanks, too, a `SUBFAILED` line a subtest by
its test's node ID and pytest's description of it, and an `ERROR` line a node
by its ID, or a path. A path names a collection that failed before any test in
it ran -- the check that failed, not a test -- whatever file it is and whether
it holds blanks or brackets, though words naming no Python file are one only
where pytest says so. A node ID names the setup or teardown of a test where a
section pytest printed says that failed -- where both did, the one whose
section raised the error the line gives; a collection where a section of its
run says pytest failed collecting the node or its path, or its run says
collection was interrupted, since a class pytest could not collect is reported
by its ID; and, nothing saying which, an error outside any test body, in one
of the three. An ID is the longest an entry of the findings names whole, or
pytest titled a section by; where nothing names one, it ends where the line's
message may first begin, so the message is never cut short, and where a later
split could end it too the lead says where the ID ends is unavailable. Each
failure leads with its name and the error the line gives. Where the line gives
none -- pytest drops it from a line too long for the terminal -- the exception
the section pytest printed for it shows gives it, each section going to one
summary line, so tests of two modules sharing a name each take their own
(`review_findings_pytest`); or else the error of the reviewer's entry naming
it. Where none is found the lead says so. No name is ever made up: a check
pytest's summary names nothing in is led by the failure entries
(`review_findings_entries`) the reviewer wrote for it in the findings, each
named as the reviewer named it, or by a line saying nothing names it. An entry
is a check's where the check's output shows the entry's error -- never because
the two name one command, since one stdin command, such as `.venv/bin/python
-`, may run several scenarios, each a check of its own. A lead says too where
the check quoted no output to show an error by, and -- whatever names its
failures -- where its command reads its code from stdin -- a `-` argument,
split as a shell splits it, that no argument before it gave a program inline,
by module, or as a script and no entry it backs gives the snippet it read, as
a code block holding code below its `Reproduce:` line: such a command
reproduces nothing alone, however an entry names it. A lead names every
failure pytest's summary reports, each with its error, as a lead by entries
names every entry the output backs.

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
`Failure:`, `Error:`, `Reproduce:`, `Unavailable:` -- and never on a
declaration keyword, so
what is shown still declares nothing; the names and errors it takes from
output stand in code spans their own backticks cannot close, so Markdown
shows them as the output spelled them. Reading entries decides nothing
either: what is shown is read from the text alone.
"""
from __future__ import annotations

import re
import shlex
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import partial
from itertools import chain

from orchestrator.workflow.engine import (
    review_findings_entries as _entries,
    review_findings_fences as _markdown,
    review_findings_pytest as _pytest,
    review_findings_summary as _summary,
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
_UNAVAILABLE = "Unavailable"

# What separates a node ID's path from the test it names. An ID without it
# names no test: pytest's summary reports such an ID only for a path it failed
# to collect, so where nothing pytest printed says it failed collecting it,
# text that reads as no path is no failure of pytest's -- a word holding no
# `/` and not naming a `.py` file, or words, as an `ERROR` line of a check's
# own may hold, not naming one either.
_NODE_SEPARATOR = "::"
_PATH_RE = re.compile(r"\S*/\S*|.*\.py")

# The title a failure `--tb=line` printed stands under: none.
_UNTITLED = ""

# The bare fence the layout before leads quoted a check's output in, below its
# sentence (`review_findings_entries.CHECK_SENTENCE_RE`), which closes on a
# period where the check quoted no output.
_BARE_FENCE_RE = re.compile(f"{_BACKTICK}{{3,}}")
_NO_OUTPUT_CLOSE = "."

# The argument a command reads the code it runs from stdin by, and one giving
# the program before it otherwise: inline, by module, or as a script.
_STDIN = "-"
_PROGRAM_RE = re.compile(r"-[cme].*|--(?:command|eval)(?:=.*)?|.*\.py")

_UNNAMED = f"{_NAME}: not named; no test ID or scenario name was recorded for this check"

_NO_OUTPUT = f"{_ERROR}: not recorded; the check quoted no output"

_UNSTATED = f"{_ERROR}: not on pytest's summary line; see the output below"

_UNSURE = (
    f"{_UNAVAILABLE}: where the test ID ends; pytest's summary line could part it from its message at a later"
    " dash too, the ID running on into the error shown"
)

_UNREPRODUCED = f"{_REPRODUCTION}: not recorded; {{command}} reads its code from stdin, and no snippet was given"

_UNCOLLECTED = "collection of {path}, before any test in it ran"

_ERRED = "{node}, which errored outside any test body: in its collection, setup, or teardown"

_PHASE_FAILED = "{node}, whose {phase} failed"

_SUBTEST = "{node}, subtest {subtest}"

_Entries = Sequence[_entries.FailureEntry]

_Pytest = _pytest.PytestOutput

_Summary = _summary.SummaryLine

# What a summary line takes where no section is left for it: nothing raised.
_UNTAKEN = _pytest.Section(_UNTITLED, "", -1)

# A lead, by the number of the line it goes above.
_Lead = tuple[int, tuple[str, ...]]


def lead(command: str, output: str, entries: _Entries) -> tuple[str, ...]:
    """The lines leading the failing check that ran `command` and quoted `output`, given the findings' `entries`.

    The failures pytest's summary reports lead it, else the entries it backs,
    else a line saying nothing names it; and either way a check whose command
    reads stdin says where no entry it backs gives the snippet it read.
    """
    backed = [entry for entry in entries if entry.backs(output)]
    reported = tuple(dict.fromkeys(_Reported.of(output, entries)))
    named = dict.fromkeys(entry.name for entry in backed if entry.name)
    said = list(_Reported.leading(reported))
    said = said or [f"{_NAME}: {name}" for name in named] or [_UNNAMED]
    if not output:
        said.append(_NO_OUTPUT)
    snippet = any(entry.snippet for entry in backed)
    if not snippet and _reads_stdin(command):
        said.append(_UNREPRODUCED.format(command=span(command)))
    return tuple(said)


def said(text: str, entries: _Entries) -> str:
    """The reviewer's `text`, what each entry leaves out said already, as shown: each check left unled, led.

    `entries` are those of the findings `text` stands among, read before
    anything is said of them (`review_findings_entries.FailureEntry.annotated`
    says it).
    """
    return _Unled(text.split("\n")).led(entries)


def _reads_stdin(command: str) -> bool:
    """Whether `command` reads the code it runs from stdin: a `-` argument no earlier one gave the program before.

    Its arguments are split as a shell splits them, so a dash quoted inside one
    is no argument -- or on blanks where its quoting does not close. A program
    given inline or by module (`-c`, `-m`, `-e`), or as a script, makes a `-`
    after it the program's own argument.
    """
    try:
        arguments = shlex.split(command)
    except ValueError:
        arguments = command.split()
    if _STDIN not in arguments:
        return False
    given = arguments[:arguments.index(_STDIN)]
    return not any(map(_PROGRAM_RE.fullmatch, given))


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
    """A failure pytest's short summary reports in a check's output.

    `name` is how a lead names it, `error` its error or "", and `unsure` says
    where its test ID ends is unavailable (`review_findings_summary`).
    """

    name: str
    error: str
    unsure: bool = False

    @classmethod
    def of(cls, output: str, entries: _Entries) -> Iterator[_Reported]:
        """Each failure a summary line of `output` reports, read beside the findings' `entries`."""
        read = _pytest.PytestOutput(output.split("\n"))
        for line, run in read.summary:
            reported = cls._summarised(line, read, entries, run)
            if reported is not None:
                yield reported

    @classmethod
    def leading(cls, reported: Sequence[_Reported]) -> tuple[str, ...]:
        """The lines naming each of `reported` and its error."""
        said: list[str] = []
        for failure in reported:
            error = f"{_ERROR}: {span(failure.error)}" if failure.error else _UNSTATED
            said.extend((f"{_NAME}: {failure.name}", error))
            said.extend((_UNSURE,) if failure.unsure else ())
        return tuple(said)

    @classmethod
    def _named(cls, read: _Pytest, entries: _Entries, node: str) -> bool:
        """Whether pytest titled a section of `read` by `node`, or an entry of the findings names it whole."""
        return read.sectioned(node) or bool(_entries.FailureEntry.naming(entries, node))

    @classmethod
    def _summarised(cls, line: str, read: _Pytest, entries: _Entries, run: int) -> _Reported | None:
        """The failure `line` of `read` reports, if it is a summary line of pytest's; None where not.

        A failed test or subtest is named by its node ID (`_failed`), an error
        by what failed (`_erred`), each from the sections of the line's `run`
        alone.
        """
        summary = _Summary.read(line, partial(cls._named, read, entries))
        if summary is None:
            return None
        named = _entries.FailureEntry.error_naming(entries, summary.node)
        if summary.errored:
            return cls._erred(summary, named, read, run)
        return cls._failed(summary, named, read, run)

    @classmethod
    def _failed(cls, summary: _Summary, named: str, read: _Pytest, run: int) -> _Reported | None:
        """The test or subtest a summary line of `read` reports as `summary` says; None where its ID names no test.

        `named` is the error of the entry naming the failure. Where the line
        gives none -- pytest drops it from a line too long for the terminal
        -- the error is the exception the section pytest printed for the test,
        or for the subtest by its test's name and description, shows, else
        the entry's.
        """
        node = summary.node
        if _NODE_SEPARATOR not in node:
            return None
        titled = f"{read.name(node)} {summary.subtest}".rstrip()
        taken = read.take({titled, _UNTITLED}, summary.error, run)
        raised = (taken or _UNTAKEN).raised
        failed = span(node)
        if summary.subtest:
            failed = _SUBTEST.format(node=failed, subtest=span(summary.subtest))
        return cls(failed, summary.error or raised or named, summary.unsure)

    @classmethod
    def _erred(cls, summary: _Summary, named: str, read: _Pytest, run: int) -> _Reported | None:
        """The failure an `ERROR` summary line of `read` reports as `summary` says; None where it is not pytest's.

        `named` is the error of the entry naming the failure.

        A path names a collection -- one of any shape where pytest says it
        failed collecting it or that the line's `run` was interrupted
        collecting, as a doctest's text file, its path holding blanks or not.
        A node ID names the setup or teardown its section says failed with the
        line's error (`PytestOutput.phase`); or a collection, where pytest
        says it failed collecting the node or its path, or that the line's
        `run` says collection was interrupted; or else an error in one of the
        three, nothing saying which. A setup's,
        teardown's, or collection's error is the summary line's, else the
        exception the section pytest printed for it shows -- the line may be
        too long to carry one -- and either's, the entry naming the failure's
        where neither gives one.
        """
        node = summary.node
        phase, raised = read.phase(node, summary.error, run)
        if phase:
            failed = _PHASE_FAILED.format(node=span(node), phase=phase)
            return cls(failed, summary.error or raised or named, summary.unsure)
        collected = read.collection(node, summary.error, run)
        if collected is None and _NODE_SEPARATOR in node:
            failed = _ERRED.format(node=span(node))
            return cls(failed, summary.error or named, summary.unsure)
        if collected is None and not _PATH_RE.fullmatch(node):
            return None
        failed = _UNCOLLECTED.format(path=span(node))
        return cls(failed, summary.error or collected or named, summary.unsure)


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
