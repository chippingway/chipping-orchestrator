# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a park notice quotes of the last message a developer run ended on.

A run that committed and handed over no usable report is parked for a human,
by `report_delivery` (its notice worded by `report_refusal_notices`) and by the
fixing stage's own holds, and the prompt tells a developer that cannot finish
to end on its question: the decision it is waiting on, and the choices it
offered, are what the reply has to answer. So the notice quotes that message,
in the blockquote form every agent output an issue carries is quoted in
(`messages._as_blockquote`), with every line ending made the line feed that
form prefixes: markdown also ends a line on a bare carriage return, and a line
left without its prefix falls out of the quote.

Quoted whole wherever one comment carries it beside the notice's own words and
the marker every comment of ours ends on, since a notice GitHub refuses parks
nothing. Past that ceiling the head goes and the end stays, because the prompt
puts the question last: the longest end that fits once quoted.

Markdown hides text only through raw HTML, and raw HTML always opens on `<`:
an HTML comment opener nothing closes swallows every line after it, the
question and its choices included. So a message carrying `<` is quoted inside
a code fence, where nothing reads as anything but text, and one without it
renders as the developer wrote it. A cut one is always fenced, since the head
the cut drops can hold the opening of a code block whose content the end kept
would then expose.

A fence ends only on a line that is a run of its own character at least as
long, so it is made one longer than every such line it holds, and of whichever
character -- backtick or tilde -- that leaves shorter: a message holding a
long run of one is fenced in the other, rather than spending the room its
question needed on two fences. A cut quote's first line, the one the cut went
through, opens on a mark that says so and leaves it unable to close a fence.
Only the lines the cut kept whole size the fence then, and they only grow as
the end kept lengthens, so the longest end that fits is found by bisection.

A receipt marker inside the message is kept out of the raw comment by escaping
its opening bracket as an HTML entity. Receipts are found by searching raw
comment text, and a comment of ours carrying one would read as the step it
names; escaped, no search reads it, and the developer's words around it are
still quoted -- rendered as written outside code, and as the entity typed
inside a fence or a code span, where markdown reads nothing.
"""
from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence

from orchestrator.github import comments as _github_comments, pinned_state as _pinned_state
from orchestrator.workflow.engine import comments as _comments, messages as _messages

_QUOTED = (
    "\n\nThe developer's last message{how}, with any question it is waiting on "
    "and the choices it offered:\n\n{quoted}"
)

# How the heading names a quote fenced as text, whole and cut.
_QUOTED_AS_TEXT = ", shown as plain text"

_QUOTED_CUT = ", cut to the end of it that fits in this comment and shown as plain text"

# What the first line of a cut quote opens on: the line the cut went through.
_CUT_MARK = "..."

# What every raw HTML construct markdown reads opens on.
_HTML_OPENER = "<"

# The line endings markdown reads beside the line feed.
_CARRIAGE_RETURN = "\r"

_CRLF = "\r\n"

# The receipt prefix with its opening bracket escaped, which no search of raw
# comment text reads as ours.
_ESCAPED_RECEIPT_PREFIX = _github_comments.RECEIPT_MARKER_PREFIX.replace("<", "&lt;", 1)

# The characters a fence is built of, and the shortest fence markdown has.
_FENCE_CHARACTERS = ("`", "~")

_SHORTEST_FENCE = 3


def quoting_the_last_message(render: Callable[[str], str], message: str) -> str:
    """The notice `render` words, with as much of a run's last `message` quoted into it as one comment carries.

    `render` takes the quote, "" included, and answers the whole notice: the
    quote opens on its own blank line, so a notice places it straight after a
    sentence. A run that said nothing gets no quote at all.

    Measured over the body the post sends -- the notice's own words, the
    quote's blockquote prefixes, fences and cut mark, and the comment marker
    appended to it -- so nothing is cut that the comment had room for.
    """
    lines = message.replace(_CRLF, "\n").replace(_CARRIAGE_RETURN, "\n")
    said = lines.strip().replace(_github_comments.RECEIPT_MARKER_PREFIX, _ESCAPED_RECEIPT_PREFIX)
    if not said:
        return render("")
    room = _pinned_state.MAX_PINNED_BODY - len(_comments._with_orch_marker(render("")))
    quoted = _whole_quote(said)
    if len(quoted) <= room:
        return render(quoted)
    return render(_cut_quote_within(said, room))


def _whole_quote(said: str) -> str:
    """The quote of the whole of `said`: as written, or as text where raw HTML could hide part of it."""
    if _HTML_OPENER not in said:
        return _QUOTED.format(how="", quoted=_messages._as_blockquote(said))
    return _QUOTED.format(how=_QUOTED_AS_TEXT, quoted=_fenced(said, said.split("\n")))


def _cut_quote_within(said: str, room: int) -> str:
    """The quote of the longest end of `said` that takes no more than `room`, or "" where none does.

    Every character an end keeps costs at least one, so no end longer than
    the room is asked about; and the cost of an end only grows as it
    lengthens, so the ends that fit are the shortest ones. Their starts are
    asked shortest end first, the empty one among them, which is no quote.
    """
    tail = said[max(0, len(said) - room):]
    starts = range(len(tail), -1, -1)
    fitting = bisect.bisect_right(
        starts, room, key=lambda start: len(_cut_quote(tail[start:])),
    )
    if fitting <= 1:
        return ""
    return _cut_quote(tail[starts[fitting - 1]:])


def _cut_quote(end: str) -> str:
    """The quote of a cut message's `end`, marked as cut and fenced as text.

    The mark opens the line the cut went through, so only the lines after it
    can close a fence, and only they size it.
    """
    return _QUOTED.format(
        how=_QUOTED_CUT, quoted=_fenced(f"{_CUT_MARK}{end}", end.split("\n")[1:]),
    )


def _fenced(text: str, lines: Sequence[str]) -> str:
    """`text` quoted inside the shortest fence of either character that none of `lines` can close."""
    fence = min((_fence_of(character, lines) for character in _FENCE_CHARACTERS), key=len)
    return _messages._as_blockquote(f"{fence}\n{text}\n{fence}")


def _fence_of(character: str, lines: Sequence[str]) -> str:
    """The shortest fence of `character` that none of `lines` can close.

    A line closes a fence only by being a run of the fence character and
    nothing else, surrounding whitespace aside, so only such lines lengthen it.
    """
    runs = (line.strip(" \t") for line in lines)
    longest = max(
        (len(run) for run in runs if run and not run.strip(character)),
        default=0,
    )
    return character * max(_SHORTEST_FENCE, longest + 1)
