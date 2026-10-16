# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The failure entries a reviewer writes in its findings: read, and shown with what each leaves out said.

A reviewer is taught (`review_evidence_prompts`) to enter each failure its
findings rest on under the numbered item it supports, opening on a line
naming it -- `Failure:` -- with its own labels below, each on a line of its
own: `Error:`, `Expected:`, `Observed:`, `Reproduce:`, `Unavailable:`. An
entry runs from one `Failure:` line to the next, and a line a code block holds
is the block's, never a label, so a snippet quoting the layout enters nothing.
A label gives what follows it on its line, or, where that is blank, the code
block below it, only blank lines between: a multi-line error, or a snippet.

`review_findings_failures` reads each entry (`FailureEntry`) to lead the
checks its error shows in. `review_findings` shows the entries themselves as
written, save what one leaves out, which it says where the entry stands
(`FailureEntry.annotated`): a `Failure:` line naming nothing, and an error or
a reproduction an entry has no label for, or a label giving nothing. A label
giving nothing is said in place; one an entry has none of is added in the
entry's own indentation -- an error below its `Failure:` line, a
reproduction below its last label -- each past the lines its label goes on
over and the code block below it. What is said gives each label a value, so
showing an entry again says nothing more.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from itertools import chain
from types import MappingProxyType

from orchestrator.workflow.engine import review_findings_fences as _markdown

# What may make up a blank line, a CRLF line's carriage return included.
_BLANKS = " \t\r"

_BACKTICK = "`"

# The labels of the entry layout reviewers are taught, those read here first.
_NAME = "Failure"
_ERROR = "Error"
_REPRODUCTION = "Reproduce"

# A line of the findings opening on one of the layout's labels, bulleted or not.
_LABEL_RE = re.compile(
    rf"(?P<prefix>[ \t]*(?:[-+*][ \t]+)?)(?P<label>{_NAME}|{_ERROR}|Expected|Observed|{_REPRODUCTION}|Unavailable)"
    r":(?P<given>.*)",
)

# The sentence `review_findings` shows a check not shown passing as -- closing
# on a period where it quoted no output, otherwise on a colon over the output
# fenced below -- spelled as the layout before leads spelled it too. A run of
# label lines right above one is the lead the formatting wrote for that check,
# never an entry of the reviewer's.
CHECK_SENTENCE_RE = re.compile(
    r"(?:(?P<run>`+)(?P<command>.+?)(?P=run)(?!`)|A check naming no command)"
    r" (?:exited with status .*|reported (?:no exit status|a blank exit status|the exit statuses .*))(?P<close>[.:])",
)

# What a label line holds besides its number, in the order `_Label` keeps it.
_FIELDS = ("prefix", "label", "given")

# A node ID standing whole in an entry's name, as a word or a code span: a
# longer ID holding it, or one its path alone opens, is another failure's.
_WHOLE_NODE = r"(?<![^\s`(]){node}(?![^\s`),;])"

# What an entry leaving each out is said to give.
_UNNAMED = "not named; the entry gives no test ID or scenario name"
_MISSING = MappingProxyType({
    _ERROR: "not recorded; the entry gives no error",
    _REPRODUCTION: "not recorded; the entry gives no reproduction",
})

# Where a line said of an entry stands among those at its place: an error
# added before a reproduction added, and both before the line written there.
_ERROR_ADDED = 0
_REPRODUCTION_ADDED = 1
_WRITTEN = 2
_Place = tuple[int, int]
_Said = tuple[_Place, str]


@dataclass(frozen=True)
class FailureEntry:
    """One failure the reviewer entered in the findings, under a line opening on `Failure:`.

    `name` is what that line names it; `error` what its `Error:` line gives,
    code-span backticks aside, or, where that line gives nothing, the last
    line of the code block below it; `snippet` whether a code block stands
    below its `Reproduce:` line -- the code a stdin command would read, which
    the command alone, however it is written there, does not give.
    """

    name: str
    error: str = ""
    snippet: bool = False

    @classmethod
    def read(cls, findings: str) -> tuple[FailureEntry, ...]:
        """Every entry `findings` hold, in order."""
        return tuple(map(cls._of, _Lines(findings.split("\n")).entries))

    @classmethod
    def annotated(cls, findings: str) -> str:
        """`findings` with what each entry leaves out said where it stands, every other line as written."""
        return _Lines(findings.split("\n")).annotated()

    @classmethod
    def error_naming(cls, entries: Sequence[FailureEntry], node: str) -> str:
        """The error of the first of `entries` whose name holds `node`, an ID pytest reported, whole; "" for none."""
        whole = re.compile(_WHOLE_NODE.format(node=re.escape(node)))
        errors = (entry.error for entry in entries if whole.search(entry.name))
        return next(filter(None, errors), "")

    def backs(self, output: str) -> bool:
        """Whether the check that quoted `output` is this failure's: that output shows its error."""
        return bool(self.error) and self.error in output

    @classmethod
    def _of(cls, labels: Sequence[_Label]) -> FailureEntry:
        """The entry the label lines `labels` make up, a later label of a kind taking the place of an earlier."""
        errors = [label.error for label in labels if label.label == _ERROR]
        snippets = [label.quoted is not None for label in labels if label.label == _REPRODUCTION]
        error = errors[-1] if errors else ""
        snippet = snippets[-1] if snippets else False
        return cls(labels[0].stated, error, snippet)


@dataclass(frozen=True)
class _Label:
    """A line opening on a label, read where it stands among the findings.

    `number` is the line's; `prefix` what stands before the label; `given`
    what follows its colon; `quoted` the lines of the code block below it,
    only blank lines between, or None where none stands there; and `end` the
    number of the line after all it gives -- that block, or the lines it goes
    on over.
    """

    number: int
    prefix: str
    label: str
    given: str
    quoted: tuple[str, ...] | None
    end: int

    @property
    def stated(self) -> str:
        """What follows the colon, blanks aside."""
        return self.given.strip(_BLANKS)

    @property
    def gives(self) -> bool:
        """Whether the label gives anything: on its line, or as the code block below it."""
        return bool(self.stated) or self.quoted is not None

    @property
    def error(self) -> str:
        """What the label gives as an error: its line, code-span backticks aside, or its block's last line."""
        stated = self.stated.strip(_BACKTICK).strip(_BLANKS)
        held = [line.strip(_BLANKS) for line in self.quoted or ()]
        return stated or next(filter(None, reversed(held)), "")

    def said(self, text: str) -> str:
        """This label's line giving `text`."""
        return f"{self.prefix}{self.label}: {text}"


class _Lines:
    """The lines of the findings, and the failure entries they hold: each one's label lines, in order."""

    def __init__(self, lines: Sequence[str]) -> None:
        self._lines = lines
        self._blocks = {block.start: block for block in _markdown.markdown_code_blocks(lines)}
        spans = (range(block.start, block.end) for block in self._blocks.values())
        self._held = frozenset(chain.from_iterable(spans)) | self._led()
        self.entries = self._grouped()

    def annotated(self) -> str:
        """The lines, with what each entry leaves out said, joined."""
        shown = {(number, _WRITTEN): line for number, line in enumerate(self._lines)}
        shown.update(chain.from_iterable(map(_left_out, self.entries)))
        return "\n".join(shown[place] for place in sorted(shown))

    def _grouped(self) -> tuple[tuple[_Label, ...], ...]:
        """Each entry's label lines, from its `Failure:` line to the next; those above the first name no entry.

        A line a code block holds is the block's, and a lead's line the
        formatting's, never a label of an entry.
        """
        entries: list[list[_Label]] = []
        for number, line in enumerate(self._lines):
            labeled = None if number in self._held else _LABEL_RE.fullmatch(line)
            if labeled is None:
                continue
            label = self._label(number, labeled)
            if label.label == _NAME:
                entries.append([label])
            elif entries:
                entries[-1].append(label)
        return tuple(map(tuple, entries))

    def _led(self) -> frozenset[int]:
        """The number of each line of a lead: the run of label lines right above a check's sentence."""
        labeled = [_LABEL_RE.fullmatch(line) is not None for line in self._lines]
        led: set[int] = set()
        for number, line in enumerate(self._lines):
            if CHECK_SENTENCE_RE.fullmatch(line):
                above = number
                while above and labeled[above - 1]:
                    above -= 1
                led.update(range(above, number))
        return frozenset(led)

    def _label(self, number: int, labeled: re.Match[str]) -> _Label:
        """The label line `number`, as `labeled` reads it, with the block below it and where all it gives ends."""
        below = self._block_below(number)
        written = labeled.group(*_FIELDS)
        if below is None:
            return _Label(number, *written, None, self._end(number))
        held = self._lines[below.held_start:below.held_end]
        return _Label(number, *written, tuple(held), below.end)

    def _block_below(self, number: int) -> _markdown.CodeBlock | None:
        """The code block opening on the first non-blank line below line `number`, if one does."""
        below = number + 1
        for line in self._lines[below:]:
            if line.strip(_BLANKS):
                break
            below += 1
        return self._blocks.get(below)

    def _end(self, number: int) -> int:
        """The number of the line after the lines label line `number` goes on over: none blank, labeled, or code."""
        end = number + 1
        for line in self._lines[end:]:
            stops = not line.strip(_BLANKS) or end in self._blocks
            if stops or _LABEL_RE.fullmatch(line):
                break
            end += 1
        return end


def _left_out(labels: Sequence[_Label]) -> Iterator[_Said]:
    """Each line said of the entry the label lines `labels` make up, by its place: what it leaves out.

    A name its `Failure:` line gives nothing of is said in place; so is an
    error or a reproduction where no label of that kind gives anything. One
    with no such label is added in the entry's indentation, an error after all
    its `Failure:` line gives, a reproduction after all its last label gives.
    """
    named = labels[0]
    if not named.stated:
        yield (named.number, _WRITTEN), named.said(_UNNAMED)
    yield from _unstated(labels, _ERROR, named.end, _ERROR_ADDED)
    yield from _unstated(labels, _REPRODUCTION, labels[-1].end, _REPRODUCTION_ADDED)


def _unstated(labels: Sequence[_Label], kind: str, end: int, added: int) -> Iterator[_Said]:
    """The line said where the entry `labels` make up gives no `kind`: in place, or added `added` at line `end`."""
    given = [label for label in labels if label.label == kind]
    missing = _MISSING[kind]
    if not given:
        unlabeled = replace(labels[0], label=kind)
        yield (end, added), unlabeled.said(missing)
    elif not any(label.gives for label in given):
        first = given[0]
        yield (first.number, _WRITTEN), first.said(missing)
