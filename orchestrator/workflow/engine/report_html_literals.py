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
"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterator
from typing import Final

# A comment's opener; or one tag of an element HTML shows literally or not at
# all, its quoted attribute values taken whole -- `\x22` and `\x27` being the two
# quotes. A tag its own `>` never closes, or a value its quote never closes,
# takes the rest of the text with it.
_TOKEN_RE = re.compile(
    r"<!--"
    r"|<(?P<closes>/?)(?P<tag>pre|code|samp|kbd|tt|script|style|textarea)\b"
    r"(?:\x22[^\x22]*(?:\x22|\Z)|\x27[^\x27]*(?:\x27|\Z)|[^>\x22\x27])*+>?",
    re.IGNORECASE,
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
    resume = 0
    token = _TOKEN_RE.search(text)
    while token is not None:
        resume = token.end()
        if token[_TAG] is None:
            resume = reading.comment_ends(text, token)
        ended = reading.ended_by(token, resume)
        if ended is not None:
            yield ended
        token = _TOKEN_RE.search(text, resume)
    if reading.open_since is not None:
        yield reading.open_since, len(text)


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

    def comment_ends(self, text: str, opener: re.Match[str]) -> int:
        """Where the reading goes on past a comment's opener.

        Past the whole comment where it is one; past the opener alone where it
        stands in definite code, so that the text after it is still read.
        """
        if self._quoted(opener):
            return opener.end()
        closer = text.find(_COMMENT_CLOSER, opener.end())
        return len(text) if closer < 0 else closer + len(_COMMENT_CLOSER)

    def ended_by(self, token: re.Match[str], resume: int) -> _Stretch | None:
        """The literal stretch `token` ends, or None while it ends none.

        A comment, which runs to `resume`, is a stretch of its own unless an
        element already holds it.
        """
        if self._quoted(token):
            return None
        if token[_TAG] is None:
            return (token.start(), resume) if self.open_since is None else None
        if token["closes"]:
            return self._closed_by(token)
        if self.open_since is None:
            self.open_since = token.start()
            self._stands_in = self._code.holding(token.start())
        self._depths[token[_TAG].lower()] += 1
        return None

    def _quoted(self, token: re.Match[str]) -> bool:
        """Whether `token` is an example quoted as code rather than HTML."""
        quoted = self._definite.holding(token.start()) != _OUTSIDE
        return quoted and self.open_since is None

    def _closed_by(self, token: re.Match[str]) -> _Stretch | None:
        tag = token[_TAG].lower()
        hidden = self._code.holding(token.start()) != self._stands_in
        if hidden or not self._depths[tag]:
            return None
        self._depths[tag] -= 1
        self._depths = +self._depths
        if self._depths or self.open_since is None:
            return None
        ended = (self.open_since, token.end())
        self.open_since = None
        return ended
