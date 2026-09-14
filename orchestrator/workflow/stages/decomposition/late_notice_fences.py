# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Compact Markdown fences that preserve every line of a recorded explanation.

Closing runs are measured for both fence characters. Candidate caps split
the quote into safe blocks, and the shortest complete rendering wins. Line
endings stay intact, including explanations without a final newline.
"""
from __future__ import annotations

import re

# What the shortest fence is, the two characters markdown builds one out of,
# and how a run of each is found. A thread is markdown, so an explanation is
# put in a fenced block: inside one, text opening an HTML comment is shown
# rather than obeyed, which is the whole point -- an agent writing `<!--`
# anywhere would otherwise swallow the rest of the sentence, and a human would
# be told neither what it said nor what to do about it. Escaping the openers
# instead grows the comment per occurrence, which an explanation the record
# can hold is enough of to push past what GitHub accepts; a fence costs the
# same handful of characters however long the quote is.
#
# A fence has to be longer than any LINE inside it that could close it, and a
# line closes one only by being a run of the fence character and nothing else
# -- a run in the middle of a line closes nothing. Which is why both
# characters are kept rather than one: a line of backticks cannot close a
# tilde fence at all, so the explanation that would cost a backtick fence a
# copy of itself at each end costs a tilde fence three characters. The
# backtick comes first, so a quote that leaves both cheap is blocked off by
# the ordinary one.
_SHORTEST_FENCE = 3

_FENCE_CHARACTERS = ("`", "~")

# What ends a line, for markdown and so for a fence. A quote is split on all
# of them and rejoined by the ones it arrived with, because an explanation
# written on a machine that ends its lines with a carriage return is still an
# explanation whose fence lines close a block -- and reading only the newline
# would block such a quote off at three characters it carries.
_LINE_ENDINGS = ("\n", "\r")

_FENCE_LINE = re.compile(r"\A[ \t]*(`+|~+)[ \t]*(?:\r\n|[\n\r])?\Z")

# And what to do where neither character is cheap, which is the quote carrying
# a long line of each: the quote is BLOCKED OFF IN PIECES rather than in one.
# A fence costs two characters for every character of width and a further
# block costs a fixed handful, so the two trade against each other -- a wide
# fence buys one block for a quote whose lines are wide, and many narrow
# blocks buy a narrow fence for a quote whose wide lines are few.
#
# Which way round is not something a rule of thumb gets right: a quote of
# eight-character fence lines wants ONE block nine characters wide, and a
# quote of two enormous ones wants three blocks three characters wide, and a
# greedy that splits whenever a widening looks dear picks the first badly. So
# every width from the shortest fence up to the widest line is tried by
# doubling, and the smallest rendering wins. Each pass is one walk of the
# lines and there are as many passes as the quote has doublings, which is
# nothing beside what it costs to be wrong.
_CAP_STEP = 2


def _quoted_block(quoted: str) -> str:
    """This text between fences no line inside one can close.

    A fence is longer than any line in the block that could close it, because
    markdown ends a fenced block on a line that is a run of the fence
    character and nothing else -- so a quote carrying a fence of its own would
    otherwise close this one early and let everything after it render as
    markdown again, which is the failure the fence is here to prevent. A run
    in the MIDDLE of a line closes nothing, which is what keeps the fence a
    handful of characters around prose that merely mentions one.

    Which character it is built out of follows from that: a line of backticks
    cannot close a tilde fence, so the cheaper of the two is taken. That
    answers the explanation that is a long run of ONE character; the one that
    carries a long line of EACH is answered by blocking the quote off in
    pieces, since a fence is two characters per character of width and a
    further block is a fixed handful.

    How wide to let a fence grow before paying for a block instead is the
    whole of it, and it is answered by trying: every width from the shortest
    fence up to the widest line the quote carries, doubling, and the smallest
    rendering wins. A quote of narrow fence lines wants one wide block and a
    quote of two enormous ones wants three narrow blocks, and nothing local to
    a line tells them apart.
    """
    lines = quoted.splitlines(keepends=True)
    closings = [_closing_lengths(line) for line in lines]
    return min(
        (_blocked_at(lines, closings, cap) for cap in _fence_caps(closings)),
        key=len,
    )


def _fence_caps(closings: list[tuple[int, int]]) -> list[int]:
    """The fence widths worth blocking a quote off at.

    From the shortest fence markdown has to the widest line in the quote,
    doubling: below the first nothing is legal and above the last nothing is
    bought, and between them the doublings bracket whatever the best answer
    is closely enough that the rendering they miss is a handful of characters
    rather than a copy of the quote.
    """
    widest = max(
        (max(closing) for closing in closings), default=0,
    ) + 1
    caps = []
    cap = _SHORTEST_FENCE
    while cap < widest:
        caps.append(cap)
        cap *= _CAP_STEP
    caps.append(max(widest, _SHORTEST_FENCE))
    return caps


def _blocked_at(
    lines: list[str], closings: list[tuple[int, int]], cap: int,
) -> str:
    """This quote in blocks, none of them fenced wider than `cap`.

    A line that would widen the fence past the cap starts a fresh block
    instead, and every block is fenced at its own width rather than the cap's
    -- so a cap that is never reached costs one block and nothing else.
    """
    blocks = []
    held: list[str] = []
    closes = (0, 0)
    for line, closing in zip(lines, closings, strict=True):
        if held and len(_fence_of(_widened(closes, closing))) > cap:
            blocks.append(_walled(held, closes))
            held = []
            closes = (0, 0)
        held.append(line)
        closes = _widened(closes, closing)
    blocks.append(_walled(held, closes))
    return "\n".join(blocks)


def _widened(
    closes: tuple[int, int], closing: tuple[int, int],
) -> tuple[int, int]:
    """The longest closing run of each character, with one more line in it."""
    return tuple(
        max(so_far, added)
        for so_far, added in zip(closes, closing, strict=True)
    )


def _closing_lengths(line: str) -> tuple[int, int]:
    """How long a fence of each character this ONE line could close.

    A line closes a block only by being a run of the fence character with
    nothing else on it, so this answers zero for every line that merely
    carries a run -- which is most of them, and why an explanation that talks
    about fences is still blocked off by three characters.

    Leading and trailing whitespace is allowed around the run rather than
    refused, because markdown allows it on a closing fence and reading it as
    harmless would be the reading that lets a quote close its own block. The
    line ENDING is allowed for the same reason and matters more: the line
    arrives with the terminator it was written with, and markdown ends a line
    on a carriage return as readily as on a newline -- so a run followed by
    `\r\n` or by a bare `\r` is a closing fence, and one read as ordinary
    text would be blocked off by three characters it could close.
    """
    matched = _FENCE_LINE.match(line)
    if matched is None:
        return (0, 0)
    run = matched.group(1)
    if run.startswith(_FENCE_CHARACTERS[0]):
        return (len(run), 0)
    return (0, len(run))


def _fence_of(closes: tuple[int, int]) -> str:
    """The shortest fence no line closing at these lengths can close.

    One character longer than the run it has to survive, and the cheaper of
    the two characters, with the tie going to the backtick -- which is the
    ordinary one and so the one a quote that carries neither is blocked off
    by.
    """
    widths = tuple(
        max(_SHORTEST_FENCE, closing + 1) for closing in closes
    )
    if widths[0] <= widths[1]:
        return _FENCE_CHARACTERS[0] * widths[0]
    return _FENCE_CHARACTERS[1] * widths[1]


def _walled(lines: list[str], closes: tuple[int, int]) -> str:
    """These lines between one fence they cannot close.

    Joined by the terminators they arrived with rather than by a newline this
    owner picks, so an explanation written with carriage returns reaches the
    thread as its author wrote it. The closing fence needs a line of its own,
    which the last line supplies unless it ended without one.
    """
    fence = _fence_of(closes)
    body = "".join(lines)
    if not body.endswith(_LINE_ENDINGS):
        body = f"{body}\n"
    return f"{fence}\n{body}{fence}"
