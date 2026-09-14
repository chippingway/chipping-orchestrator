# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Durable late-park notices, bounded explanation rendering, and receipt reads.

A notice is owed only while its reason still names the standing park. The
recorded explanation is inserted at delivery time, fenced when it fits and
escaped or visibly cut only when required by the comment budget. A receipt
counts only on this bot's authenticated comment.
"""
from __future__ import annotations

import logging

from orchestrator.github.comments import authored_by_us
from orchestrator.github.pinned_state import MAX_PINNED_BODY, pinned_state_body
from orchestrator.workflow.stages.decomposition import (
    late_notice_fences as _notice_fences,
    late_result_payloads as _late_result_payloads,
    late_run_reading as _late_run_reading,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext, _StagedPark
from orchestrator.workflow.stages.decomposition.late_result_models import UNRECORDED_SPLIT_BLOCKER

log = logging.getLogger("orchestrator.workflow")

# The notice a park recorded here has still to say out loud. Spelled with the
# mode's own prefix because it is this mode's obligation: another stage's park
# is not one this owner may speak for.
PARK_NOTICE = "late_park_notice"

# What a notice writes where it means the explanation the record already
# holds. A sentence that copied that prose instead would put the same agent
# text in the same comment twice, so an explanation the outcome could be
# recorded with would be one its own obligation could not be written beside --
# and the parks these sentences explain are the ones nothing supersedes, so
# what that costs is a human never told at all.
#
# Named rather than searched for: the wording puts it where the explanation
# goes, because a short explanation is a substring of the sentence around it
# and a search would find the wrong one.
#
# Deliberately NOT an HTML comment, which is what every marker this
# orchestrator writes onto a THREAD is. This one is written into the pinned
# comment, and that comment is itself an HTML comment: a sentinel carrying
# `-->` would close it early, and GitHub would render the rest of the payload
# -- the recorded result, the recovery fields, everything after it -- as
# visible issue text. So it is a bracketed token, which JSON carries verbatim
# and HTML has no opinion about.
RECORDED_EXPLANATION = "{{orchestrator-late-explanation}}"

# What OPENS an HTML comment on a thread, and how it is written where the
# quote carrying it is not blocked off. Inside a block that text is shown
# rather than obeyed and nothing is rewritten; outside one it is obeyed, and
# GitHub renders nothing from the opener onwards -- which on this park costs a
# human the tail of the only explanation they will ever be given.
#
# The escape is a backslash, which is one character and the cheapest markdown
# has: what follows the `<` is then an escaped `!` rather than the opener's
# own, so no HTML comment is recognized and the four characters render exactly
# as the agent wrote them. Escaping every `<` instead, or writing the entity
# for it, costs three or more apiece, and an explanation the record can hold
# is enough of them to push the comment past what GitHub accepts.
_COMMENT_OPEN = "<!--"

_ESCAPED_COMMENT_OPEN = r"<\!--"

# What a human is told where no rendering of an explanation fits one comment.
# Nothing this binary records reaches it -- an outcome is held to a budget
# that leaves the room, and blocking a quote off in pieces costs a handful of
# characters even for a quote built to defeat a single fence. What it answers
# is the one failure with no recovery at all: a notice GitHub refuses is
# rebuilt identically on every poll, so the park stands and the human is never
# told anything.
_CUT_QUOTE = "\n\n(cut: no rendering of the whole explanation fits one comment)"

# The one park whose sentence names that record. Spelled here rather than
# imported for the reason `_PARK_REASON` below is: reaching back into the
# owner that stages parks would make this leaf part of the cycle it sits
# under. What it buys is that the substitution is scoped to the sentence this
# owner worded -- every other park's sentence is an agent's or a human's text
# carried verbatim, and one that happens to contain the marker is theirs to
# have written, not this owner's to expand.
_NAMES_THE_EXPLANATION = "late_single_decision"

# The shared park flag this field is the missing half of. Spelled here rather
# than imported for the reason its neighbours spell it: reaching back into the
# owner that stages parks would make this leaf part of the cycle it sits
# under.
_PARK_REASON = "park_reason"

# The consumed-comment watermark a park's own mention ratchets, and only ever
# on a write that landed. That is what makes it the right window to look for
# an undelivered notice in: a sentence whose write failed fell ABOVE the mark
# its post should have moved, while one from an episode that completed sits at
# or below it and cannot answer for a later park carrying the same words.
_LAST_ACTION_COMMENT_ID = "last_action_comment_id"

_REASON = "reason"

_MESSAGE = "message"


def _owed_notice(context: _LateContext) -> _StagedPark | None:
    """The sentence this issue's standing park has still to say, if any.

    Read back as the same staged park the release takes, so a notice owed by
    an earlier tick and one staged by this tick are the same thing to
    everything downstream -- the obligation as it is stored, marker and all.
    Rendering it is the delivering step's own, and asked exactly once there,
    because a sentence expanded twice is not the sentence that was posted.

    Matched against the reason the issue is actually parked for. A notice left
    behind by a park something has since replaced or answered explains a state
    the issue is no longer in, and saying it would tell a human to settle a
    thing that is already settled.
    """
    owed = context.state.get(PARK_NOTICE)
    if not isinstance(owed, dict):
        return None
    reason = owed.get(_REASON)
    if not reason or reason != context.state.get(_PARK_REASON):
        return None
    message = owed.get(_MESSAGE)
    if not isinstance(message, str) or not message:
        return None
    return _StagedPark(message=message, reason=reason)


def _filled(context: _LateContext, owed: _StagedPark) -> str:
    """Put the recorded explanation back into a notice that named it.

    The other half of naming it rather than copying it. Asked ONCE per road a
    sentence takes, and never of what it returns: the two places a rendered
    notice is needed are the post and the thread reading that looks for it,
    and each asks for itself. What is carried between the steps in between --
    on the tick, and on the pinned comment -- is the obligation as it is
    stored, so no road can expand what a previous step already expanded.

    Scoped by the park it explains, because only one park's sentence is worded
    by this orchestrator with a place left in it. Every other park carries an
    agent's or a human's text verbatim -- a categorized question quotes what
    the agent asked -- so one that happens to contain the marker wrote it
    itself, and rewriting it would put words in somebody's mouth and leave the
    posted sentence unfindable on the thread.

    Inside that scope, replacement does not re-scan what it inserts, so one
    pass leaves an explanation's own marker text exactly where the agent wrote
    it; two passes would expand it as though this owner had put it there, and
    the sentence posted and the sentence looked for would stop being the same
    one.

    A record with no explanation on it answers with the same stand-in every
    other reader of a `single` gets. Reaching that is a record something
    dropped out from under a park still owing its sentence, and telling a
    human no reason was recorded is the true answer to it.

    What goes in is FENCED rather than escaped. A thread is markdown, so an
    explanation opening an HTML comment would swallow the rest of the sentence
    and leave a human reading as far as the quote -- told neither what the
    agent said nor what to do about it. Inside a fence that text is shown
    rather than obeyed, and the fence costs the same handful of characters
    however long the quote is, where escaping the openers grows the comment
    per occurrence and an explanation the record can hold is enough of them to
    push it past what GitHub accepts.

    The whole of it goes in, whatever that costs the rendering. An
    explanation that is a long run of BOTH fence characters leaves neither one
    cheap, and no comment could hold the block that would go around it -- so
    that quote goes in unblocked, with its HTML-comment openers escaped. It is
    the block that gives way and never a word of the explanation: this park is
    one nothing supersedes, its sentence is the only thing that will ever say
    what stopped a split, and a piece of a reason reads as the whole of one.

    The escape is only for the unblocked road, and it is what makes that road
    an answer at all. Inside a block an opener is shown rather than obeyed;
    outside one GitHub renders nothing from it onwards, so an explanation that
    defeated the fence AND opened a comment would reach the thread with its
    tail invisible -- present in the body and gone from the page, which is not
    a human being told. Both roads fit because the room the dearer of them
    needs is reserved where the outcome was accepted.

    Nothing else is rewritten. A sentence carrying this orchestrator's own
    pinned-state marker is left as its author wrote it, and what keeps it
    findable afterwards is the reader below.
    """
    if owed.reason != _NAMES_THE_EXPLANATION:
        return owed.message
    if RECORDED_EXPLANATION not in owed.message:
        return owed.message
    recorded = _late_run_reading._recovered_adjudication(
        _late_run_reading._read_late_run(context.state),
    )
    return owed.message.replace(
        RECORDED_EXPLANATION,
        _quoted(recorded.split_blocker_explanation or UNRECORDED_SPLIT_BLOCKER),
    )


def _quoted(explanation: str) -> str:
    """This explanation as a comment can carry it, whole and visible.

    Blocked off where a comment can hold the blocks, because inside one an
    opener is shown rather than obeyed and nothing at all is rewritten. The
    quote built to defeat that -- a long fence line of each character -- is
    answered by blocking it off in pieces rather than by saying less of it.

    Unblocked otherwise, with the HTML-comment openers escaped, since
    unblocked is exactly where an opener is obeyed again: GitHub renders
    nothing from it onwards, so an explanation that reached the thread raw
    would be in the comment body and off the page, which is not a human being
    told.

    Cut only where neither fits, which nothing this binary records can reach:
    the outcome budget leaves the room and the pieces cost a handful of
    characters. It is here because the alternative has no recovery -- a
    comment GitHub refuses is rebuilt identically on every poll, so the park
    stands with its sentence owed and the human is told nothing at all, for
    good. A cut quote says so where it was cut.
    """
    blocked = _notice_fences._quoted_block(explanation)
    if len(blocked) <= _late_session.MAX_QUOTED_BLOCK:
        return blocked
    shown = explanation.replace(_COMMENT_OPEN, _ESCAPED_COMMENT_OPEN)
    if len(shown) <= _late_session.MAX_QUOTED_BLOCK:
        return shown
    log.error(
        "no rendering of a %d-character split-blocker explanation fits one "
        "comment; cutting the quote so the park's sentence can be said at all",
        len(explanation),
    )
    room = _late_session.MAX_QUOTED_BLOCK - len(_CUT_QUOTE)
    return shown[:room] + _CUT_QUOTE


def _owe_notice(context: _LateContext, staged: _StagedPark) -> None:
    """Record this park's sentence as one that has still to be said.

    Staged into memory only, like every other field this mode writes: what
    makes it durable is the write the park itself rides out on, which is what
    keeps the obligation and the park it explains in one write rather than
    two.

    A notice the pinned comment cannot hold is refused, and so is whatever it
    replaces -- the park that owed the older sentence is gone, so keeping it
    would announce the wrong one. What is lost is the retry, not the park and
    not this tick's own attempt to post.

    Whether it fits is measured on the whole comment the write would produce,
    because that comment is shared and what is already in it counts. What it
    is measured beside is the record WITHOUT any obligation already on it,
    since a notice replaces one rather than joining it. A notice that NAMES
    the recorded explanation is measured at the size it is stored at, which is
    this owner's own wording, so no agent's prose can put it past that.

    The ceiling is `MAX_NOTICE_COMMENT`, which is the whole of what a recorded
    outcome may take plus the room reserved BESIDE it for the sentence the
    park it earns owes -- beside rather than inside, since measuring a notice
    against the outcome's own budget would charge it twice.

    A record on a live issue can cost more than that budget without ever
    having broken it, in two ways that are the same way: one an older binary
    wrote was held to the whole outcome budget and reserved nothing out of it,
    and one written before the payload escaped the wrapper's own terminator
    (`github.pinned_state`) renders five characters longer per `-->` today
    than on the tick that measured it -- an agent's explanation and a
    preserved pull-request body both carry those. Neither is anything the
    sentence did, and neither is anything a later tick can undo: the record is
    durable, and every write of this issue carries it. Refused for either, a
    park nothing supersedes would drop the obligation its retry depends on,
    and the human would never be told what their unpublished candidate is
    waiting on. So the reserve is granted on top of what the record actually
    costs, and the one hard bound is the size a write really fails at: a
    comment longer than GitHub accepts is one that cannot be written, and the
    write it would take down is the park's.
    """
    record = {
        key: held
        for key, held in context.state.data.items()
        if key != PARK_NOTICE
    }
    owed = {_REASON: staged.reason, _MESSAGE: staged.message}
    ceiling = min(
        max(
            _late_session.MAX_NOTICE_COMMENT,
            len(pinned_state_body(record)) + _late_session.MAX_NOTICE_BODY,
        ),
        MAX_PINNED_BODY,
    )
    if not _late_result_payloads._fits_the_comment({**record, PARK_NOTICE: owed}, ceiling):
        log.error(
            "issue=#%d the notice for park %s does not fit the pinned "
            "comment; it will be posted once and never retried",
            context.issue.number, staged.reason,
        )
        _notice_settled(context)
        return
    context.state.set(PARK_NOTICE, owed)


def _notice_settled(context: _LateContext) -> None:
    """Drop the obligation, however it ended.

    One name for both endings, because the field records an obligation rather
    than an event: a sentence posted to the thread and a park retired or
    answered before anybody had to read it leave exactly nothing owed.
    """
    context.state.data.pop(PARK_NOTICE, None)


def _delivered_id(context: _LateContext, owed: _StagedPark) -> int | None:
    """The id of this notice's own comment on the thread, if it is there.

    The receipt a park notice has, since the post and the write that records
    it are two operations: a write that failed after a post that landed leaves
    pinned state claiming the opposite of what the issue holds, and the issue
    is the one of the two that cannot be wrong about what was said.

    The whole comment is matched rather than a marker, because a park notice
    carries none of its own: the sentence IS the identity, and it is one this
    mode built rather than anything a reader can shorten. The mention prefixed
    to it is not required to match, so the same reconciliation answers for a
    notice however the shared park decorated it.

    Taken from the OBLIGATION as it is stored, and rendered here: what is on
    the thread is a sentence with whatever it names put back, and this is the
    one place on this road that puts it back. A caller that rendered it first
    would have this expand it a second time, and an explanation naming the
    marker itself would then stop matching the comment it was posted as.

    The thread is read with the pinned comment named by its IDENTITY rather
    than found by the marker in its body. A notice quoting an agent who wrote
    that marker -- an explanation about this orchestrator's own state comment
    -- reads as a state comment to the body test, so the one comment this is
    looking for would be the one comment it could not see, and the sentence
    would be said again on every tick after the write recording it was lost.
    Escaping the marker out of the sentence would answer that too, and it is
    the wrong answer: it grows the comment per occurrence, and an explanation
    the record can hold is one such a rewrite can push past what GitHub
    accepts -- a notice no tick could deliver at all.

    And the receipt has to be OURS. That the sentence is its own identity is
    exactly what makes the author load-bearing: it is plain text on a public
    thread, so anybody can paste it back, and read from anybody it would
    discharge an obligation nobody discharged. The park would stand with its
    notice marked said, the watermark would be dragged past whatever else an
    outsider had written under it, and the human the park was taken for would
    never be told -- on this tick and on every tick after it, since nothing
    supersedes a park like the spent-budget one. So the author goes through
    the same owner every other receipt this repository reads off a thread does
    (`github.comments.authored_by_us`), and a client with no authenticated
    login of its own to compare against falls back to the text alone exactly
    as those do.

    The highest match is the one reported, so what the watermark is repaired to
    is the last thing said rather than the first.

    A read that could not be taken answers None, which is the safe direction:
    the notice stays owed and is said again, which costs one repeated comment
    and never a silence.
    """
    try:
        thread = context.gh.comments_after(
            context.issue,
            context.state.get(_LAST_ACTION_COMMENT_ID),
            state_comment_id=context.state.comment_id,
        )
    except Exception:
        log.exception(
            "issue=#%d could not be read for a park notice already posted; "
            "leaving it owed rather than assuming it was said",
            context.issue.number,
        )
        return None
    bot_login = getattr(context.gh, "_bot_login", None)
    delivered = _filled(context, owed)
    said = [
        issue_comment.id
        for issue_comment in thread
        if delivered in (issue_comment.body or "")
        and authored_by_us(issue_comment, bot_login=bot_login)
    ]
    return max(said) if said else None
