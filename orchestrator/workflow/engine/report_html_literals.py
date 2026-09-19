# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What of a Markdown text HTML shows literally, or hides.

The elements GitHub renders as code or not at all -- `<pre>`, `<code>` and
their kind -- and comments, read off the text AS WRITTEN: an element is literal
whether or not some reading pairs a backtick across its opening tag.

EVERY tag is read, not those elements' alone, and read as an HTML tokenizer
reads one: a quote opens an attribute's value only after its `=`, a value never
closed takes the rest of the text, and whatever stands inside a tag -- or a
comment, or the bogus comment a `<!` or a `<?` opens -- is that tag's markup.
So a closing tag inside another tag's quoted value closes nothing. Whitespace
is HTML's own five characters and a name is folded as HTML folds one, in ASCII
alone: a no-break space is a character of the name it stands in, so `</pre` and
one after it names an element that is not `pre`, and closes nothing.

Whether a tag-like stretch IS a tag is a doubt of its own, since Markdown hands
HTML on as written only where its own, stricter syntax is met. It is settled
towards code both ways: a CLOSING tag is trusted only as a tag of its own,
standing in no other tag's markup, while an OPENING tag counts wherever it is
found, inside another's markup or a comment included.

Two more doubts, settled opposite ways. A closing tag is trusted only where it
stands in the same possible code, or the same prose, as the tag that opened the
element: one a code span may hide closes nothing, and an element nothing closes
runs to the end. An opening tag or comment opens nothing where it stands in
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

# The elements HTML shows literally, or not at all.
_LITERAL_TAGS = frozenset((
    "pre", "code", "samp", "kbd", "tt", "script", "style", "textarea",
))

# What HTML counts as whitespace, inside a character class: the tab, the line
# feed, the form feed, the carriage return and the space. Not what `\s` does --
# a no-break space, a vertical tab and a line separator are characters of
# whatever name or value they stand in.
HTML_SPACE: Final = r" \t\n\f\r"

# What opens a comment, a bogus comment, or a tag of any name -- as far as the
# name, which is all a tag quoted as code is read for.
_OPENER_RE = re.compile(
    rf"<!--|<[!?]|</(?![A-Za-z])|<(?P<closes>/?)(?P<tag>[A-Za-z][^{HTML_SPACE}/>]*)",
)

# A tag's attributes as an HTML tokenizer reads them, `\x22` and `\x27` being the
# two quotes: a name runs to whitespace, `/`, `>` or `=` and may open on a stray
# `=`; a quote opens a value only after the `=` behind a name, and anywhere else
# is a character like any other; a value never closed takes the rest of the text.
TAG_ATTRIBUTES: Final = (
    rf"(?:[{HTML_SPACE}/]+|(?:=[^{HTML_SPACE}/>=]*|[^{HTML_SPACE}/>=]+)"
    rf"(?:[{HTML_SPACE}]*=[{HTML_SPACE}]*"
    rf"(?:\x22[^\x22]*(?:\x22|\Z)|\x27[^\x27]*(?:\x27|\Z)|[^{HTML_SPACE}>]*))?)*+"
)

# The rest of a tag past its name, and of a bogus comment past its opener: each
# to its own `>`, or to the end of a text that has none.
_TAG_REST_RE = re.compile(f"{TAG_ATTRIBUTES}>?")

_BOGUS_REST_RE = re.compile("[^>]*>?")

_TAG = "tag"

_COMMENT_OPENER = "<!--"

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
            for within in _OPENER_RE.finditer(text, opener.end(), resume):
                reading.opened_by(within)
        opener = _OPENER_RE.search(text, resume)
    if reading.open_since is not None:
        yield reading.open_since, len(text)


def _name_of(opener: re.Match[str]) -> str:
    """The element a tag names, folded as HTML folds a name; "" for none.

    In ASCII alone: a name holding any other character names no element here,
    whatever a wider case folding would make of it.
    """
    tag = opener[_TAG] or ""
    return tag.lower() if tag.isascii() else ""


def _ends_at(text: str, opener: re.Match[str]) -> int:
    """Where the comment or the tag `opener` opens ends, as HTML reads it."""
    if opener[_TAG] is not None:
        return _TAG_REST_RE.match(text, opener.end()).end()
    if opener.group() != _COMMENT_OPENER:
        return _BOGUS_REST_RE.match(text, opener.end()).end()
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
        if opener.group() == _COMMENT_OPENER and self.open_since is None:
            return opener.start(), end
        if opener[_TAG] is None or not opener["closes"]:
            self.opened_by(opener)
            return None
        return self._closed_by(_name_of(opener), opener.start(), end)

    def opened_by(self, opener: re.Match[str]) -> None:
        """Count `opener` where it is the opening tag of a literal element.

        Wherever that is: the markup of another tag, or a comment, is no
        shelter, since it may be neither as Markdown reads it.
        """
        tag = _name_of(opener)
        if tag not in _LITERAL_TAGS or opener["closes"] or self.quotes(opener):
            return
        if self.open_since is None:
            self.open_since = opener.start()
            self._stands_in = self._code.holding(opener.start())
        self._depths[tag] += 1

    def _closed_by(self, tag: str, start: int, end: int) -> _Stretch | None:
        hidden = self._code.holding(start) != self._stands_in
        if hidden or not self._depths[tag]:
            return None
        self._depths[tag] -= 1
        self._depths = +self._depths
        if self._depths or self.open_since is None:
            return None
        ended = (self.open_since, end)
        self.open_since = None
        return ended
