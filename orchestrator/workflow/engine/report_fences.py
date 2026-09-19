# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which lines of an agent's Markdown message a code fence may enclose.

The developer report reader and the reviewer verification reader both ask, so
that a marker line Markdown shows as code is never read as the outcome. The
answer is reached without a Markdown parser, so a doubt reads as fenced: a
fence opens at the top level or behind the markers of the list items its line
opens, closes only on a bare run at its opening run's column, and stays open to
the end of the message past a line that may have ended the list item it sat
in. A blockquote's fence needs no reading: every line inside one opens on `>`,
and no marker line does.

`report_prose` asks the same question of a pull request's description, where a
quoted fence IS code that matters, so the reading takes blockquote markers among
the list markers on request. A fence still closes only behind the very markers
it opened behind, so a quoted run inside an unquoted fence closes nothing.

That reading errs towards code, which is the wrong way to err for a reader that
must not take a tag quoted as code for a tag. `definite_fences` is the other
end of the doubt: the closed fences that are fences however the text is read.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

_LINE_RE = re.compile(r"^.*$", re.MULTILINE)

# What Markdown lets make up a blank line or trail a closing run: spaces, tabs,
# and the carriage return a CRLF line keeps. A no-break space, like any other
# character, is text.
_BLANK_CHARACTERS = " \t\r"

# A line that opens a code fence as Markdown renders one, behind the markers of
# any list items that line opens. A backtick run with another backtick after it
# on the line is inline code, not a fence.
_FENCE_OPENING_RE = re.compile(
    r"(?P<prefix>(?:[ \t]*(?:[-+*]|[0-9]{1,9}[.)])(?=[ \t]))*[ \t]*)"
    r"(?P<run>`{3,}(?!.*`)|~{3,}).*",
)

# The same opening behind blockquote markers as well, in any nesting with the
# list markers: `- > ~~~` opens a fence as surely as `~~~` does.
_QUOTED_FENCE_OPENING_RE = re.compile(
    r"(?P<prefix>(?:[ \t]*(?:>|(?:[-+*]|[0-9]{1,9}[.)])(?=[ \t])))*[ \t]*)"
    r"(?P<run>`{3,}(?!.*`)|~{3,}).*",
)

# A list item's content lines stand where the text after its marker does, so
# the lines inside a fence repeat its opening prefix with every marker
# character turned into a space -- and every blockquote marker repeated, since
# a quoted line opens on one however deep in a list it sits.
_LIST_MARKER_CHARACTER_RE = re.compile(r"[^\s>]")


# The markers a line opens on, in any nesting: up to three columns, a
# blockquote or list marker, and the one space that belongs to the marker.
_CONTAINER_PREFIX_RE = re.compile(r"(?: {0,3}(?:>|[-+*]|[0-9]{1,9}[.)]) ?)*")

# As far in from its markers as a fence may open or close: a column more and
# Markdown reads the line as indented code, or as the paragraph above going on.
_AT_MARGIN_RE = re.compile(" {0,3}")

_BLOCKQUOTE_MARKER = ">"

_TAG_OPENER = "<"


@dataclass(frozen=True)
class _OpenFence:
    """The run a code fence opened on, and what each line inside it repeats.

    `continuation` is the indentation a line needs to stay where the fence
    is, or None once a line has lacked it: that line may have ended the list
    item the fence sat in, and the fence with it, so no later line is trusted
    to close the fence.
    """

    run: str
    continuation: str | None


def _fenced_line_starts(text: str, *, quoted: bool = False) -> frozenset[int]:
    """The offset of every line of `text` that may sit inside a code fence.

    A fence never closed runs to the end of the text. `quoted` reads the fences
    a blockquote holds as well, which a reader of marker lines has no use for.
    """
    fenced: set[int] = set()
    fence: _OpenFence | None = None
    for line in _LINE_RE.finditer(text):
        if fence is None:
            fence = _fence_opened_by(line.group(), quoted=quoted)
        else:
            fenced.add(line.start())
            fence = _fence_after(fence, line.group())
    return frozenset(fenced)


def _fence_opened_by(line: str, *, quoted: bool = False) -> _OpenFence | None:
    pattern = _QUOTED_FENCE_OPENING_RE if quoted else _FENCE_OPENING_RE
    opening = pattern.fullmatch(line)
    if opening is None:
        return None
    continuation = _LIST_MARKER_CHARACTER_RE.sub(" ", opening.group("prefix"))
    return _OpenFence(opening.group("run"), continuation)


def _fence_after(fence: _OpenFence, line: str) -> _OpenFence | None:
    """The fence still open after `line`, a line inside `fence`.

    A line stays where the fence is when it repeats the continuation or is
    blank. It closes the fence only when all it adds is a bare run of the
    fence's own character at least as long as the opening run, at that run's
    column: a run any further in may be the fence's content, since the list
    item the fence sits in can start left of its opening run.
    """
    if fence.continuation is None:
        return fence
    blank = not line.strip(_BLANK_CHARACTERS)
    if not blank and not line.startswith(fence.continuation):
        return _OpenFence(fence.run, None)
    closing = line.removeprefix(fence.continuation).rstrip(_BLANK_CHARACTERS)
    bare_run = not closing.strip(fence.run[0])
    return None if bare_run and closing.startswith(fence.run) else fence


def definite_fences(text: str) -> Iterator[tuple[int, int]]:
    """Every closed fence of `text` that is a fence however the text is read.

    From its opening line to its closing one. Opened at the margin of its
    markers, with no line since the last blank one opening on `<` -- an HTML
    block runs to the next blank line, and a fence inside one is text -- and
    closed where Markdown closes it, not merely where this owner's stricter
    reading does: a bare run Markdown would have closed on sooner, or a blank
    line that ended the blockquote the fence sat in, leaves what follows
    outside the fence, so such a fence is not offered at all.
    """
    reading = _DefiniteReading()
    for line in _LINE_RE.finditer(text):
        closed = reading.closed_by(line)
        if closed is not None:
            yield closed


class _DefiniteReading:
    """The fence a line-by-line reading stands in, and whether it is certain."""

    def __init__(self) -> None:
        self._fence: _OpenFence | None = None
        self._opened_at: int | None = None
        self._raw_html = False

    def closed_by(self, line: re.Match[str]) -> tuple[int, int] | None:
        """The definite fence `line` closes, or None while it closes none."""
        written = line.group()
        if self._fence is None:
            self._opens(line.start(), written)
            return None
        still_open = _fence_after(self._fence, written)
        if still_open is not None and self._ends_sooner(written):
            self._opened_at = None
        self._fence = still_open
        if still_open is not None or self._opened_at is None:
            return None
        return self._opened_at, line.end()

    def _opens(self, start: int, written: str) -> None:
        margin = _margin_of(written)
        if not written.strip(_BLANK_CHARACTERS + _BLOCKQUOTE_MARKER):
            self._raw_html = False
        elif written.startswith(_TAG_OPENER, margin):
            self._raw_html = True
        self._fence = _fence_opened_by(written, quoted=True)
        run = getattr(self._fence, "run", _TAG_OPENER)
        certain = not self._raw_html and written.startswith(run, margin)
        self._opened_at = start if certain else None

    def _ends_sooner(self, written: str) -> bool:
        """Whether Markdown may end the open fence on a line this owner reads on past."""
        fence = self._fence
        if not written.strip(_BLANK_CHARACTERS):
            return fence.continuation is None or _BLOCKQUOTE_MARKER in fence.continuation
        bare = written[_margin_of(written):].rstrip(_BLANK_CHARACTERS)
        mark = fence.run[0]
        return bare.startswith(fence.run) and not bare.strip(mark)


def _margin_of(written: str) -> int:
    """Where a line's text may start: past its markers, and up to three columns."""
    unmarked = _CONTAINER_PREFIX_RE.match(written).end()
    return _AT_MARGIN_RE.match(written, unmarked).end()
