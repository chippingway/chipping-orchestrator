# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Recorded and rendered unsplit explanations at quoting and pinned-state limits."""
from __future__ import annotations

from orchestrator.github.pinned_state import (
    MAX_PINNED_BODY,
    PINNED_STATE_MARKER,
    pinned_state_body,
)
from orchestrator.workflow.stages.decomposition import (
    late_notice as _late_notice,
    late_session as _late_session,
)
from tests.workflow.stages.decomposition.late_reply_support import late_block
from tests.workflow.stages.decomposition.late_run_support import agent_reply
from tests.workflow.stages.decomposition.late_test_support import CANDIDATE_SHA, KEYS, generation_state, late_generation

# What separates the lines of a quote, and so what makes a run of fence
# characters a LINE that could close a block rather than a run inside one.
_LINE_BREAK = "\n"

# And how a JSON reply spells one, so a fixture can carry the fence LINES a
# quote is built out of.
_BACKSLASH = "\N{REVERSE SOLIDUS}"

_ESCAPED_LINE_BREAK = f"{_BACKSLASH}n"


def _single_reply(blocker: str):
    """One `single` reply carrying this explanation, line breaks and all.

    The reply is JSON, so a line break in an explanation is written as its
    escape -- which is what lets a fixture carry the fence LINES that are the
    only thing able to close a block.
    """
    written = blocker.replace(_BACKSLASH, _BACKSLASH * 2).replace(
        _LINE_BREAK, _ESCAPED_LINE_BREAK,
    )
    return agent_reply(late_block(
        '{"decision": "single", "rationale": "one coherent change",'
        f' "split_blocker": "{written}"}}'
    ))


# An explanation that writes the very marker the obligation names it by. The
# agent's own text, so it survives to the thread exactly as written -- and the
# sentence looked for there afterwards has to be the one that was posted.
_MARKER_BLOCKER = f"alpha {_late_notice.RECORDED_EXPLANATION} omega"

_MARKER_RUN = _single_reply(_MARKER_BLOCKER)

# A question whose own sentence writes the marker. Nothing this orchestrator
# worded, so the announcement carries it exactly as the agent asked it.
_QUESTION_MARKER_RUN = agent_reply(late_block(
    '{"decision": "question", "category": "scope_ambiguous",'
    f' "question": "which half {_late_notice.RECORDED_EXPLANATION} of it?"}}'
))

# What this issue's pinned comment holds besides the explanation -- the
# generation, the run identity, the watermarks -- with room to grow. Sized
# generously and guarded by the record actually landing: a fixture that
# outgrew it would refuse the outcome and fail loudly rather than quietly
# testing a comfortable case.
_ROOM_TO_SPARE = 2048

# An explanation recorded within a few hundred bytes of everything an outcome
# may take, so the room its own notice needs is the room the record left. A
# notice carrying a copy of it would not fit beside it; one naming it does.
_NEAR_LIMIT_BLOCKER = "b" * (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE)

_NEAR_LIMIT_RUN = _single_reply(_NEAR_LIMIT_BLOCKER)

# An explanation that opens this orchestrator's own pinned-state comment, over
# and over, at the length the record can just hold. Both halves matter: the
# marker is what the body test would hide the delivered notice behind, and the
# length is what any per-marker rewrite would push past what GitHub accepts.
_STATE_MARKER_BLOCKER = " ".join(
    PINNED_STATE_MARKER
    for _packed in range(
        (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE)
        // (len(PINNED_STATE_MARKER) + 1)
    )
)

_STATE_MARKER_RUN = _single_reply(_STATE_MARKER_BLOCKER)

# What ends the HTML comment the pinned state is written as. A sentence stored
# inside it that carried one would close it early.
_COMMENT_CLOSE = "-->"

# What OPENS one on a thread, and the fence that keeps a quote from being read
# as opening anything. The shortest fence is what an explanation carrying no
# backticks of its own is blocked off by.
_HTML_OPEN = "<!--"


_FENCE = "\n```\n"

_TILDE_FENCE = "\n~~~\n"

# An explanation carrying a fence LINE of each kind, with an opener behind
# them. A line that is a run and nothing else is the only thing that can close
# a block, so at the shortest fence this quote would close its own -- and two
# blocks cost more here than one fence a character wider, so the wider one is
# what it gets.
_FENCED_BLOCKER = "```\n~~~\nand <!-- after it"

_FENCED_RUN = _single_reply(_FENCED_BLOCKER)

_LONGER_FENCE = "\n````\n"

# The two shortest fences, named so a case can say which one blocked a quote
# off -- and so which one a quote of its own could have closed.
_SHORTEST_BACKTICK_FENCE = "```\n"

_SHORTEST_TILDE_FENCE = "~~~\n"

# A line of backticks as long as the record can hold. Blocked off by backticks
# it would be fenced by a longer run at both ends, so the block comes to three
# times the quote; blocked off by tildes it costs three characters at each end
# and the explanation reaches the thread whole.
_BACKTICK_BLOCKER = "`" * (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE)

_BACKTICK_RUN_REPLY = _single_reply(_BACKTICK_BLOCKER)

# The adversarial explanation: a long line of EACH fence character, so either
# one could close a block holding both and no single fence answers it under
# twice the quote. What answers it is blocking the quote off in PIECES.
_HALF_RUN = (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE) // 2

_BOTH_RUNS_BLOCKER = _LINE_BREAK.join(("`" * _HALF_RUN, "~" * _HALF_RUN))

_BOTH_RUNS_REPLY = _single_reply(_BOTH_RUNS_BLOCKER)

# And the two together, which is the case the reviewer's own reproduction is:
# a long fence line of each character AND the opener that makes GitHub render
# nothing from itself onwards wherever a block does not hold it. What a human
# has to still be able to read is everything past that opener.
_QUARTER_RUN = (_late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE) // 4

_QUOTED_TAIL = "and that is what stopped the split"


def _runs_and_openers(room: int) -> str:
    """A line of each fence character, then openers, then the tail.

    Sized to the room a record leaves, so the same shape can stand for a fresh
    outcome and for one an older binary wrote at its own ceiling.
    """
    run = room // 4
    spent = 2 * run + 2 + len(_QUOTED_TAIL)
    openers = _HTML_OPEN * ((room - spent) // len(_HTML_OPEN))
    return _LINE_BREAK.join((
        "`" * run, "~" * run, f"{openers}{_QUOTED_TAIL}",
    ))


_RUNS_AND_OPENERS_BLOCKER = _runs_and_openers(
    _late_session.MAX_RECORDED_BODY - _ROOM_TO_SPARE,
)

_RUNS_AND_OPENERS_REPLY = _single_reply(_RUNS_AND_OPENERS_BLOCKER)

# An explanation no block can hold: one fence short of everything a quote may
# take, so the block around it would not fit -- and carrying an opener, so the
# unblocked road it falls to has to escape that.
_UNBLOCKABLE_BLOCKER = "{padded}{opener}".format(
    padded="b" * (_late_session.MAX_QUOTED_BLOCK - 2 * len(_HTML_OPEN)),
    opener=_HTML_OPEN,
)

# What ends a line on the machine an explanation was written on. Markdown
# ends one on a carriage return as readily as on a newline, so a fence line
# arriving under either is a line that can close a block -- and one read as
# ordinary text would be blocked off by three characters it carries, with the
# opener behind it hiding the rest from a human.
_LINE_ENDINGS = ("\r\n", "\r", "\n")

_HIDDEN_TAIL = "the tail an opener would hide"


def _fenced_and_opened(ending: str) -> str:
    """An explanation whose own fence line rides on this line ending."""
    return ending.join(("before it", "```", f"{_HTML_OPEN} {_HIDDEN_TAIL}"))


# And the one nothing renders whole: every character an opener, at the length
# a quote may take, so blocking it off and escaping it both overflow. Nothing
# this binary records can be it, since an outcome is held to a smaller budget
# than a quote is -- what it stands for is the guarantee that no notice is
# ever one GitHub refuses and every poll rebuilds.
_UNSAYABLE_BLOCKER = _HTML_OPEN * (
    _late_session.MAX_QUOTED_BLOCK // len(_HTML_OPEN)
)

# The last thing the sentence tells a human, and so the thing an explanation
# swallowing the rest of it would cost them.
_REPLY_INSTRUCTION = "Reply with the change to make"

# A recorded `single` an older binary left: written when the whole outcome
# budget was the ceiling, so it sits past the reserve this one keeps and could
# never have paid it. The park it earns today still owes its sentence.
_LEGACY_ROOM_LEFT = 256

# What escaping the wrapper's own terminator costs the payload, measured
# rather than spelled: the record is the same either way and only its
# rendering grew, which is exactly the difference a notice may not be charged
# for.
_ESCAPE_COST = (
    len(pinned_state_body({KEYS.split_blocker: _COMMENT_CLOSE}))
    - len(pinned_state_body({KEYS.split_blocker: "abc"}))
)

# And so how many terminators a record has to carry for re-serializing it to
# cost more than the whole reserve its park's sentence is measured into.
_TERMINATORS = _late_session.MAX_NOTICE_BODY // _ESCAPE_COST + 1

# How many for escaping them to cost more than the comment GitHub takes at
# all: the headroom the outcome budget leaves under that limit, and one
# escape more. Past it the payload goes as it was stored, since a write
# refused for a RENDERING would take the park and the sentence it owes down
# with it.
_UNESCAPABLE_TERMINATORS = (
    (MAX_PINNED_BODY - _late_session.MAX_RECORDED_BODY) // _ESCAPE_COST + 1
)


def _last_said(github) -> str:
    """The body of the last comment this tick posted to the thread."""
    return github.posted_comments[-1][1]


def _legacy_record(terminators: int = 0, room_left: int = _LEGACY_ROOM_LEFT) -> dict:
    """The pinned comment a `single` recorded before the reserve existed.

    Sized against the comment as it was written THEN, so the case sits in the
    band between the two ceilings rather than near it: past what a `single`
    may be recorded with now, and inside what one could be recorded with then.

    `terminators` is how many of the wrapper's own terminators the record
    carries. They cost nothing in the rendering that accepted it and five
    characters each in today's, since the payload escapes them now -- a
    migration the sentence the park owes did not cause and cannot undo.
    """
    recorded = {
        **generation_state(late_generation()),
        KEYS.verdict: "single",
        KEYS.run_cycle_id: late_generation().cycle_id,
        KEYS.run_generation: late_generation().generation,
        KEYS.source_sha: CANDIDATE_SHA,
    }
    empty = len(pinned_state_body({**recorded, KEYS.split_blocker: ""}))
    padding = (
        _late_session.MAX_RECORDED_BODY - room_left - empty
        - len(_COMMENT_CLOSE) * terminators
    )
    return {
        **recorded,
        KEYS.split_blocker: _COMMENT_CLOSE * terminators + "b" * padding,
    }


# The same shape as `_RUNS_AND_OPENERS_BLOCKER` at the ceiling a record could
# actually have been written at, which is what an older binary's `single`
# left on a live issue.
_OLD_LIMIT_BLOCKER = _runs_and_openers(
    len(_legacy_record()[KEYS.split_blocker]),
)
