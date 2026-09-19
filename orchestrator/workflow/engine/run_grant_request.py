# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `/orchestrator add-agent-runs N` has to say before anything acts on it.

Reading the command and spending on it are two separate questions, and this
owner answers only the first. Nothing here touches a ledger, a park, or a
thread: it turns the words a human wrote into one record that already knows
whether it buys anything, and the owner beside it (`run_grant.py`) decides
what to do about that.

The command is a whole line of its own, and its argument an exact positive
whole number no larger than `MAX_RUNS_PER_COMMAND`, because the number IS the
command: a slip of the keyboard that reads as a thousand runs is not a
decision anybody took. Every other reading buys nothing, and they are all the
same nothing -- separated from a request by the human's own comment, which is
still on the thread right above the answer it earns.

The same grammar answers the drift hash, which is why the bare-command reading
is published beside the rest rather than kept inside. An answered command
hands the SAME tick to the stage the label names, so a hash counting it would
put that handler in front of a body nobody edited and call it changed
requirements -- a developer resumed where a reviewer was owed a round. What is
control is the command ALONE; words beside it are requirements and travel the
drift road that carries them to an agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# The most one command may buy. A bound is what keeps a decision a decision:
# a typo costs at most this many runs, and a human who wants more says so
# again -- which is one more sentence on the record rather than one unbounded
# number nobody reads twice. It is a property of the command rather than of
# the deployment, so it does not move when `MAX_AGENT_RUNS_PER_ISSUE` does and
# it still bounds a request on an issue whose ceiling is off.
MAX_RUNS_PER_COMMAND = 50

# The command, as a whole line of its own. Anchored at both ends so the
# receipts the owner beside this one writes -- which spell the command inside
# a sentence, quoted -- are not read back as requests. The argument is
# captured as whatever was written rather than as a number, because a
# malformed one is a request that owes an answer and not a line nobody saw.
_ADD_RUNS_RE = re.compile(
    r"^[ \t]*/orchestrator[ \t]+add-agent-runs"
    r"(?P<count>[ \t]+[^\r\n]*?)?[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)

# What the argument has to be: digits and nothing else. `int()` would take a
# sign, a surrounding space, and a unicode digit nobody typed on purpose, and
# a command whose number is guessed at is a ceiling nobody chose.
_COUNT_RE = re.compile(r"[0-9]+")

# How many digits a number this command can act on is written in. The bound
# above is the reason it exists, but the length is checked BEFORE the digits
# are converted: `int()` refuses a string past the interpreter's own
# conversion limit by raising, and a request that raises is one nobody is
# answered about -- neither granted nor refused, on a park that goes on
# standing. So a count too long to be inside the bound is turned away as the
# excessive request it is, without being converted at all.
_MAX_COUNT_DIGITS = len(str(MAX_RUNS_PER_COMMAND))


@dataclass(frozen=True)
class _Request:
    """One `add-agent-runs` command, the comment that carried it, and what it
    buys.

    The comment is part of the request because the receipt written for it --
    a grant's or a refusal's -- is scoped to that comment: what a marker has
    to tell apart is one request from the next, and the argument alone cannot,
    since two people asking for the same thing are still two decisions.

    `added` is None for a request nothing can be bought with, which is the
    whole of what "malformed" means here. It is settled where the line is read
    rather than where it is acted on, so both roads the owner beside this one
    takes are handed one record that already knows which of the two it is.

    `consumed` is the last comment of the batch this request was read out of,
    and it is carried rather than looked up again for the same reason: what a
    tick may mark answered is what it READ, and a thread re-read for a
    boundary would hand back comments nobody there has seen.
    """

    asked: str
    comment_id: int
    added: int | None
    consumed: int


def _is_bare_command(issue_comment: Any) -> bool:
    """Whether this comment is the command and nothing else.

    Asked by the drift hash rather than by the owner that acts on a request. A
    command is an operator CONTROL, not a line of requirements: counted as
    content it would shift the hash on the very tick the park comes down, and
    the handler the grant hands the issue to would read a body nobody edited
    as changed requirements -- resuming a developer where a reviewer was owed
    a round.

    Bare is the whole test, for the reason `/orchestrator continue` is held to
    the same one: a comment that carries the command ALONGSIDE guidance is
    guidance, it moves the hash, and the drift road it opens is how those
    words reach the agent that has to act on them.
    """
    written = (getattr(issue_comment, "body", "") or "").strip()
    return _ADD_RUNS_RE.fullmatch(written) is not None


def _requested(comments: list) -> _Request | None:
    """The last `add-agent-runs` command the unread thread carries.

    The last rather than the first, because a batch is read in thread order
    and a human who wrote the command twice meant the second one. Several
    lines in one comment read the same way, so a corrected count below a typo
    is the request rather than the line it corrects.

    What the record carries out of here is the whole batch as well as the
    command: the words a human wrote above or below it are read by the same
    tick, and answering the command is answering the replies to the park. The
    batch ends at the last TRUSTED comment, since that is all this reading is
    handed -- an outsider's is left where it is for the next tick to filter out
    again. Which of those words are replies to the park, rather than input the
    park interrupted, is the consuming owner's question rather than this one.
    """
    latest = None
    for comment in comments:
        for found in _ADD_RUNS_RE.finditer(comment.body or ""):
            latest = ((found.group("count") or "").strip(), comment.id)
    if latest is None:
        return None
    asked, comment_id = latest
    return _Request(
        asked=asked,
        comment_id=comment_id,
        added=_added_runs(asked),
        consumed=max(read.id for read in comments),
    )


def _added_runs(asked: str) -> int | None:
    """How many runs one request buys, where what it asks for buys any.

    None for every other reading, and the same None for all of them: a missing
    count, a word, a sign, a fraction, a zero, and a number past the bound end
    in one place -- a park that stands and a thread that is told what a
    request has to say. What separates them is the human's own comment, which
    is still on the thread right above the receipt.

    The leading zeros go before the length is measured, so `007` is the seven
    somebody wrote and a thousand digits is a number no bound could hold. That
    order is what keeps the count out of `int()` until it is known to be
    short: the interpreter refuses to convert a long enough digit string at
    all, and a request that RAISES is one nobody is answered about -- not
    granted, not refused, on a park that goes on standing.

    A zero falls out of the same step rather than being tested for. Every
    digit of it is a leading one, so what is left of `0` or `000` is nothing
    at all -- which is exactly what a request naming no runs buys.
    """
    if not _COUNT_RE.fullmatch(asked):
        return None
    counted = asked.lstrip("0")
    if not counted or len(counted) > _MAX_COUNT_DIGITS:
        return None
    added = int(counted)
    if added > MAX_RUNS_PER_COMMAND:
        return None
    return added
