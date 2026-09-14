# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Durable unauthorized-exemption parks, scoped notices, and reply consumption.

A notice receipt is recorded before its post and cleared after delivery.
The standing park must still name this candidate, and reply consumption uses
the command reading's watermark instead of swallowing a later human reply.
"""
from __future__ import annotations

from types import MappingProxyType

from orchestrator.workflow.late_split import (
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_command as _command,
    late_records as _records,
    state as _state,
)

# The receipt each sentence this owner writes is stamped with, scoped to the
# one thing it is the answer to: the candidate a park was taken over, and the
# reply a refusal was written for. HTML comments, so both are invisible in the
# rendered thread.
#
# Each is what keeps a second poll from saying the same thing to the same
# people twice, because neither the sentence nor its consequence can be made
# one operation with the write that records it. Recorded BEFORE the sentence
# carrying it goes out, so the record says a sentence is outstanding and the
# thread says whether it landed: a receipt the thread carries is a sentence
# that was said, and one it carries nowhere is one still owed.
#
# Both halves of the thread's answer are asked -- the receipt and the author
# -- and that is the safe direction for SILENCING a sentence and the wrong one
# for claiming a comment. These strings are public text, deterministic from an
# issue and a commit, and recording one publishes it, since the record is
# itself a comment; the login beside it may be the operator's own. So read as
# proof of authorship a retraction written under a quoted receipt would be
# taken for one of ours and deleted from the reading -- publishing the
# authorization beneath it on consent withdrawn. Silencing a sentence costs a
# poll; claiming a comment costs whatever its author said. Attribution is
# `late_recovery`'s, on the one thing that can bear it: a secret it commits to
# by DIGEST before the seam is entered, stamped on every sentence that call
# posts -- these among them, since both are worded inside it.
_RECEIPTS = MappingProxyType({
    "parked": (
        "<!--orchestrator-unauthorized-exemption-parked:"
        "issue={issue}:candidate={scope}-->"
    ),
    "refused": (
        "<!--orchestrator-unauthorized-exemption-refused:"
        "issue={issue}:read={scope}-->"
    ),
})


def _receipt(gate: _records._Gate, said: str, scope) -> str:
    """The receipt one sentence of ours is stamped with, scoped to its subject."""
    return _RECEIPTS[said].format(issue=gate.issue.number, scope=scope)


def _recorded_as_said(gate: _records._Gate) -> None:
    """Catch the record up with a thread that already carries our sentence.

    An outstanding receipt says a tick died between recording a sentence and
    recording having said it. Reaching here is the thread having answered
    which side of the post that was -- everything this owner owes has been
    said -- so the record is brought into line with it.

    Left standing instead, the receipt would have every later poll of a park
    nobody has answered read the whole thread again to reach the same
    conclusion, and would go on saying something is outstanding when nothing
    is. Dropping it costs one write, once.

    Nothing is owed at this point whichever sentence the receipt was for. The
    park's own notice would have taken the announcing road rather than this
    one, and the refusal's at-most-once guard asks the thread for its own
    scoped receipt rather than this field.
    """
    if gate.state.get(_state._HELD_RECEIPT) is None:
        return
    gate.state.set(_state._HELD_RECEIPT, None)
    gate.gh.write_pinned_state(gate.issue, gate.state)


def _owes_the_notice(gate: _records._Gate, receipt: str) -> bool:
    """Whether a sentence this park recorded is still owed to the thread.

    Two questions, and the record answers only the first. A park carrying no
    receipt has nothing outstanding -- the write past the post dropped it --
    so the ordinary quiet poll is answered without a request. A park still
    carrying one is a tick that died somewhere between recording the sentence
    and recording having said it, and WHICH side of the post it died on is a
    question only the thread can answer.

    So the thread is asked, on the same terms and for the same reason the
    refusal beside this one asks it: the receipt AND the author, which is the
    safe direction to fail in for a question about SILENCING a sentence.
    Read from anybody, a receipt somebody pasted would silence a notice a
    human is owed; read this way, the worst a reviewer sharing this token can
    do by quoting our notice back is cost a poll.

    What may never be built on THIS evidence is the opposite claim -- that
    some comment on the thread is OURS. The receipt is deterministic from the
    issue and the candidate, and recording it publishes it: the record is
    itself a comment, so the string is readable before the sentence it names
    exists, by the operator whose consent this park collects and from a login
    they may share with us. Claimed on that basis, a retraction they wrote
    under it would be deleted from every later reading and the authorization
    beneath it would become the last word and publish on consent withdrawn.

    Nothing here writes the id ledger that says a comment is ours. The one
    attribution `late_recovery` does make rests on a SECRET, minted per
    handoff into the publication seam and recorded there by its digest alone
    -- which is the claim this receipt cannot support and is not asked for.
    Every sentence this owner words goes out from inside that seam call, so
    the secret is on them too, beside the receipt this read is about.
    """
    if gate.state.get(_state._HELD_RECEIPT) != receipt:
        return False
    return not _command._already_said(gate, receipt)


def _held(gate: _records._Gate, receipt: str) -> None:
    """Make this park, and the receipt it is about to say, durable first.

    Both halves go down in one write and both are the same precaution. The
    park is what a restarted tick reads to know somebody is already waiting
    behind this candidate; the receipt is what tells a later poll that the
    sentence saying so never got out, and it can only do that if it was
    written down before the comment carrying it existed.

    The park's flags are set here rather than left to the guard below, because
    the guard sets them AFTER it posts -- which is the window this write
    exists to close.
    """
    gate.state.set(_state._AWAITING_HUMAN, True)
    gate.state.set(_state._PARK_REASON, _command.PARK_UNAUTHORIZED_EXEMPTION)
    gate.state.set(_state._HELD_RECEIPT, receipt)
    gate.gh.write_pinned_state(gate.issue, gate.state)


def _stands_over(
    gate: _records._Gate, generation: LateGeneration,
) -> bool:
    """Whether this park is already up, over this very candidate.

    Both halves of the park are required. The flag and the reason say somebody
    is waiting behind this question rather than behind a timeout, a dirty
    tree, or a reading nobody could take; the recorded candidate says they are
    waiting behind THIS one.

    Read off the durable record, which the freeze ahead of this call has
    already written the pair onto -- so what is compared is the commit the
    park is about rather than a count nothing persists. A park a resumed
    developer's fresh commit has moved past never reaches this owner at all:
    the road in is an exemption naming the candidate in hand, and a hold
    routes the issue to the adjudication, which clears whatever park it
    supersedes on the way.
    """
    if gate.state.get(_state._PARK_REASON) != _command.PARK_UNAUTHORIZED_EXEMPTION:
        return False
    if not gate.state.get(_state._AWAITING_HUMAN):
        return False
    recorded = _late_state.read_late_generation(gate.state)
    return recorded.candidate_sha == generation.candidate_sha


def _consumed(
    gate: _records._Gate, answer: _command._Answer, said: int = 0,
) -> None:
    """Record what this tick read as read, and its own answer with it.

    Staged rather than written, so it lands with whatever else the caller is
    recording or not at all: a watermark moved without the answer beside it
    would drop a command nobody acted on.

    It starts at the furthest comment the READING got to, which is what the
    reader hands back rather than a fresh look at the thread: a tick that
    consumed past whatever the tip has become since would swallow a reply
    posted in the meantime -- a retraction of the very command being acted on
    is the case that matters -- unread, unanswered and gone for good. Consumed
    to what was read, that reply is still there for the next poll, which is
    the most a reading taken before it can honestly offer.

    Then it reaches the answer this tick POSTED, and `read_through` beside the
    reading decides how far that is: over our own comments and no further,
    since a sentence of ours left unconsumed is read on the next poll as
    guidance nobody wrote, while a watermark jumped straight to its id would
    swallow the corrected command an operator posted in the same window.
    """
    gate.state.set(
        _state._LAST_ACTION_COMMENT_ID, answer.read_through(gate, said),
    )
