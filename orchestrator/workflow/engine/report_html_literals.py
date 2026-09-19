# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What of a Markdown text HTML shows literally, or hides.

The elements GitHub renders as code or not at all -- `<pre>`, `<code>` and
their kind -- and what it renders as nothing: a comment, a declaration, a
processing instruction, a CDATA section, and the bogus comment any other `<!`,
`<?` or `</` opens. Read off the text AS WRITTEN: an element is literal whether
or not some reading pairs a backtick across its opening tag.

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

What is hidden ends where the LATER of its two readings ends it. Markdown ends
a processing instruction at `?>` and a CDATA section at `]]>`; HTML ends either
at the first `>`, as it does every bogus comment, and that `>` is never the
later one. One with no terminator of Markdown's is HTML's alone, and one with no
`>` at all takes the rest of the text -- as a comment with no `-->` does. The
tags are read on from where HTML ends it, all the same: what Markdown hands on
whole the browser still reads from that `>`, where a comment may open that
Markdown's terminator does not close.

A tag is found by its OPENER and read to its end only once it counts. One
quoted as code is passed over at its `<` and no further, so whatever follows
that code is still read: read to its own `>` first, a tag cut short inside a
span would take a real tag after the span as its attributes, and hide the
element that opens; and passed over at its name, it would take one along that
stands right behind the span, since a name runs on through a backtick and a `<`.
For the same reason the openers inside a tag that counts are looked for from
every `<` of it, its name's included.
"""
from __future__ import annotations

import re
from bisect import bisect_right
from collections import Counter
from collections.abc import Iterator
from types import MappingProxyType
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

# A name a character longer than any of those is none of them, which is as
# much of one as an opener is read for: read whole, a text of nothing but
# openers would be read once for each.
_LONGEST_NAME: Final = max(map(len, _LITERAL_TAGS))

# What opens a comment, a CDATA section, any other hidden construct, or a tag
# of any name -- as far into the name as tells a literal element.
_OPENER_RE = re.compile(
    r"<!--|<!\[CDATA\[|<[!?]|</(?![A-Za-z])"
    rf"|<(?P<closes>/?)(?P<tag>[A-Za-z][^{HTML_SPACE}/>]{{0,{_LONGEST_NAME}}})",
)

# The rest of a tag's name, from anywhere in it.
_NAME_REST_RE = re.compile(rf"[^{HTML_SPACE}/>]*")

# One attribute of a tag, or what parts two, as an HTML tokenizer reads them,
# `\x22` and `\x27` being the two quotes: a name runs to whitespace, `/`, `>` or
# `=` and may open on a stray `=`; a quote opens a value only after the `=`
# behind a name, and anywhere else is a character like any other; a value never
# closed takes the rest of the text. Nothing but a `>` fails to be one.
_ATTRIBUTE_RE = re.compile(
    rf"[{HTML_SPACE}/]+|(?:=[^{HTML_SPACE}/>=]*|[^{HTML_SPACE}/>=]+)"
    rf"(?:[{HTML_SPACE}]*=[{HTML_SPACE}]*"
    rf"(?:\x22[^\x22]*(?:\x22|\Z)|\x27[^\x27]*(?:\x27|\Z)|[^{HTML_SPACE}>]*))?",
)

_TAG = "tag"

_TAG_CLOSER = ">"

_COMMENT_OPENER = "<!--"

_COMMENT_CLOSER = "-->"

# What Markdown ends a hidden construct at where HTML ends it sooner, at the
# first `>` as it ends every bogus comment.
_MARKDOWN_CLOSERS: Final = MappingProxyType({"<![CDATA[": "]]>", "<?": "?>"})

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
    tags = TagEnds(text)
    opener = _OPENER_RE.search(text)
    while opener is not None:
        resume = opener.start() + 1
        if not reading.quotes(opener):
            resume = tags.ends_at(opener)
            ended = reading.ended_by(opener, tags.hidden_to(opener, resume))
            if ended is not None:
                yield ended
            reading.opened_within(opener, _openers_within(text, opener, resume))
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


def _openers_within(
    text: str, around: re.Match[str], end: int,
) -> Iterator[re.Match[str]]:
    """Every opener in what `around` opens, which runs to `end`.

    From each `<` of it, so one inside another's name is found too.
    """
    opener = _OPENER_RE.search(text, around.start() + 1, end)
    while opener is not None:
        yield opener
        opener = _OPENER_RE.search(text, opener.start() + 1, end)


class TagEnds:
    """Where the tags of one text end, and what it hides, asked opener after opener.

    A tag nothing closes is read to the end of the text, and its reader may go
    on to ask of the next `<` inside it. So what one reading found unclosed is
    remembered by where each of its attributes began, a later reading that
    comes to stand there ending as that one did; and so is how far a run of
    name characters goes. A text of nothing but openers is read once.
    """

    def __init__(self, text: str) -> None:
        self.text: Final = text
        self._unclosed: set[int] = set()
        self._name_run: _Stretch = (_OUTSIDE, _OUTSIDE)

    def closed_at(self, named_to: int) -> int | None:
        """Past the `>` of the tag whose name is read to `named_to`.

        None for a tag nothing closes.
        """
        position = self._name_end(named_to)
        walked: list[int] = []
        attribute = self._attribute_at(position)
        while attribute is not None:
            walked.append(position)
            position = attribute.end()
            attribute = self._attribute_at(position)
        if self.text.startswith(_TAG_CLOSER, position):
            return position + len(_TAG_CLOSER)
        self._unclosed.update(walked)
        return None

    def ends_at(self, opener: re.Match[str]) -> int:
        """Where the tag or the hidden construct `opener` opens ends, as HTML reads it."""
        if opener[_TAG] is not None:
            return self.closed_at(opener.end()) or len(self.text)
        closer = _TAG_CLOSER
        if opener.group() == _COMMENT_OPENER:
            closer = _COMMENT_CLOSER
        return self._past(closer, opener.end()) or len(self.text)

    def hidden_to(self, opener: re.Match[str], ends_at: int) -> int:
        """Where what `opener` hides ends: at `ends_at`, or later as Markdown reads it."""
        closer = _MARKDOWN_CLOSERS.get(opener.group())
        if closer is None:
            return ends_at
        return self._past(closer, opener.end()) or ends_at

    def _past(self, closer: str, position: int) -> int | None:
        """Past the first `closer` from `position` on; None where there is none."""
        found = self.text.find(closer, position)
        return None if found < 0 else found + len(closer)

    def _name_end(self, position: int) -> int:
        """Where the name `position` stands in, or at the end of, ends."""
        known_from, known_end = self._name_run
        if not known_from <= position <= known_end:
            known_end = _NAME_REST_RE.match(self.text, position).end()
            self._name_run = (position, known_end)
        return known_end

    def _attribute_at(self, position: int) -> re.Match[str] | None:
        """The attribute at `position`; None at a `>`, the end, or a lost cause."""
        if position in self._unclosed:
            return None
        return _ATTRIBUTE_RE.match(self.text, position)


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

        None while it ends none. A hidden construct is a stretch of its own
        unless an element already holds it.
        """
        if opener[_TAG] is None:
            return (opener.start(), end) if self.open_since is None else None
        if not opener["closes"]:
            self.opened_by(opener, opener.start())
            return None
        return self._closed_by(_name_of(opener), opener.start(), end)

    def opened_within(
        self, around: re.Match[str], openers: Iterator[re.Match[str]],
    ) -> None:
        """Count each of `openers`, found in the markup `around` opens."""
        for opener in openers:
            self.opened_by(opener, around.start())

    def opened_by(self, opener: re.Match[str], since: int) -> None:
        """Count `opener` where it is the opening tag of a literal element.

        Wherever that is: the markup of another tag, or a comment, is no
        shelter, since it may be neither as Markdown reads it. The element is
        literal `since` that markup began, though: cut from its own tag on, it
        would take the `>` of the tag around it, and leave that tag's
        attributes standing as prose.
        """
        tag = _name_of(opener)
        if tag not in _LITERAL_TAGS or opener["closes"] or self.quotes(opener):
            return
        if self.open_since is None:
            self.open_since = since
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
