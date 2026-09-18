# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The inline code spans of a Markdown text: those possible, and those certain.

Markdown pairs backticks within one block, and where a block begins is the
doubt: a heading, a list item or a quote can start one with no blank line above
it. So a span is looked for from EVERY line a block could begin on, within what
blank lines certainly bound. POSSIBLE is whatever any of those readings
encloses, for `report_prose`, to which a doubt is code.

CERTAIN is the other end of the same doubt, for a reader that must not take a
tag quoted as code for a tag: a span every reading agrees on. One that stays on
its line, on a line no earlier reading's span runs into -- past that line's
start every reading reads alike -- and with no `<` before it in its block but
inside the certain spans already found: an HTML tag or an autolink binds as
tightly as a code span and the leftmost wins, so a backtick after a `<` may be
part of one rather than a delimiter.

An escaped backtick opens nothing, being a literal character; inside a span a
backslash escapes nothing, so a span closes on the next whole run of its
opener's length whatever stands before it.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass
from itertools import chain

from orchestrator.workflow.engine import report_fences as _fences

# A line that certainly ends a block: blank, or nothing but blockquote markers.
_BLOCK_END_RE = re.compile(r"[ \t>]*")

# What an inline code span is delimited by, and what cannot delimit one: a
# backslash escape, whose character is literal text, and a backtick run. Read
# left to right, so the backtick of an escape is never seen as a run.
_INLINE_TOKEN_RE = re.compile(r"\\[\s\S]|`+")

_BACKTICK = "`"

# What an HTML tag or an autolink opens on.
_TAG_OPENER = "<"

# A stretch of the text, as its two offsets.
type _Stretch = tuple[int, int]

# A backtick run as a span CLOSES on one: whole, and escaped or not, since
# inside a span a backslash is a literal character.
_BACKTICK_RUN_RE = re.compile("`+")

# How many lines of one block a span is looked for from. A block with more
# backticked lines than this is code throughout, so a description built to be
# slow to read is read quickly and as code.
_MAX_SPAN_READINGS = 64


@dataclass(frozen=True)
class CodeSpans:
    """The spans some reading of a text encloses, and those every reading does."""

    possible: tuple[_Stretch, ...]
    certain: tuple[_Stretch, ...]


def code_spans(text: str) -> CodeSpans:
    """Read `text` from every line a block could begin on.

    One reading per backticked line of each block blank lines bound, begun at
    that line: a block that really begins there pairs its backticks from
    there, and one that does not is read from the line it does begin on. A
    reading runs to the end of what the blank lines bound, since stopping
    sooner could only leave a span it found unclosed.
    """
    runs = _BacktickRuns(text)
    read = [block.spans(text, runs) for block in _blocks(text)]
    return CodeSpans(
        tuple(chain.from_iterable(found.possible for found in read)),
        tuple(chain.from_iterable(found.certain for found in read)),
    )


def _blocks(text: str) -> Iterator[_Block]:
    """Each block blank lines bound, beside the backticked lines within it."""
    block_start = 0
    lines: list[_Stretch] = []
    for line in _fences._LINE_RE.finditer(text):
        if _BLOCK_END_RE.fullmatch(line.group()) is None:
            if _BACKTICK in line.group():
                lines.append(line.span())
            continue
        yield _Block(block_start, line.start(), tuple(lines))
        block_start = line.end()
        lines = []
    yield _Block(block_start, len(text), tuple(lines))


@dataclass(frozen=True)
class _Block:
    """What blank lines bound, and the lines of it a reading is begun at."""

    start: int
    end: int
    lines: tuple[_Stretch, ...]

    def spans(self, text: str, runs: _BacktickRuns) -> CodeSpans:
        """The spans of this block, one too crowded to read being code throughout."""
        if len(self.lines) > _MAX_SPAN_READINGS:
            return CodeSpans(((self.start, self.end),), ())
        starts = (line[0] for line in self.lines)
        readings = [list(runs.spans_from(start, self.end)) for start in starts]
        return CodeSpans(
            tuple(chain.from_iterable(readings)),
            tuple(self._agreed(text, readings)),
        )

    def _agreed(self, text: str, readings: list[list[_Stretch]]) -> Iterator[_Stretch]:
        """The undisputed spans up to the first `<` standing outside them."""
        cursor = self.start
        for span in self._undisputed(readings):
            if _TAG_OPENER in text[cursor:span[0]]:
                return
            yield span
            cursor = span[1]

    def _undisputed(self, readings: list[list[_Stretch]]) -> Iterator[_Stretch]:
        """The spans that stay on a line no earlier reading's span runs into."""
        for index, line in enumerate(self.lines):
            earlier = readings[:index]
            if not any(_runs_into(spans, line[0]) for spans in earlier):
                yield from _staying_before(readings[index], line[1])


def _staying_before(spans: list[_Stretch], line_end: int) -> Iterator[_Stretch]:
    """The spans of one reading, in order, up to the first that leaves its line."""
    for span in spans:
        if span[1] > line_end:
            return
        yield span


def _runs_into(spans: list[_Stretch], position: int) -> bool:
    """Whether one of `spans`, in order, opens before `position` and ends past it."""
    nearest = bisect_left(spans, (position,)) - 1
    return nearest >= 0 and spans[nearest][1] > position


class _BacktickRuns:
    """Where every backtick run of one text starts, in order, under its length.

    Found once, so that each of a block's readings looks its closing runs up
    rather than searching the block again for every span it opens.
    """

    def __init__(self, text: str) -> None:
        self._text = text
        self._starts: dict[int, list[int]] = defaultdict(list)
        for run in _BACKTICK_RUN_RE.finditer(text):
            self._starts[len(run.group())].append(run.start())

    def spans_from(self, start: int, end: int) -> Iterator[_Stretch]:
        """The code spans read left to right from `start` to `end`.

        A span opens on a backtick run and closes on the next run of exactly
        that length. A run nothing closes is literal, and the reading goes on
        past it.
        """
        token = _INLINE_TOKEN_RE.search(self._text, start, end)
        while token is not None:
            resume = self._closed_at(token, end) or token.end()
            if resume > token.end():
                yield token.start(), resume
            token = _INLINE_TOKEN_RE.search(self._text, resume, end)

    def _closed_at(self, token: re.Match[str], end: int) -> int | None:
        """Where the span `token` opens closes before `end`, or None for no span."""
        opener = token.group()
        if not opener.startswith(_BACKTICK):
            return None
        closers = self._starts.get(len(opener), ())
        nearest = bisect_left(closers, token.end())
        if nearest == len(closers):
            return None
        closed = closers[nearest] + len(opener)
        return closed if closed <= end else None
