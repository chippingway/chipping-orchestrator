# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a park notice quotes of the last message a developer run ended on.

A run that committed and handed over no usable report is parked for a human,
by `report_delivery` (its notice worded by `report_refusal_notices`) and by the
fixing stage's own holds, and the prompt tells
a developer that cannot finish to end on its question: the decision it is
waiting on, and the choices it offered, are what the reply has to answer. So
the notice quotes that message, in the blockquote form every agent output an
issue carries is quoted in (`messages._as_blockquote`).

Quoted whole wherever one comment carries it beside the notice's own words and
the marker every comment of ours ends on, since a notice GitHub refuses parks
nothing. Past that ceiling the head goes and the end stays, because the prompt
puts the question last -- the longest end whose QUOTED length fits, counted
character by character, since a line break spends its blockquote prefix too.

A whole message renders as the developer wrote it. A cut one is fenced: the
head the cut drops can hold the opening of a code block, and the end kept
would then expose what that block protected -- an HTML comment opener above
all, which swallows every line after it, the question and its choices
included. Inside a fence no line of the message can close, nothing of it is
read as anything but text.

A receipt marker inside the message is kept out of the raw comment by escaping
its opening bracket as an HTML entity. Receipts are found by searching raw
comment text, and a comment of ours carrying one would read as the step it
names; escaped, no search reads it, and the developer's words around it are
still quoted.
"""
from __future__ import annotations

import itertools
from collections.abc import Callable

from orchestrator.github import comments as _github_comments, pinned_state as _pinned_state
from orchestrator.workflow.engine import comments as _comments, messages as _messages

_QUOTED = (
    "\n\nThe developer's last message{cut}, with any question it is waiting on "
    "and the choices it offered:\n\n{quoted}"
)

_QUOTED_CUT = (
    ", cut to the end of it that fits in this comment and shown as plain text"
)

# The blockquote prefix a quote's first line opens on.
_QUOTE_PREFIX = _messages._as_blockquote("")

# What one line break of the message spends once quoted: the break and the
# blockquote prefix the next line opens on. Every other character spends one.
_QUOTED_LINE_BREAK = len(_messages._as_blockquote("\n")) - len(_QUOTE_PREFIX)

# The receipt prefix with its opening bracket escaped: what GitHub renders as
# the developer wrote it outside code (inside code the entity shows as typed),
# and what no search of raw comment text reads as ours.
_ESCAPED_RECEIPT_PREFIX = _github_comments.RECEIPT_MARKER_PREFIX.replace("<", "&lt;", 1)

# The character a cut quote is fenced with, and the shortest fence markdown
# has. A fence ends only on a line that is a run of its own character at least
# as long, so it is made one longer than every such line the quote carries.
_FENCE_CHARACTER = "`"

_SHORTEST_FENCE = 3


def quoting_the_last_message(render: Callable[[str], str], message: str) -> str:
    """The notice `render` words, with as much of a run's last `message` quoted into it as one comment carries.

    `render` takes the quote, "" included, and answers the whole notice: the
    quote opens on its own blank line, so a notice places it straight after a
    sentence. A run that said nothing gets no quote at all.

    Measured over the body the post sends -- the notice's own words, the
    quote's blockquote prefixes and fences, and the comment marker appended
    to it -- so nothing is cut that the comment had room for. The fence a cut
    quote needs depends on the end it keeps, so the end is chosen twice: under
    the shortest fence, then under the fence that end needs. The second end
    is part of the first, so no line of it can close that fence either.
    """
    said = message.strip().replace(_github_comments.RECEIPT_MARKER_PREFIX, _ESCAPED_RECEIPT_PREFIX)
    if not said:
        return render("")
    room = _pinned_state.MAX_PINNED_BODY - len(_comments._with_orch_marker(render("")))
    quoted = _QUOTED.format(cut="", quoted=_messages._as_blockquote(said))
    if len(quoted) <= room:
        return render(quoted)
    fence = _fence_for(_end_within(said, room, _FENCE_CHARACTER * _SHORTEST_FENCE))
    kept = _end_within(said, room, fence)
    return render(_cut_quote(kept, fence) if kept else "")


def _end_within(said: str, room: int, fence: str) -> str:
    """The longest end of `said` whose cut quote, inside `fence`, takes no more than `room`.

    Counted from the last character back, each at what it costs once quoted.
    """
    spent = itertools.accumulate(
        _QUOTED_LINE_BREAK if character == "\n" else 1 for character in reversed(said)
    )
    budget = room - len(_cut_quote("", fence))
    kept = sum(1 for total in spent if total <= budget)
    return said[len(said) - kept:]


def _fence_for(text: str) -> str:
    """The shortest fence no line of `text` can close.

    A line closes a fence only by being a run of the fence character and
    nothing else, surrounding whitespace aside, so only such lines lengthen it.
    """
    runs = (line.strip(" \t") for line in text.splitlines())
    longest = max(
        (len(run) for run in runs if run and not run.strip(_FENCE_CHARACTER)),
        default=0,
    )
    return _FENCE_CHARACTER * max(_SHORTEST_FENCE, longest + 1)


def _cut_quote(kept: str, fence: str) -> str:
    """The quote of a cut message's `kept` end, fenced so nothing in it reads as markdown."""
    return _QUOTED.format(
        cut=_QUOTED_CUT, quoted=_messages._as_blockquote(f"{fence}\n{kept}\n{fence}"),
    )
