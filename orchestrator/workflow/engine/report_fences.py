# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which lines of an agent's Markdown message a code fence may enclose.

The developer report reader and the reviewer verification reader both ask, so
that a marker line Markdown shows as code is never read as the outcome. The
answer is reached without a Markdown parser, so a doubt reads as fenced: a
fence opens at the top level or behind the markers of the list items its line
opens, closes only on a bare run at its opening run's column, and stays open to
the end of the message past a line that may have ended the list item it sat
in. A blockquote's fence needs no reading: every line inside one opens on `>`,
and no marker line does.

`outside_code` is the same reading turned the other way, for a caller that
needs only the text Markdown certainly renders as prose -- the closing keywords
a pull request's description acts on, which GitHub does not read inside code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_LINE_RE = re.compile(r"^.*$", re.MULTILINE)

# What Markdown lets make up a blank line or trail a closing run: spaces, tabs,
# and the carriage return a CRLF line keeps. A no-break space, like any other
# character, is text.
_BLANK_CHARACTERS = " \t\r"

# A line that opens a code fence as Markdown renders one, behind the markers of
# any list items that line opens. A backtick run with another backtick after it
# on the line is inline code, not a fence.
_FENCE_OPENING_RE = re.compile(
    r"(?P<prefix>(?:[ \t]*(?:[-+*]|[0-9]{1,9}[.)])(?=[ \t]))*[ \t]*)"
    r"(?P<run>`{3,}(?!.*`)|~{3,}).*",
)

# An inline code span: a backtick run, then anything up to that same run alone.
_CODE_SPAN_RE = re.compile(r"(`+)[\s\S]*?(?<!`)\1(?!`)")

# A list item's content lines stand where the text after its marker does, so
# the lines inside a fence repeat its opening prefix with every marker
# character turned into a space.
_LIST_MARKER_CHARACTER_RE = re.compile(r"\S")


@dataclass(frozen=True)
class _OpenFence:
    """The run a code fence opened on, and what each line inside it repeats.

    `continuation` is the indentation a line needs to stay where the fence
    is, or None once a line has lacked it: that line may have ended the list
    item the fence sat in, and the fence with it, so no later line is trusted
    to close the fence.
    """

    run: str
    continuation: str | None


def _fenced_line_starts(text: str) -> frozenset[int]:
    """The offset of every line of `text` that may sit inside a code fence.

    A fence never closed runs to the end of the text.
    """
    fenced: set[int] = set()
    fence: _OpenFence | None = None
    for line in _LINE_RE.finditer(text):
        if fence is None:
            fence = _fence_opened_by(line.group())
        else:
            fenced.add(line.start())
            fence = _fence_after(fence, line.group())
    return frozenset(fenced)


def outside_code(text: str) -> str:
    """`text` with everything Markdown may show as literal code taken out.

    Lines a fence may enclose and the lines that open fences, indented lines,
    and inline code spans. A doubt reads as code, so what is left is prose.
    """
    fenced = _fenced_line_starts(text)
    prose = "\n".join(
        line.group() for line in _LINE_RE.finditer(text)
        if line.start() not in fenced
        and _fence_opened_by(line.group()) is None
        and not line.group().startswith(("    ", "\t"))
    )
    return _CODE_SPAN_RE.sub(" ", prose)


def _fence_opened_by(line: str) -> _OpenFence | None:
    opening = _FENCE_OPENING_RE.fullmatch(line)
    if opening is None:
        return None
    continuation = _LIST_MARKER_CHARACTER_RE.sub(" ", opening.group("prefix"))
    return _OpenFence(opening.group("run"), continuation)


def _fence_after(fence: _OpenFence, line: str) -> _OpenFence | None:
    """The fence still open after `line`, a line inside `fence`.

    A line stays where the fence is when it repeats the continuation or is
    blank. It closes the fence only when all it adds is a bare run of the
    fence's own character at least as long as the opening run, at that run's
    column: a run any further in may be the fence's content, since the list
    item the fence sits in can start left of its opening run.
    """
    if fence.continuation is None:
        return fence
    blank = not line.strip(_BLANK_CHARACTERS)
    if not blank and not line.startswith(fence.continuation):
        return _OpenFence(fence.run, None)
    closing = line.removeprefix(fence.continuation).rstrip(_BLANK_CHARACTERS)
    bare_run = not closing.strip(fence.run[0])
    return None if bare_run and closing.startswith(fence.run) else fence
