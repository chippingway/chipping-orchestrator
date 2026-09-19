# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What of a Markdown text a link, an image or a definition reads and shows nothing of.

For `report_prose`, to which a closing keyword GitHub renders into an attribute,
or into nothing, closes no issue. Three things, each taken wherever it MAY be
one, since what is taken out that was prose after all only holds work back.

An image's DESCRIPTION, which is an `alt` attribute once rendered: from its `!`
to the bracket that closes it, brackets inside it paired as Markdown pairs them
-- innermost first, a backslash escaping one -- so a description holding a label
of its own is one description. Whatever follows it, or nothing: a collapsed or a
shortcut image is one by a definition elsewhere, which nobody looks up.

What stands BEHIND a link's or an image's text: the destination and title in
parentheses, or the label of the definition it names. A bare destination holds
parentheses in pairs, as deep as the renderer GitHub runs reads them; one that
goes deeper is taken to run to the whitespace that ends it, how deep a renderer
reads being one more doubt.

And a link reference DEFINITION whole, behind the markers its line opens on:
its destination may stand on the next line and its title on the one after, and
the rest of the line either ends on goes with it. Below a paragraph it cannot
interrupt it is taken all the same.

A title goes on over line endings, one behind a backslash included, and the
parts of a link stand either side of one behind whatever blockquote markers the
next line opens on, which Markdown has off before it reads the link.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from types import MappingProxyType
from typing import Final

# What Markdown counts as whitespace inside a link, in a character class.
_SPACE = r" \t\n\v\f"

# The blockquote markers a line may open on, behind the line ending before
# them: Markdown has them off before it reads a link, so what stands either
# side of a line ending inside one stands there behind them too.
_QUOTED_LINE = r"\n(?:[ \t]*+>)*+"

# The whitespace between the parts of what stands behind a link's text.
_BETWEEN = rf"(?:[ \t\v\f]|{_QUOTED_LINE})"

# A backslash and whatever it stands before, a line ending included. It
# escapes punctuation alone and is a character of its own before anything else,
# but nothing else it could stand before delimits a title, a label or a bracket
# -- and read as `\\.` reads it, one before a line ending would end a title
# that goes on to the next line.
_ESCAPED = r"\\[\s\S]"

# A link's title, in any of its three spellings, with whatever a backslash
# escapes inside it; `\x22` and `\x27` being the two quotes.
_TITLE = (
    rf"(?:\x22(?:[^\x22\\]++|{_ESCAPED})*+\x22|\x27(?:[^\x27\\]++|{_ESCAPED})*+\x27"
    rf"|\((?:[^()\\]++|{_ESCAPED})*+\))"
)

# As long as Markdown lets a label be, which bounds what is read for one.
_LABEL = rf"(?:[^\]\[\\]|{_ESCAPED}){{1,999}}+"

# A definition, behind the markers its line opens on.
_DEFINITION_RE = re.compile(
    rf"^(?: {{0,3}}(?:>|[-+*]|[0-9]{{1,9}}[.)]) ?)*+ {{0,3}}\[{_LABEL}\]:"
    rf"[ \t]*+(?:{_QUOTED_LINE})?[ \t]*+(?:<[^<>\n]*+>|[^{_SPACE}]++)"
    rf"(?:[ \t]*+(?:{_QUOTED_LINE})?[ \t]*+{_TITLE})?[^\n]*+",
    re.MULTILINE,
)

# The brackets of a text, and the escapes that are none.
_BRACKET_RE = re.compile(rf"{_ESCAPED}|[\[\]]")

_BRACKET_OPENER = "["

_BRACKET_CLOSER = "]"

_IMAGE_MARK = "!"

# What opens the parentheses behind a link's text, and what closes them past
# the destination: a title, or none.
_TAIL_OPENING_RE = re.compile(rf"\({_BETWEEN}*+")

_TAIL_CLOSING_RE = re.compile(rf"(?:{_BETWEEN}++{_TITLE})?{_BETWEEN}*+\)")

# A destination in angle brackets, which holds anything but a line ending.
_POINTED_DESTINATION_RE = re.compile(r"<[^<>\n]*+>")

_POINTED_OPENER = "<"

# What a bare destination is read by: the parentheses it holds in pairs and
# the whitespace that ends it, past the escapes that are neither. Whitespace
# ends one behind a backslash too, which escapes none of it.
_DESTINATION_MARK_RE = re.compile(
    rf"\\[^{_SPACE}]|[()]|(?P<space>[{_SPACE}])",
)

_ENDING_SPACE = "space"

# How much deeper in parentheses each of the two leaves a destination.
_PAREN_STEPS: Final = MappingProxyType({"(": 1, ")": -1})

# How deep the renderer GitHub runs reads the parentheses of a destination,
# which also bounds what is read pair by pair: a text of nothing but openers is
# read this deep from each, and from there straight to the whitespace that ends
# the destination.
_DEEPEST_PARENS = 32

_DESTINATION_END_RE = re.compile(rf"[{_SPACE}]|\Z")

# A stretch of the text, as its two offsets.
type _Stretch = tuple[int, int]


def unshown_fields(text: str) -> Iterator[_Stretch]:
    """Every stretch of `text` read as a link's, an image's or a definition's and not shown.

    In no order, and not apart: an image holds the link inside its description.
    """
    reading = _LinkReading(text)
    for opened, closed in reading.closes.items():
        if text[max(opened - 1, 0):opened] == _IMAGE_MARK:
            yield opened - 1, closed + 1
        behind = reading.behind_the_text(closed + 1)
        if behind is not None:
            yield closed, behind
    for definition in _DEFINITION_RE.finditer(text):
        yield definition.span()


def _closing_brackets(text: str) -> dict[int, int]:
    """Where the `]` of each `[` that has one stands, paired innermost first."""
    closes: dict[int, int] = {}
    opened: list[int] = []
    for bracket in _BRACKET_RE.finditer(text):
        if bracket.group() == _BRACKET_OPENER:
            opened.append(bracket.start())
        elif opened and bracket.group() == _BRACKET_CLOSER:
            closes[opened.pop()] = bracket.start()
    return closes


class _LinkReading:
    """The brackets of one text, and what stands behind each text they close.

    How far a run without whitespace goes is remembered from one destination
    to the next, so a text of nothing but over-deep destinations is read once.
    """

    def __init__(self, text: str) -> None:
        self.closes: Final = _closing_brackets(text)
        self._text: Final = text
        self._run: _Stretch = (0, -1)

    def behind_the_text(self, position: int) -> int | None:
        """Past what stands behind a link's text, which ends before `position`.

        The label it names, or its destination and title in parentheses. None
        for neither, which leaves what stands there as written.
        """
        label_closed = self.closes.get(position)
        if label_closed is not None:
            return label_closed + 1
        opening = _TAIL_OPENING_RE.match(self._text, position)
        if opening is None:
            return None
        destination = self._destination_end(opening.end())
        closing = None
        if destination is not None:
            closing = _TAIL_CLOSING_RE.match(self._text, destination)
        return None if closing is None else closing.end()

    def _destination_end(self, position: int) -> int | None:
        """Past the destination at `position`; None for one Markdown reads none of."""
        if not self._text.startswith(_POINTED_OPENER, position):
            return self._bare_destination_end(position)
        pointed = _POINTED_DESTINATION_RE.match(self._text, position)
        return None if pointed is None else pointed.end()

    def _bare_destination_end(self, position: int) -> int:
        """Past the destination at `position` that stands in no angle brackets."""
        depth = 0
        for mark in _DESTINATION_MARK_RE.finditer(self._text, position):
            depth += _PAREN_STEPS.get(mark.group(), 0)
            if mark[_ENDING_SPACE] or depth < 0:
                return mark.start()
            if depth > _DEEPEST_PARENS:
                return self._run_end(mark.end())
        return len(self._text)

    def _run_end(self, position: int) -> int:
        """Where the run without whitespace that `position` stands in ends."""
        known_from, known_end = self._run
        if not known_from <= position <= known_end:
            known_end = _DESTINATION_END_RE.search(self._text, position).start()
            self._run = (position, known_end)
        return known_end
