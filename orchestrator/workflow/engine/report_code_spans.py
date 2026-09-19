# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The inline code spans of a Markdown text: those possible, and those certain.

Markdown pairs backticks left to right within one stretch of inline text, and
where such a stretch begins is the doubt. A heading, a list item or a quote
starts a block with no blank line above it, and a table reads each CELL on its
own. And a backtick is no delimiter where something else has TAKEN it: an HTML
tag or an autolink binds as tightly as a code span with the leftmost winning, a
bare URL is linked where it stands and runs through a backtick to whitespace, a
link or an image reads its destination and title itself once its text has
closed, and a `$` may open math -- past any of which the pairing starts afresh.

So a span is looked for from EVERY place a reading could begin, within what
blank lines certainly bound: each line, each cell of a block that may hold a
table, and -- from the first `<`, `[`, `$` or bare URL standing in no certain
code -- past each `>`, `]`, `)` and `$` and the end of each bare URL. POSSIBLE
is whatever any of those readings encloses, for `report_prose`, to which a doubt
is code.

CERTAIN is the other end of the same doubt, for a reader that must not take a
tag quoted as code for a tag: a span every reading agrees on. One that ends
before the next place a reading could begin, begun where no earlier reading's
span runs in -- past there every reading reads alike -- and with none of those
takers before it in its block but inside the certain spans already found.

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

# A bare URL as GitHub links one where it stands: from its scheme or its `www.`
# through every character, a backtick included, to whitespace -- the six ASCII
# characters GitHub ends one on, not what `\s` does -- or a `<`. In any case, and
# whatever stands before it: whether it IS a link is one more doubt.
_BARE_URL = r"(?:(?:https?|ftp)://|www\.)"

_BARE_URL_RE = re.compile(rf"{_BARE_URL}[^ \t\n\v\f\r<]*", re.IGNORECASE)

# What may take a backtick for its own opens on one of these: a tag or an
# autolink, a link or an image or a footnote, math, and a bare URL. And each
# ends on one of those -- a link on its text's `]` where it is a reference, and
# on the `)` of its destination and title where it is not -- or where the bare
# URL does.
_TAKER_RE = re.compile(rf"[<\[$]|{_BARE_URL}", re.IGNORECASE)

_TAKER_ENDS = (re.compile(r"[>\])$]"), _BARE_URL_RE)

# Where a reading could begin: each line; and each cell as well, in a block
# that may hold a table. Every pipe is taken for a cell's edge, an escaped one
# too, since one reading more only adds to what is possible.
_LINE_START_RE = re.compile("^", re.MULTILINE)

_CELL_START_RE = re.compile(r"^|\|", re.MULTILINE)

# The row of dashes a table's header stands on, behind whatever markers its line
# opens on. Without one no line of the block is a row, and a pipe is a pipe.
_TABLE_DELIMITER_RE = re.compile(
    r"^[ \t>*+-]*\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*$",
    re.MULTILINE,
)

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
    """Read `text` from every place a reading of its inline code could begin.

    A reading runs to the end of what the blank lines bound, since stopping
    sooner could only leave a span it found unclosed.
    """
    runs = _BacktickRuns(text)
    read = [block.spans(text, runs) for block in _blocks(text)]
    return CodeSpans(
        tuple(chain.from_iterable(found.possible for found in read)),
        tuple(chain.from_iterable(found.certain for found in read)),
    )


def _blocks(text: str) -> Iterator[_Block]:
    """Each backticked block blank lines bound."""
    block_start = 0
    for line in _fences._LINE_RE.finditer(text):
        if _BLOCK_END_RE.fullmatch(line.group()) is not None:
            yield _Block(block_start, line.start())
            block_start = line.end()
    yield _Block(block_start, len(text))


@dataclass(frozen=True)
class _Block:
    """What blank lines bound: as far as any reading of inline code can run."""

    start: int
    end: int

    def spans(self, text: str, runs: _BacktickRuns) -> CodeSpans:
        """The spans of this block, one too crowded to read being code throughout."""
        if _BACKTICK not in text[self.start:self.end]:
            return CodeSpans((), ())
        begun = self._begun_past(text, (self._edges(text),), self.start)
        if len(begun) > _MAX_SPAN_READINGS:
            return CodeSpans(((self.start, self.end),), ())
        readings = [list(runs.spans_from(start, self.end)) for start in begun]
        certain = tuple(self._agreed(text, begun, readings))
        past_takers = self._begun_past_takers(text, certain)
        if len(begun) + len(past_takers) > _MAX_SPAN_READINGS:
            return CodeSpans(((self.start, self.end),), ())
        for start in past_takers:
            readings.append(list(runs.spans_from(start, self.end)))
        return CodeSpans(tuple(chain.from_iterable(readings)), certain)

    def _edges(self, text: str) -> re.Pattern[str]:
        """What a reading begins past: each line, or each cell where a table may be."""
        table = _TABLE_DELIMITER_RE.search(text, self.start, self.end)
        return _LINE_START_RE if table is None else _CELL_START_RE

    def _begun_past_takers(self, text: str, certain: tuple[_Stretch, ...]) -> list[int]:
        """Where a reading could begin past what may have taken a backtick.

        Past each end of one from the first that stands in no certain span:
        before it nothing such an end could close has begun, so a `>` or a `)`
        there ends nothing.
        """
        taken = self._first_taker(text, certain)
        return [] if taken is None else self._begun_past(text, _TAKER_ENDS, taken)

    def _begun_past(
        self, text: str, edges: tuple[re.Pattern[str], ...], since: int,
    ) -> list[int]:
        """Where a reading could begin: past each of `edges` in the block from `since`.

        Less those with no backtick before the next, which read as the next
        does -- so a text of many lines costs a reading per backticked one.
        """
        found = chain.from_iterable(
            edge.finditer(text, since, self.end) for edge in edges
        )
        begun = sorted({past.end() for past in found})
        following = [*begun, self.end][1:]
        return [
            start for start, until in zip(begun, following, strict=True)
            if _BACKTICK in text[start:until]
        ]

    def _agreed(
        self, text: str, begun: list[int], readings: list[list[_Stretch]],
    ) -> Iterator[_Stretch]:
        """The undisputed spans up to the first taker standing outside them."""
        cursor = self.start
        for span in self._undisputed(begun, readings):
            if _TAKER_RE.search(text, cursor, span[0]) is not None:
                return
            yield span
            cursor = span[1]

    def _undisputed(
        self, begun: list[int], readings: list[list[_Stretch]],
    ) -> Iterator[_Stretch]:
        """The spans ending before the next reading begins, where none runs in."""
        ends = [*begun, self.end][1:]
        for index, start in enumerate(begun):
            earlier = readings[:index]
            if not any(_runs_into(spans, start) for spans in earlier):
                yield from _staying_before(readings[index], ends[index])

    def _first_taker(self, text: str, certain: tuple[_Stretch, ...]) -> int | None:
        """Where the first taker standing in no certain span is, or None for none."""
        cursor = self.start
        for span_start, span_end in (*certain, (self.end, self.end)):
            taken = _TAKER_RE.search(text, cursor, span_start)
            if taken is not None:
                return taken.start()
            cursor = span_end
        return None


def _staying_before(spans: list[_Stretch], end: int) -> Iterator[_Stretch]:
    """The spans of one reading, in order, up to the first that runs past `end`."""
    for span in spans:
        if span[1] > end:
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
