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
code span some reading encloses, which is `report_code_spans`'s question, and
what HTML shows literally or hides, which is `report_html_literals`'s.

The one doubt that reads the other way is theirs to settle too: a tag quoted as
an example, in a span or a closed fence that is code however the text is read,
is no tag -- read as one it would take every line after it, and a description
that merely mentions `<pre>` would close nothing.

What is taken out leaves a character no keyword, number or whitespace is made
of, so the words either side of code never read as one reference; and a tag's
own markup goes the same way, since an attribute is nothing GitHub shows. A
tag nothing closes is no tag, unless it opens its line -- behind markers, or
behind what was taken out, which may have opened an HTML block -- where it
takes the rest of the text.

So does what Markdown itself reads and shows nothing of -- a link reference
definition, what stands behind a link's or an image's text, and an image's
description -- which is `report_link_fields`'s question, asked once the tags
are out, so a bracket in a tag's attribute pairs with nothing.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from orchestrator.workflow.engine import (
    report_code_spans as _code_spans,
    report_fences as _fences,
    report_html_literals as _html,
    report_link_fields as _link_fields,
)

# What stands where code was. Not whitespace, so `Fixes` and `#12` either side
# of a span are not a reference; not a word character, so a keyword beside it
# still starts on a word boundary.
_GAP = "\N{OBJECT REPLACEMENT CHARACTER}"

# The line endings Markdown knows beside the line feed every reading here is
# taken over.
_LINE_ENDING_RE = re.compile(r"\r\n?")

_LINE_FEED = "\n"

# Four columns in from wherever the markers leave off, which is as far as
# Markdown lets prose stand.
_CODE_INDENT_RE = re.compile(r" {4}| {0,3}\t")

# What opens any other tag, whose markup is read as an HTML tokenizer reads it;
# and what a line may open on before one -- markers, and whatever was taken out,
# since a comment or its like opens an HTML block that holds the rest of its
# line. A tag that opens a line and that nothing closes is what an HTML block
# hands the browser as it is -- where it takes the rest of the text. One nothing
# closes anywhere else is no tag.
_TAG_OPENER_RE = re.compile("</?[A-Za-z]")

_LINE_OPENING_RE = re.compile(rf"[ \t>*+{_GAP}-]*")

# A stretch of the text, as its two offsets.
type _Stretch = tuple[int, int]


def outside_code(text: str) -> str:
    """`text` with everything that may be shown as literal code taken out."""
    written = _LINE_ENDING_RE.sub(_LINE_FEED, text)
    spans = _code_spans.code_spans(written)
    code = _merged((*_code_lines(written), *spans.possible))
    definite = _merged((*_fences.definite_fences(written), *spans.certain))
    literal = _merged((*code, *_html.html_literals(written, code, definite)))
    return _without_markup(_without(written, literal))


def _without(text: str, stretches: list[_Stretch]) -> str:
    """`text` with each of `stretches`, in order and apart, left as one gap."""
    kept: list[str] = []
    cursor = 0
    for start, end in stretches:
        kept += [text[cursor:start], _GAP]
        cursor = end
    kept.append(text[cursor:])
    return "".join(kept)


def _without_markup(text: str) -> str:
    """`text` with what is read and not shown left as gaps.

    The markup of every tag first, and then what a link, an image or a
    definition reads of what is left.
    """
    shown = _without(text, list(_tag_markup(text)))
    return _without(shown, _merged(_link_fields.unshown_fields(shown)))


def _tag_markup(text: str) -> Iterator[_Stretch]:
    """The markup of every tag in `text`, in order and apart."""
    tags = _html.TagEnds(text)
    read_to = 0
    opener = _TAG_OPENER_RE.search(text)
    while opener is not None:
        closed = tags.closed_at(opener.end())
        if closed is None:
            line = _line_opened_at(text, opener.start(), read_to)
            if line is not None:
                yield line, len(text)
                return
            closed = opener.start() + 1
        else:
            yield opener.start(), closed
            read_to = closed
        opener = _TAG_OPENER_RE.search(text, closed)


def _line_opened_at(text: str, position: int, read_to: int) -> int | None:
    """Where the line begins that `position` opens; None where it opens none.

    Nor does it where that line began in a tag already read, up to `read_to`.
    """
    line = text.rfind(_LINE_FEED, 0, position) + 1
    if line < read_to or _LINE_OPENING_RE.fullmatch(text, line, position) is None:
        return None
    return line


def _code_lines(text: str) -> Iterator[_Stretch]:
    """Every line a fence may enclose or open, or that is indented as code."""
    fenced = _fences._fenced_line_starts(text, quoted=True)
    for line in _fences._LINE_RE.finditer(text):
        written = line.group()
        unmarked = _fences._CONTAINER_PREFIX_RE.match(written).end()
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
        reached = merged[-1][1] if merged else -2
        if start > reached + 1:
            merged.append((start, end))
        elif end > reached:
            merged[-1] = (merged[-1][0], end)
    return merged
