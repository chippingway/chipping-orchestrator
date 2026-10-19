# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The failure entries a reviewer writes in its findings: read, and shown with what each leaves out said.

A reviewer is taught (`review_evidence_prompts`) to enter each failure its
findings rest on under the numbered item it supports, opening on a line
naming it -- `Failure:` -- with its own labels below, each on a line of its
own: `Error:`, `Expected:`, `Observed:`, `Reproduce:`, `Unavailable:`. An
entry runs from one `Failure:` line to the next, or to the next finding
before it -- a list item or a heading set out no further than its `Failure:`
line, or a paragraph set out less, which leaves its list item -- and a line a
code block holds is the block's, never a label, so a snippet quoting the
layout enters nothing;
and a paragraph of label lines opening on `Failure:` right above a check's
sentence, each line written as a lead writes it, is the lead the formatting
wrote for that check, never an entry -- one holding a label that gives
nothing is the reviewer's, since a lead's every label gives something.
A label gives what follows it on its line, or, where that is blank, the code
block below it, only blank lines between: a multi-line error, or a snippet. A
block holding no code, empty or blank, gives nothing.

`review_findings_failures` reads each entry (`FailureEntry`) to lead the
checks its error shows in. `review_findings` shows the entries themselves as
written, save what one leaves out, which it says where the entry stands
(`FailureEntry.annotated`), reading the findings' parts around their
declarations whole, as the entries are read, so an entry's labels may stand in
parts the declaration stood between: a `Failure:` line naming nothing, and an
error or a reproduction an entry has no label for, or a label giving nothing.
A label giving nothing is said in place; one an entry has none of is added in
the entry's own indentation -- an error below its `Failure:` line, a
reproduction below its last label -- each past the lines its label goes on
over and the code block below it, a block nothing closes closed first, so what
is added stands outside it. What is said gives each label a value, so showing
an entry again says nothing more.
"""
from __future__ import annotations

import math
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from itertools import accumulate, chain
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
# label lines right above one, opening its paragraph on a `Failure:` line, is
# the lead the formatting wrote for that check, never an entry of the
# reviewer's.
CHECK_SENTENCE_RE = re.compile(
    r"(?:(?P<run>`+)(?P<command>.+?)(?P=run)(?!`)|A check naming no command)"
    r" (?:exited with status .*|reported (?:no exit status|a blank exit status|the exit statuses .*))(?P<close>[.:])",
)

# Each line a lead the formatting writes holds (`review_findings_failures`),
# at the margin: what failed, named; its error, as a code span or a sentence
# saying why none is shown; where its test ID ends, unavailable; and a stdin
# command's snippet, unrecorded. A label giving nothing, or written any other
# way, is never the formatting's.
_LEAD_LINE_RE = re.compile(
    rf"{_NAME}: \S.*"
    rf"|{_ERROR}: (?:`.*`|not on pytest's summary line; see the output below|not recorded; the check quoted no output)"
    r"|Unavailable: where the test ID ends; .*"
    rf"|{_REPRODUCTION}: not recorded; `.*` reads its code from stdin, and no snippet was given(?: for .+)?",
)

# What the findings' parts around their declarations are read whole as
# joined by: one blank line.
_PARTED = "\n\n"

# A line's indentation, and a line opening a list item or a heading: a new
# finding, where it stands no further in than an entry's `Failure:` line. A
# line no new finding opens sets out nothing an entry has to reach.
_INDENT_RE = re.compile(r"[ \t]*")
_OPENING_RE = re.compile(r"[ \t]*(?:\d{1,9}[.)]|[-+*]|#{1,6})(?:[ \t]|$)")
_UNREACHED = math.inf

# A line ending no entry wherever it stands: a blank line, a label line, or the
# sentence the formatting shows a check by -- each ending what a label goes
# on over, too.
_ENDING_NOTHING_RE = re.compile(rf"[{_BLANKS}]*|{_LABEL_RE.pattern}|{CHECK_SENTENCE_RE.pattern}")

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

# Where a line said of an entry stands among those at its place: the fence
# closing a code block the findings never close, then an error added, then a
# reproduction added, all before the line written there.
_CLOSED = -1
_ERROR_ADDED = 0
_REPRODUCTION_ADDED = 1
_WRITTEN = 2

# A fence's opening line, read up to the run a line closing it repeats.
_FENCE_RE = re.compile(r"[ \t]*(?:`{3,}|~{3,})")
_Place = tuple[int, int]
_Said = tuple[_Place, str]

# How each line of the findings reads as a label line, None where it opens on no label.
_Labels = Sequence[re.Match[str] | None]


@dataclass(frozen=True)
class FailureEntry:
    """One failure the reviewer entered in the findings, under a line opening on `Failure:`.

    `name` is what that line names it; `error` what its `Error:` line gives,
    code-span backticks aside, or, where that line gives nothing, the last
    line of code in the block below it; `snippet` whether a code block holding
    code stands below its `Reproduce:` line -- the code a stdin command would
    read, which the command alone, however it is written there, does not give.
    """

    name: str
    error: str = ""
    snippet: bool = False

    @classmethod
    def read(cls, parts: Sequence[str]) -> tuple[FailureEntry, ...]:
        """Every entry the findings' `parts`, read whole, hold, in order."""
        return tuple(map(cls._of, _Lines(parts).entries))

    @classmethod
    def annotated(cls, parts: Sequence[str]) -> tuple[str, ...]:
        """Each of the findings' `parts`, read whole, with what each entry leaves out said where it stands.

        Every other line stays as written, in the part it stands in.
        """
        return _Lines(parts).annotated()

    @classmethod
    def naming(cls, entries: Sequence[FailureEntry], node: str) -> tuple[FailureEntry, ...]:
        """Each of `entries` whose name holds `node`, an ID pytest reported, whole."""
        whole = re.compile(_WHOLE_NODE.format(node=re.escape(node)))
        return tuple(entry for entry in entries if whole.search(entry.name))

    @classmethod
    def error_naming(cls, entries: Sequence[FailureEntry], node: str) -> str:
        """The error of the first of `entries` naming `node` that gives one; "" for none."""
        errors = (entry.error for entry in cls.naming(entries, node))
        return next(filter(None, errors), "")

    def backs(self, output: str) -> bool:
        """Whether the check that quoted `output` is this failure's: that output shows its error."""
        return bool(self.error) and self.error in output

    @classmethod
    def _of(cls, labels: Sequence[_Label]) -> FailureEntry:
        """The entry the label lines `labels` make up, a later label of a kind taking the place of an earlier."""
        errors = [label.error for label in labels if label.label == _ERROR]
        snippets = [bool(label.code) for label in labels if label.label == _REPRODUCTION]
        error = errors[-1] if errors else ""
        snippet = snippets[-1] if snippets else False
        return cls(labels[0].stated, error, snippet)


@dataclass(frozen=True)
class _Label:
    """A line opening on a label, read where it stands among the findings.

    `number` is the line's; `prefix` what stands before the label; `given`
    what follows its colon; `quoted` the lines of the code block below it,
    only blank lines between, or None where none stands there; `end` the
    number of the line after all it gives -- that block, or the lines it goes
    on over; and `unclosed` the line that would close that block where it is
    a fence nothing closes, "" otherwise: a line said at `end` would stand in
    the block, the reviewer's, unless the block is closed first.
    """

    number: int
    prefix: str
    label: str
    given: str
    quoted: tuple[str, ...] | None
    end: int
    unclosed: str = ""

    @property
    def stated(self) -> str:
        """What follows the colon, blanks aside."""
        return self.given.strip(_BLANKS)

    @property
    def code(self) -> tuple[str, ...]:
        """The lines of the code block below the label that hold anything, blanks aside; none for no block."""
        held = (line.strip(_BLANKS) for line in self.quoted or ())
        return tuple(filter(None, held))

    @property
    def gives(self) -> bool:
        """Whether the label gives anything: on its line, or as code in the block below it."""
        return bool(self.stated or self.code)

    @property
    def error(self) -> str:
        """What the label gives as an error: its line, code-span backticks aside, or its block's last line of code."""
        stated = self.stated.strip(_BACKTICK).strip(_BLANKS)
        return stated or next(reversed(self.code), "")

    def said(self, text: str) -> str:
        """This label's line giving `text`."""
        return f"{self.prefix}{self.label}: {text}"

    def takes(self, label: _Label, reach: Sequence[float]) -> bool:
        """Whether the entry this `Failure:` line opens takes `label`, below it: no line between ends it.

        `reach` says how far set out an entry has to be for each line of the
        findings to end it.
        """
        indent = len(_INDENT_RE.match(self.prefix).group().expandtabs())
        between = reach[self.number + 1:label.number]
        return min(between, default=_UNREACHED) > indent


class _Lines:
    """The lines of the findings, read whole across their parts, and the failure entries they hold.

    The parts are those around the findings' declarations, joined a blank
    line apart (`_parted` numbers each such line); each entry is its label
    lines, in order.
    """

    def __init__(self, parts: Sequence[str]) -> None:
        lines = _PARTED.join(parts).split("\n")
        self._lines = lines
        ends = accumulate(part.count("\n") + 2 for part in parts)
        self._parted = frozenset(end - 1 for end in ends)
        self._blocks = {block.start: block for block in _markdown.markdown_code_blocks(lines)}
        spans = (range(block.start, block.end) for block in self._blocks.values())
        self._held = frozenset(chain.from_iterable(spans)) | self._led()
        above = chain(("",), lines)
        holding = map(self._held.__contains__, range(len(lines)))
        self._reach = tuple(map(_reach, above, lines, holding))
        self.entries = self._grouped()

    def annotated(self) -> tuple[str, ...]:
        """Each part, with what each entry leaves out said: in the part holding the line above where it is said."""
        shown = {(number, _WRITTEN): line for number, line in enumerate(self._lines)}
        shown.update(chain.from_iterable(map(_left_out, self.entries)))
        parts: list[list[str]] = [[]]
        for number, place in sorted(shown):
            if place == _WRITTEN and number in self._parted:
                parts.append([])
            else:
                parts[-1].append(shown[number, place])
        return tuple("\n".join(part) for part in parts)

    def _grouped(self) -> tuple[tuple[_Label, ...], ...]:
        """Each entry's label lines, from its `Failure:` line to the next finding; those above the first, no entry's."""
        entries: list[list[_Label]] = []
        read = map(self._label, range(len(self._lines)))
        for label in filter(None, read):
            if label.label == _NAME:
                entries.append([label])
            elif entries and entries[-1][0].takes(label, self._reach):
                entries[-1].append(label)
        return tuple(map(tuple, entries))

    def _led(self) -> frozenset[int]:
        """The number of each line of a lead the formatting wrote above a check's sentence (`_lead_above`)."""
        labels = [_LABEL_RE.fullmatch(line) for line in self._lines]
        led: set[int] = set()
        for number, line in enumerate(self._lines):
            if CHECK_SENTENCE_RE.fullmatch(line):
                led.update(_lead_above(self._lines, labels, number))
        return frozenset(led)

    def _label(self, number: int) -> _Label | None:
        """Line `number` as a label line, with the block below it and where all it gives ends; None for no label.

        A line a code block holds is the block's, and a lead's line the
        formatting's, never a label of an entry.
        """
        line = "" if number in self._held else self._lines[number]
        labeled = _LABEL_RE.fullmatch(line)
        if labeled is None:
            return None
        below = self._block_below(number)
        written = labeled.group(*_FIELDS)
        if below is None:
            return _Label(number, *written, None, self._end(number))
        opening = _FENCE_RE.match(self._lines[below.start])
        return _Label(
            number,
            *written,
            tuple(self._lines[below.held_start:below.held_end]),
            below.end,
            "" if below.closing or opening is None else opening.group(),
        )

    def _block_below(self, number: int) -> _markdown.CodeBlock | None:
        """The code block opening on the first non-blank line below line `number`, if one does."""
        below = number + 1
        for line in self._lines[below:]:
            if line.strip(_BLANKS):
                break
            below += 1
        return self._blocks.get(below)

    def _end(self, number: int) -> int:
        """The number of the line after the lines label line `number` goes on over.

        None of them is blank, labeled, or code, nor a check's sentence -- the
        check's, as is the output below it -- nor opens the next finding
        (`_reach`), so what is said below a label stays the entry's own.
        """
        line = self._lines[number]
        indent = len(_INDENT_RE.match(line).group().expandtabs())
        end = number + 1
        for below in self._lines[end:]:
            stops = end in self._blocks or _ENDING_NOTHING_RE.fullmatch(below)
            if stops or self._reach[end] <= indent:
                break
            end += 1
        return end


def _reach(above: str, line: str, held: bool) -> float:
    """How far set out an entry standing above `line`, below `above`, has to be for `line` to end it.

    A new finding ends it: a list item or a heading set out no further than
    its `Failure:` line, or a paragraph set out less, which leaves its list
    item. A blank line, a label, a line going on over the one above it, the
    sentence the formatting shows a check by, and a line a code block or a
    lead holds -- `held` -- end none.
    """
    opening = _OPENING_RE.match(line)
    goes_on = opening is None and bool(above.strip(_BLANKS))
    if held or goes_on or _ENDING_NOTHING_RE.fullmatch(line):
        return _UNREACHED
    indent = len(_INDENT_RE.match(line).group().expandtabs())
    return indent if opening else indent + 1


def _lead_above(lines: Sequence[str], labels: _Labels, number: int) -> range:
    """The numbers of the lines of the lead right above the sentence on line `number`; none where no lead stands there.

    A lead is a paragraph of its own up to the sentence: label lines, `labels`
    reading each of `lines`, opening on a `Failure:` line, each written as a
    lead writes it. A run of label lines that opens no paragraph, opens on
    another label -- an entry's reproduction said right above a sentence the
    reviewer wrote, say -- or holds a line no lead writes, a label giving
    nothing among them, is the reviewer's.
    """
    top = number
    while top and labels[top - 1] is not None:
        top -= 1
    above = lines[top - 1] if top else ""
    opens = not above.strip(_BLANKS)
    named = top < number and labels[top].group("label") == _NAME
    written = all(map(_LEAD_LINE_RE.fullmatch, lines[top:number]))
    return range(top, number) if opens and named and written else range(0)


def _left_out(labels: Sequence[_Label]) -> Iterator[_Said]:
    """Each line said of the entry the label lines `labels` make up, by its place: what it leaves out.

    A name its `Failure:` line gives nothing of is said in place; so is an
    error or a reproduction where no label of that kind gives anything. One
    with no such label is added in the entry's indentation, an error after all
    its `Failure:` line gives, a reproduction after all its last label gives
    -- a code block there that nothing closes closed first, so what is added
    stands outside the reviewer's block, as it reads again.
    """
    named = labels[0]
    if not named.stated:
        yield (named.number, _WRITTEN), named.said(_UNNAMED)
    yield from _unstated(labels, _ERROR, named, _ERROR_ADDED)
    yield from _unstated(labels, _REPRODUCTION, labels[-1], _REPRODUCTION_ADDED)


def _unstated(labels: Sequence[_Label], kind: str, below: _Label, added: int) -> Iterator[_Said]:
    """The line said where the entry `labels` make up gives no `kind`: in place, or added `added` below `below`."""
    given = [label for label in labels if label.label == kind]
    missing = _MISSING[kind]
    if not given:
        unlabeled = replace(labels[0], label=kind)
        if below.unclosed:
            yield (below.end, _CLOSED), below.unclosed
        yield (below.end, added), unlabeled.said(missing)
    elif not any(label.gives for label in given):
        first = given[0]
        yield (first.number, _WRITTEN), first.said(missing)
