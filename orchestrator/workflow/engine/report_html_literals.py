# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What of a Markdown text HTML shows literally, or hides.

The elements GitHub renders as code or not at all -- `<pre>`, `<code>` and
their kind -- and comments, read off the text AS WRITTEN: an element is literal
whether or not some reading pairs a backtick across its opening tag. A tag is
read as HTML reads one, quoted attribute values and all, so a `>` or a closing
tag inside a quoted value ends nothing; a value whose quote never closes takes
the rest of the text, as it does in a browser.

Two doubts, settled opposite ways. A CLOSING tag is trusted only where it
stands in the same possible code, or the same prose, as the tag that opened the
element: one a code span may hide closes nothing, and an element nothing closes
runs to the end. An OPENING tag or comment opens nothing where it stands in
DEFINITE code -- a span or a closed fence that is code however the text is
read -- since a tag quoted as an example is no tag, and read as one it would
take every line after it. Inside an element already open that mercy ends: no
Markdown is read there, so every tag is a tag.

A tag is found by its OPENER and read to its end only once it counts. One
quoted as code is passed over at its name, so whatever follows that code is
still read: read to its own `>` first, a tag cut short inside a span would take
a real tag after the span as its attributes, and hide the element that opens.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterator
from typing import Final

# What opens a comment, or one tag of an element HTML shows literally or not
# at all: as far as its name, which is all a tag quoted as code is read for.
_OPENER_RE = re.compile(
    r"<!--|<(?P<closes>/?)(?P<tag>pre|code|samp|kbd|tt|script|style|textarea)\b",
    re.IGNORECASE,
)

# The rest of a tag past its name, quoted attribute values taken whole -- `\x22`
# and `\x27` being the two quotes. A tag its own `>` never closes, or a value its
# quote never closes, takes the rest of the text with it.
_TAG_REST_RE = re.compile(
    r"(?:\x22[^\x22]*(?:\x22|\Z)|\x27[^\x27]*(?:\x27|\Z)|[^>\x22\x27])*+>?",
)

_TAG = "tag"

_COMMENT_CLOSER = "-->"

# A stretch of the text, as its two offsets.
type _Stretch = tuple[int, int]

# Which stretch a position stands in, for one that stands in none.
_OUTSIDE = -1


def html_literals(
    text: str, code: list[_Stretch], definite: list[_Stretch],
) -> Iterator[_Stretch]:
    """Every stretch of `text` HTML shows literally or hides.

    `code` is every stretch that MAY be code and `definite` every stretch that
    certainly is, each in order and apart.
    """
    reading = _LiteralReading(_Stretches(code), _Stretches(definite))
    opener = _OPENER_RE.search(text)
    while opener is not None:
        resume = opener.end()
        if not reading.quotes(opener):
            resume = _ends_at(text, opener)
            ended = reading.ended_by(opener, resume)
            if ended is not None:
                yield ended
        opener = _OPENER_RE.search(text, resume)
    if reading.open_since is not None:
        yield reading.open_since, len(text)


def _ends_at(text: str, opener: re.Match[str]) -> int:
    """Where the comment or the tag `opener` opens ends, as HTML reads it."""
    if opener[_TAG] is not None:
        return _TAG_REST_RE.match(text, opener.end()).end()
    closer = text.find(_COMMENT_CLOSER, opener.end())
    return len(text) if closer < 0 else closer + len(_COMMENT_CLOSER)


class _Stretches:
    """Stretches of one text, in order and apart, asked which holds a position."""

    def __init__(self, stretches: list[_Stretch]) -> None:
        self._stretches: Final = stretches
        self._starts: Final = [start for start, _end in stretches]

    def holding(self, position: int) -> int:
        """Which stretch holds `position`, or `_OUTSIDE` for none."""
        nearest = bisect_right(self._starts, position) - 1
        if nearest >= 0 and position < self._stretches[nearest][1]:
            return nearest
        return _OUTSIDE


class _LiteralReading:
    """The literal element a left-to-right reading of the tags stands in.

    Opening tags are counted by name, so a nested element's closing tag closes
    that element and not the one around it.
    """

    def __init__(self, code: _Stretches, definite: _Stretches) -> None:
        self.open_since: int | None = None
        self._code: Final = code
        self._definite: Final = definite
        self._stands_in = _OUTSIDE
        self._depths: Counter[str] = Counter()

    def quotes(self, opener: re.Match[str]) -> bool:
        """Whether `opener` is an example quoted as code rather than HTML."""
        quoted = self._definite.holding(opener.start()) != _OUTSIDE
        return quoted and self.open_since is None

    def ended_by(self, opener: re.Match[str], end: int) -> _Stretch | None:
        """The literal stretch ended by what `opener` opens, which runs to `end`.

        None while it ends none. A comment is a stretch of its own unless an
        element already holds it.
        """
        if opener[_TAG] is None:
            return (opener.start(), end) if self.open_since is None else None
        if opener["closes"]:
            return self._closed_by(opener, end)
        if self.open_since is None:
            self.open_since = opener.start()
            self._stands_in = self._code.holding(opener.start())
        self._depths[opener[_TAG].lower()] += 1
        return None

    def _closed_by(self, opener: re.Match[str], end: int) -> _Stretch | None:
        tag = opener[_TAG].lower()
        hidden = self._code.holding(opener.start()) != self._stands_in
        if hidden or not self._depths[tag]:
            return None
        self._depths[tag] -= 1
        self._depths = +self._depths
        if self._depths or self.open_since is None:
            return None
        ended = (self.open_since, end)
        self.open_since = None
        return ended
