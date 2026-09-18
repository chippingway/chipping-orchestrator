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
own markup goes the same way, since an attribute is nothing GitHub shows.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator

from orchestrator.workflow.engine import (
    report_code_spans as _code_spans,
    report_fences as _fences,
    report_html_literals as _html,
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

# The markup of any other tag, attributes and all, as an HTML tokenizer reads
# them; and a tag that opens a line and that nothing closes, which an HTML block
# hands the browser as it is -- where it takes the rest of the text.
_HTML_TAG_RE = re.compile(
    rf"</?[A-Za-z][^\s/>]*{_html.TAG_ATTRIBUTES}>"
    rf"|^[ \t>*+-]*</?[A-Za-z][^\s/>]*{_html.TAG_ATTRIBUTES}\Z",
    re.MULTILINE,
)

# A stretch of the text, as its two offsets.
type _Stretch = tuple[int, int]


def outside_code(text: str) -> str:
    """`text` with everything that may be shown as literal code taken out."""
    written = _LINE_ENDING_RE.sub(_LINE_FEED, text)
    spans = _code_spans.code_spans(written)
    code = _merged((*_code_lines(written), *spans.possible))
    definite = _merged((*_fences.definite_fences(written), *spans.certain))
    literal = _merged((*code, *_html.html_literals(written, code, definite)))
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
