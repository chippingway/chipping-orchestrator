# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What of a Markdown text is certainly prose, whichever way it is read.

For the closing keywords a pull request's description acts on, which GitHub
does not read inside code. Reached without a Markdown parser, so the answer is
not one reading of the text but what EVERY reading leaves: a doubt reads as
code, and what comes back is prose under all of them.

Lines first. A line a fence may enclose, behind any nesting of list and
blockquote markers, and a line indented as code past whatever markers it opens
on. Then inline code, which Markdown pairs within one block -- and where a block
begins is the doubt: a heading, a list item or a quote can start one with no
blank line above it. So a span is looked for from EVERY line a block could
begin on, within what blank lines certainly bound, and whatever any of those
readings encloses is code. An escaped backtick opens nothing, being a literal
character; inside a span a backslash escapes nothing. Last, what HTML shows
literally or hides: `<pre>`, `<code>` and their kind, and comments.

What is taken out leaves a character no keyword, number or whitespace is made
of, so the words either side of a code span never read as one reference.
"""
from __future__ import annotations

import re
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Iterator

from orchestrator.workflow.engine import report_fences as _fences

# What stands where code was. Not whitespace, so `Fixes` and `#12` either side
# of a span are not a reference; not a word character, so a keyword beside it
# still starts on a word boundary.
_GAP = "\N{OBJECT REPLACEMENT CHARACTER}"

# The markers a line opens on, in any nesting: up to three columns, a
# blockquote or list marker, and the one space that belongs to the marker.
_CONTAINER_PREFIX_RE = re.compile(r"(?: {0,3}(?:>|[-+*]|[0-9]{1,9}[.)]) ?)*")

# Four columns in from wherever the markers leave off, which is as far as
# Markdown lets prose stand.
_CODE_INDENT_RE = re.compile(r" {4}| {0,3}\t")

# A line that certainly ends a block: blank, or nothing but blockquote markers.
_BLOCK_END_RE = re.compile(r"[ \t\r>]*")

# What an inline code span is delimited by, and what cannot delimit one: a
# backslash escape, whose character is literal text, and a backtick run. Read
# left to right, so the backtick of an escape is never seen as a run.
_INLINE_TOKEN_RE = re.compile(r"\\[\s\S]|`+")

_BACKTICK = "`"

# A stretch of the text, as its two offsets; and where every backtick run of
# one length starts, in order.
type _Stretch = tuple[int, int]

type _Runs = dict[int, list[int]]

# A backtick run as a span CLOSES on one: whole, and escaped or not, since
# inside a span a backslash is a literal character.
_BACKTICK_RUN_RE = re.compile("`+")

# How many lines of one block a span is looked for from. A block with more
# backticked lines than this is code throughout, so a description built to be
# slow to read is read quickly and as code.
_MAX_SPAN_READINGS = 64

# What HTML shows literally or not at all: the elements GitHub renders as code,
# and a comment. One never closed runs to the end of the text.
_HTML_LITERAL_RE = re.compile(
    r"<(?P<tag>pre|code|samp|kbd|tt)\b[^>]*>[\s\S]*?(?:</(?P=tag)\s*>|\Z)"
    r"|<!--[\s\S]*?(?:-->|\Z)",
    re.IGNORECASE,
)


def outside_code(text: str) -> str:
    """`text` with everything that may be shown as literal code taken out."""
    code = sorted((*_code_lines(text), *_possible_spans(text)))
    prose: list[str] = []
    cursor = 0
    for start, end in code:
        if start > cursor:
            prose.append(text[cursor:start])
        if end > cursor:
            prose.append(_GAP)
            cursor = end
    prose.append(text[cursor:])
    return _HTML_LITERAL_RE.sub(_GAP, "".join(prose))


def _code_lines(text: str) -> Iterator[_Stretch]:
    """Every line a fence may enclose or open, or that is indented as code."""
    fenced = _fences._fenced_line_starts(text, quoted=True)
    for line in _fences._LINE_RE.finditer(text):
        written = line.group()
        unmarked = _CONTAINER_PREFIX_RE.match(written).end()
        if (
            line.start() in fenced
            or _fences._fence_opened_by(written, quoted=True) is not None
            or _CODE_INDENT_RE.match(written, unmarked) is not None
        ):
            yield line.span()


def _possible_spans(text: str) -> Iterator[_Stretch]:
    """Every inline code span some reading of `text` encloses.

    One reading per backticked line of each block blank lines bound, begun at
    that line: a block that really begins there pairs its backticks from
    there, and one that does not is read from the line it does begin on. A
    reading runs to the end of what the blank lines bound, since stopping
    sooner could only leave a span it found unclosed.
    """
    runs = _runs_by_length(text)
    block_start = 0
    readings: list[int] = []
    for line in _fences._LINE_RE.finditer(text):
        if _BLOCK_END_RE.fullmatch(line.group()) is None:
            if _BACKTICK in line.group():
                readings.append(line.start())
            continue
        block = (block_start, line.start())
        yield from _spans_read(text, block, readings, runs)
        block_start = line.end()
        readings = []
    block = (block_start, len(text))
    yield from _spans_read(text, block, readings, runs)


def _runs_by_length(text: str) -> _Runs:
    """Where every backtick run of `text` starts, in order, under its length.

    Found once, so that each of a block's readings looks its closing runs up
    rather than searching the block again for every span it opens.
    """
    runs: _Runs = defaultdict(list)
    for run in _BACKTICK_RUN_RE.finditer(text):
        runs[len(run.group())].append(run.start())
    return runs


def _spans_read(
    text: str, block: _Stretch, readings: list[int], runs: _Runs,
) -> Iterator[_Stretch]:
    """The spans every one of `readings` finds in the `block` of `text`."""
    if len(readings) > _MAX_SPAN_READINGS:
        yield block
        return
    for reading in readings:
        yield from _spans_from(text, (reading, block[1]), runs)


def _spans_from(text: str, reading: _Stretch, runs: _Runs) -> Iterator[_Stretch]:
    """The code spans of `text` read left to right over `reading`.

    A span opens on a backtick run and closes on the next run of exactly that
    length. A run nothing closes is literal, and the reading goes on past it.
    """
    resume, end = reading
    token = _INLINE_TOKEN_RE.search(text, resume, end)
    while token is not None:
        resume = _closed_at(token, end, runs) or token.end()
        if resume > token.end():
            yield token.start(), resume
        token = _INLINE_TOKEN_RE.search(text, resume, end)


def _closed_at(token: re.Match[str], end: int, runs: _Runs) -> int | None:
    """Where the span `token` opens closes before `end`, or None for no span."""
    opener = token.group()
    if not opener.startswith(_BACKTICK):
        return None
    closers = runs.get(len(opener), ())
    nearest = bisect_left(closers, token.end())
    if nearest == len(closers):
        return None
    closed = closers[nearest] + len(opener)
    return closed if closed <= end else None
