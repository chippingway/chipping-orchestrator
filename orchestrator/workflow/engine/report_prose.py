# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What of a Markdown text is certainly prose, whichever way it is read.

For the closing keywords a pull request's description acts on, which GitHub
does not read inside code. Reached without a Markdown parser, so the answer is
not one reading of the text but what EVERY reading leaves: a doubt reads as
code, and what comes back is prose under all of them.

Lines first, ended as Markdown ends them -- a bare carriage return included. A
line a fence may enclose, behind any nesting of list and blockquote markers, and
a line indented as code past whatever markers it opens on. Then every inline
code span some reading encloses, which is `report_code_spans`'s question.

Then what HTML shows literally or hides: `<pre>`, `<code>` and their kind, and
comments. Read off the text AS WRITTEN rather than off what the code above
leaves, since an element is literal whether or not some reading pairs a
backtick across its opening tag. Every opening tag counts, nested ones too, and
a closing tag is trusted only where it stands in the same code, or the same
prose, as the tag that opened the element: one a code span may hide closes
nothing. An element nothing closes runs to the end of the text.

What is taken out leaves a character no keyword, number or whitespace is made
of, so the words either side of code never read as one reference; and a tag's
own markup goes the same way, since an attribute is nothing GitHub shows.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterable, Iterator
from typing import Final

from orchestrator.workflow.engine import (
    report_code_spans as _code_spans,
    report_fences as _fences,
)

# What stands where code was. Not whitespace, so `Fixes` and `#12` either side
# of a span are not a reference; not a word character, so a keyword beside it
# still starts on a word boundary.
_GAP = "\N{OBJECT REPLACEMENT CHARACTER}"

# The line endings Markdown knows beside the line feed every reading here is
# taken over.
_LINE_ENDING_RE = re.compile(r"\r\n?")

_LINE_FEED = "\n"

# The markers a line opens on, in any nesting: up to three columns, a
# blockquote or list marker, and the one space that belongs to the marker.
_CONTAINER_PREFIX_RE = re.compile(r"(?: {0,3}(?:>|[-+*]|[0-9]{1,9}[.)]) ?)*")

# Four columns in from wherever the markers leave off, which is as far as
# Markdown lets prose stand.
_CODE_INDENT_RE = re.compile(r" {4}| {0,3}\t")

# A comment, whole; or one tag of an element HTML shows literally or not at
# all. A tag its own `>` never closes takes the rest of the text with it.
_HTML_LITERAL_TOKEN_RE = re.compile(
    r"<!--[\s\S]*?(?:-->|\Z)"
    r"|<(?P<closes>/?)(?P<tag>pre|code|samp|kbd|tt|script|style|textarea)\b[^>]*>?",
    re.IGNORECASE,
)

# The markup of any other tag, attributes and all.
_HTML_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")

# A stretch of the text, as its two offsets.
type _Stretch = tuple[int, int]

# Which stretch of code a position stands in, for one that stands in none.
_IN_PROSE = -1


def outside_code(text: str) -> str:
    """`text` with everything that may be shown as literal code taken out."""
    written = _LINE_ENDING_RE.sub(_LINE_FEED, text)
    code = _merged((*_code_lines(written), *_code_spans.possible_spans(written)))
    literal = _merged((*code, *_html_literals(written, code)))
    return _HTML_TAG_RE.sub(_GAP, _without(written, literal))


def _without(text: str, stretches: list[_Stretch]) -> str:
    """`text` with each of `stretches`, in order and apart, left as one gap."""
    kept: list[str] = []
    cursor = 0
    for start, end in stretches:
        kept += [text[cursor:start], _GAP]
        cursor = end
    kept.append(text[cursor:])
    return "".join(kept)


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


def _merged(stretches: Iterable[_Stretch]) -> list[_Stretch]:
    """`stretches` in order, with those that touch or overlap made one.

    Touching across the one character between two lines counts, so a fenced
    block is one stretch of code rather than a stretch per line -- which is
    what lets a tag and its closing tag inside it stand in the same code.
    """
    merged: list[_Stretch] = []
    for start, end in sorted(stretches):
        reached = merged[-1][1] if merged else _IN_PROSE - 1
        if start > reached + 1:
            merged.append((start, end))
        elif end > reached:
            merged[-1] = (merged[-1][0], end)
    return merged


def _html_literals(text: str, code: list[_Stretch]) -> Iterator[_Stretch]:
    """Every stretch of `text` HTML shows literally or hides, as written."""
    reading = _LiteralReading(code)
    for token in _HTML_LITERAL_TOKEN_RE.finditer(text):
        ended = reading.ended_by(token)
        if ended is not None:
            yield ended
    if reading.open_since is not None:
        yield reading.open_since, len(text)


class _LiteralReading:
    """The literal element a left-to-right reading of the tags stands in.

    Opening tags are counted by name, so a nested element's closing tag closes
    that element and not the one around it. A closing tag standing in other
    code than the tag that opened the element -- or in code where that tag
    stands in prose -- may be hidden by that code, and closes nothing.
    """

    def __init__(self, code: list[_Stretch]) -> None:
        self.open_since: int | None = None
        self._code: Final = code
        self._starts: Final = [start for start, _end in code]
        self._stands_in = _IN_PROSE
        self._depths: Counter[str] = Counter()

    def ended_by(self, token: re.Match[str]) -> _Stretch | None:
        """The literal stretch `token` ends, or None while it ends none.

        A comment is a stretch of its own, unless an element already holds it.
        """
        if token["tag"] is None:
            return token.span() if self.open_since is None else None
        if token["closes"]:
            return self._closed_by(token)
        if self.open_since is None:
            self.open_since = token.start()
            self._stands_in = self._standing(token.start())
        self._depths[token["tag"].lower()] += 1
        return None

    def _closed_by(self, token: re.Match[str]) -> _Stretch | None:
        tag = token["tag"].lower()
        hidden = self._standing(token.start()) != self._stands_in
        if hidden or not self._depths[tag]:
            return None
        self._depths[tag] -= 1
        self._depths = +self._depths
        if self._depths or self.open_since is None:
            return None
        ended = (self.open_since, token.end())
        self.open_since = None
        return ended

    def _standing(self, position: int) -> int:
        """Which stretch of code holds `position`, or `_IN_PROSE` for none."""
        nearest = bisect_right(self._starts, position) - 1
        if nearest >= 0 and position < self._code[nearest][1]:
            return nearest
        return _IN_PROSE
