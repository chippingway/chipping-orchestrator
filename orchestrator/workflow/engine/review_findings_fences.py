# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the code of a reviewer's findings opens and ends, as Markdown renders it.

`review_findings` reads each code block of the findings whole -- a fence, or
indented code -- to decide what a human is shown, so it asks where a reader
sees one end. That is not where `report_fences` stops trusting a fence: the
declaration readers err towards code, so that a marker line Markdown may show
as code is never taken, while a display running a block on past where
Markdown ends it, or missing one Markdown shows, would take the findings
around it for a declaration's lines, and drop them with a passing check's
transcript.

A fence opens on a run of three or more backticks or tildes, as
`report_fences` reads one, at most three spaces in from the content column of
the list item holding its line -- column 0 outside any list. It closes on the
first line holding only a run of its own character at least as long, at most
three spaces in from that same column however far in its opening run sat. A
non-blank line set in less than that column ends the list item, and the fence
with it, before that line. One never closed runs to the end. Indented code
opens on a non-blank line set four spaces or more past that column, where no
paragraph goes on -- Markdown reads such a line as more of the paragraph --
and holds every line so set, blank ones between, up to its last non-blank one.

Which list item holds a line is read line by line, as far as Markdown's
nesting can be without a parser. A line opening on a list marker, at most
three spaces in from the item it sits in, opens an item whose content starts
past the marker and the spaces after it -- one space past the marker where
five or more follow, the rest being indented code -- unless the line is a
thematic break, such as `* * *`, which Markdown reads first, or would go on
with a paragraph otherwise: only a bullet, or a marker numbered 1, with
content after it, interrupts a paragraph. A non-blank line set in less than
an item's content column ends that item, except where it continues a
paragraph lazily, as Markdown lets a line opening no block do: then every item
stays open, and a block below is read in the item it would be read in without
that line. A tab advances to the next multiple of four columns, as Markdown
counts it.
"""
from __future__ import annotations

import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass

from orchestrator.workflow.engine import report_fences as _fences

# What may make up a blank line or trail a closing run, a CRLF line's carriage
# return included.
_BLANKS = " \t\r"

_TAB_STOP = 4

# As far in from its list item's content column as a fence's run may sit: a
# column more and Markdown reads the run as indented code, or as content.
_FENCE_INDENT_RE = re.compile(" {0,3}")

# A list marker opening an item, at most three spaces in from the item it sits
# in, and the spaces after it -- none where the line ends at the marker.
_LIST_MARKER_RE = re.compile(r" {0,3}(?:[-+*]|[0-9]{1,9}[.)])(?P<gap> +|(?=\r?\Z))")

# The most spaces after a list marker that the item's content starts past.
_WIDEST_GAP = 4

# A thematic break: three or more of one of its characters, nothing but
# spaces between and after, at most three spaces in.
_THEMATIC_BREAK = r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t\r]*\Z"
_THEMATIC_BREAK_RE = re.compile(_THEMATIC_BREAK)

# What ends a paragraph rather than continuing it, at most three spaces in: a
# blank line, a thematic break, or a heading.
_NO_PARAGRAPH_RE = re.compile(rf"[ \t\r]*\Z|{_THEMATIC_BREAK}| {{0,3}}#{{1,6}}(?:[ \t]|\r?\Z)")

# What a line opens, at its own indentation, that interrupts a paragraph
# instead of continuing it lazily: a list item, a thematic break, a fence, a
# heading, or a block quote.
_INTERRUPTION_RE = re.compile(
    r"(?:[-+*]|[0-9]{1,9}[.)])(?:[ \t]|\r?\Z)|([-*_])(?:[ \t]*\1){2,}[ \t\r]*\Z"
    r"|`{3,}(?!.*`)|~{3,}|#{1,6}(?:[ \t]|\r?\Z)|>",
)

# A list marker that may open an item where the line would otherwise go on
# with a paragraph: a bullet, or an ordered marker numbered 1, with content
# after it on the line.
_INTERRUPTING_MARKER_RE = re.compile(r" {0,3}(?:[-+*]|0{0,8}1[.)])(?P<gap> +)(?=[^ \t\r])")

# Four spaces past the content column: indented code, unless a paragraph goes on.
_CODE_INDENT = " " * 4

# As far past the content column of the innermost item it keeps open as a line
# may still open a block: a column more, and it is indented code, which
# interrupts no paragraph.
_BLOCK_INDENT = 3


@dataclass(frozen=True)
class CodeBlock:
    """Lines Markdown shows as code, a fence or indented code, by their numbers.

    `start` and `end` bound all its lines, and `held_start` and `held_end` the
    lines it holds, between the fence lines a fence has and indented code has
    none of.
    """

    start: int
    held_start: int
    held_end: int
    end: int

    @property
    def opening(self) -> int:
        """How many fence lines open it: one for a fence, none for indented code."""
        return self.held_start - self.start

    @property
    def closing(self) -> int:
        """How many fence lines close it: none for a fence never closed, or for indented code."""
        return self.end - self.held_end


def markdown_code_blocks(lines: Sequence[str]) -> Iterator[CodeBlock]:
    """Each code block of `lines`, in order.

    A fence its list item ends, or that the lines end, has no closing line,
    and indented code holds its lines up to its last non-blank one.
    """
    reading = _Reading()
    for number, line in enumerate(lines):
        ended = reading.after(number, line.expandtabs(_TAB_STOP))
        if ended is not None:
            yield ended
    if reading.block is not None:
        yield reading.block.ended(len(lines))


@dataclass(frozen=True)
class _Fence:
    """An open fence: the line it opened on, its run, and the content column of the list item holding it."""

    opening: int
    run: str
    column: int

    def ends_before(self, line: str) -> bool:
        """Whether `line` ends the list item holding the fence, and the fence with it."""
        unindented = line.lstrip(" ")
        indent = len(line) - len(unindented)
        return indent < self.column and bool(unindented.strip(_BLANKS))

    def closes(self, line: str) -> bool:
        """Whether `line` holds only a run closing the fence, close enough in to close it."""
        within = line[self.column:]
        indent = _FENCE_INDENT_RE.match(within).end()
        bare = within[indent:].rstrip(_BLANKS)
        mark = self.run[0]
        return bare.startswith(self.run) and not bare.strip(mark)

    def through(self, number: int, line: str) -> _Fence:
        """The fence once `line`, line `number`, is read inside it: as it was."""
        return self

    def ended(self, number: int) -> CodeBlock:
        """The fence ended before line `number`, with no closing line."""
        return CodeBlock(self.opening, self.opening + 1, number, number)

    def closed(self, number: int) -> CodeBlock:
        """The fence line `number` closes."""
        return CodeBlock(self.opening, self.opening + 1, number, number + 1)


@dataclass(frozen=True)
class _Code:
    """Open indented code: its first line, one past its last non-blank one, and its list item's content column."""

    start: int
    stop: int
    column: int

    def ends_before(self, line: str) -> bool:
        """Whether `line`, not blank and set in less than four spaces past the column, ends the code."""
        blank = not line.strip(_BLANKS)
        return not blank and not line.startswith(_CODE_INDENT, self.column)

    def closes(self, line: str) -> bool:
        """Never: indented code has no closing line, only a line that ends it."""
        return False

    def through(self, number: int, line: str) -> _Code:
        """The code once `line`, line `number`, is read inside it: reaching that line unless it is blank."""
        if not line.strip(_BLANKS):
            return self
        return _Code(self.start, number + 1, self.column)

    def ended(self, number: int) -> CodeBlock:
        """The code ended at or before line `number`, holding its lines up to its last non-blank one."""
        return CodeBlock(self.start, self.start, self.stop, self.stop)


class _Reading:
    """Findings read line by line: the code block open, and the content column of each list item holding the line."""

    def __init__(self) -> None:
        self.block: _Fence | _Code | None = None
        self._columns: list[int] = []
        self._paragraph = False

    def after(self, number: int, line: str) -> CodeBlock | None:
        """The code block line `number`, reading as `line`, closes or ends, if any, once it is read."""
        block = self.block
        if block is not None and not block.ends_before(line):
            if not block.closes(line):
                self.block = block.through(number, line)
                return None
            self.block = None
            self._paragraph = False
            return block.closed(number)
        self._outside(number, line)
        return None if block is None else block.ended(number)

    def _outside(self, number: int, line: str) -> None:
        """Read `line`, outside any code: the list items it ends and opens, and the code block it opens."""
        self.block = None
        if self._continues(line):
            return
        column = self._column_of(line)
        self.block = self._opened(number, line, column)
        self._paragraph = self.block is None and not _NO_PARAGRAPH_RE.match(line, column)

    def _opened(self, number: int, line: str, column: int) -> _Fence | _Code | None:
        """The fence or indented code `line`, read from `column`, opens, if any.

        Indented code interrupts no paragraph: a line set that far in goes on
        with one instead.
        """
        opening = _fences._FENCE_OPENING_RE.fullmatch(line, column)
        margin = _FENCE_INDENT_RE.match(line, column).end()
        if opening is not None and opening.start("run") == margin:
            return _Fence(number, opening.group("run"), column)
        indented = line.startswith(_CODE_INDENT, column) and bool(line.strip(_BLANKS))
        if self._paragraph or not indented:
            return None
        return _Code(number, number + 1, column)

    def _continues(self, line: str) -> bool:
        """Whether `line` continues the paragraph above lazily, set in less than the innermost item's column.

        It does where it opens no block that would interrupt the paragraph,
        or sits too far past the column of the innermost item it keeps open
        to open one.
        """
        unindented = line.lstrip(" ")
        indent = len(line) - len(unindented)
        if not (self._paragraph and self._columns and indent < self._columns[-1]):
            return False
        if not unindented.strip(_BLANKS):
            return False
        kept = max((column for column in self._columns if column <= indent), default=0)
        return indent - kept > _BLOCK_INDENT or _INTERRUPTION_RE.match(unindented) is None

    def _column_of(self, line: str) -> int:
        """The content column of the innermost list item holding `line`, once the items it ends and opens are read.

        Where the line keeps the innermost item open and a paragraph runs in
        it, its first marker has to be one that may interrupt the paragraph.
        """
        ended = self._end_items(line)
        column = self._columns[-1] if self._columns else 0
        marker = _list_marker(line, column, interrupting=self._paragraph and not ended)
        while marker is not None:
            gap = len(marker.group("gap"))
            width = gap if 0 < gap <= _WIDEST_GAP else 1
            column = marker.start("gap") + width
            self._columns.append(column)
            marker = _list_marker(line, column)
        return column

    def _end_items(self, line: str) -> bool:
        """Forget each list item a non-blank `line` is set in less than the content column of, if any, saying so."""
        unindented = line.lstrip(" ")
        if not unindented.strip(_BLANKS):
            return False
        indent = len(line) - len(unindented)
        ended = bool(self._columns) and self._columns[-1] > indent
        while self._columns and self._columns[-1] > indent:
            self._columns.pop()
        return ended


def _list_marker(line: str, column: int, *, interrupting: bool = False) -> re.Match[str] | None:
    """The list marker `line` opens an item with at `column`, if any.

    A thematic break standing there opens none, and where the line would go on
    with a paragraph otherwise, only a bullet or an ordered marker numbered 1,
    with content after it, interrupts the paragraph.
    """
    if _THEMATIC_BREAK_RE.match(line, column):
        return None
    marker = _INTERRUPTING_MARKER_RE if interrupting else _LIST_MARKER_RE
    return marker.match(line, column)
