# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The receipt a park over a manifest correction ends on, and the park a later tick owes without saying it twice.

Every park taken over an attempt -- the correction's own answer parked, or an
attempt armed with no launch granted and given up behind the ordinary park --
ends on a hidden receipt naming the issue and the source invocation's random
nonce (`receipted`), which no agent answer can know to forge. Its notice is
held on the record before it is posted (`owing`), and the park is written only
over the comment the tick last synced with (`recorded`), so a field a human or
another road wrote meanwhile is never put back. Each of those parks lands
before the attempt is resolved (`correction_settlement`), and a park whose
write did not land leaves its notice on the thread with nothing recording it.
The tick that finds that attempt owed a park it does not stand on
(`correction_reconcile`) asks the thread past the reply boundary for the
receipt first (`parks_once`), saying the notice the record still holds where
one was about to be posted when a tick ended (`owed`), so a post that never
landed is said in its own words -- the latest error and rejected answer --
rather than in what the attempt alone recalls: where a comment of ours carries
the receipt, the park is recorded over that notice and nothing is said again;
otherwise the notice is posted, receipt and all. A notice held on the record is
posted on its own tick only where the comment and the issue, read afresh behind
the write holding it, still stand; otherwise it stays owed for a later tick's
park, or is dropped once a move or a close spends or retires its attempt with
no park left to say it (`correction_settlement.discards`). Either way the park
is bounded wherever a reply boundary stands: it records the thread read through
our own comments and no further, so a reply written while the correction was
out -- below a notice that landed after it -- stays past the boundary for the
resume to deliver. A thread nobody could read says nothing and records nothing,
and the next tick asks again; so does a pinned comment or an issue that no
longer stands as the rejected run left them, read afresh behind the thread's
read and ahead of any post or write (`correction_live.answers`) -- a hold or an
unread reading holds the tick, and a moved context, owner, or requirements is
left to the road that answers it, so no notice is posted, or park written, over
it.
"""
from __future__ import annotations

import logging
from functools import partial

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    park_watermarks as _park_watermarks,
    record_admission as _record_admission,
)
from orchestrator.workflow.stages.decomposition import (
    correction_live as _live,
    correction_records as _records,
    correction_room as _room,
    ready_readings as _ready_readings,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_RECEIPT = "<!--orchestrator-decomposer-correction:issue={issue}:source={nonce}-->"

_OWED = _state._DECOMPOSER_CORRECTION_NOTICE

# The members of an owed notice: the source it is the park of, and its words.
_SOURCE = "source"
_MESSAGE = "message"


def receipted(message: str, attempt: _records.CorrectionAttempt | None) -> str:
    """`message` ending on `attempt`'s receipt, or as it is where the park is over no attempt."""
    if attempt is None:
        return message
    return f"{message}\n\n{_receipt(attempt)}"


def owing(
    gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt | None, message: str,
) -> str | None:
    """The notice the park over `attempt` posts, held on the record first; None where it may not be posted now.

    `message` is written ahead of the post, only over the comment the tick last
    synced with (`record_admission.strictly_written`) -- whole, or as much of
    its start as the comment has room for, its opening line naming the latest
    error the last of it cut (`correction_room.notice_held`) -- and dropped
    from `state` once held, for the write recording the park to land without
    it. The post is `message` whole where one comment can carry it, and the
    words held otherwise -- measured as posted, the comment marker included --
    so a notice longer than GitHub takes is never sent to be refused. A post
    that raises leaves it on the record, which the next tick's park is said
    from (`owed`) -- the latest error and rejected answer included -- under the
    same receipt and boundary. Behind that write the pinned comment and then
    the issue are read afresh (`correction_live.answers`): a hold, a move, or
    an unread reading landing while it was out -- or the write itself leaving
    the caller's state withheld, unconfirmed or refused over a comment moved
    since -- posts nothing and records no park, the notice left owed, where it
    landed, for the next tick's park to say once the issue stands
    (`correction_reconcile.recovers_park`). A park over no attempt posts as it
    always has.
    """
    if attempt is None:
        return message
    held = {_SOURCE: attempt.source.invocation.nonce, _MESSAGE: message}
    held[_MESSAGE] = _room.notice_held(state.state_data, _OWED, held, _MESSAGE)
    state.set(_OWED, held)
    if not _record_admission.strictly_written(gh, issue, state):
        log.warning("issue=#%d its manifest correction's park could not be held before its notice", issue.number)
    live = _live.answers(gh, issue, state, attempt.source)
    if live is not _live.Live.STANDS or state.withheld:
        log.info("issue=#%d reads %s behind its correction's held notice; parking nothing", issue.number, live.value)
        return None
    state.state_data.pop(_OWED, None)
    posted = receipted(message, attempt)
    rendered = _comments._with_orch_marker(posted)
    return posted if len(rendered) <= MAX_PINNED_BODY else receipted(held[_MESSAGE], attempt)


def recorded(
    gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt | None,
) -> bool:
    """Write the park `state` stages; whether it landed, so the attempt it stands over may be resolved behind it.

    A park over an attempt lands only over the comment the tick last synced
    with (`record_admission.strictly_written`) -- the one its notice was held
    on, or the one read afresh ahead of its post -- and only while the issue,
    read afresh right before the edit leaves, still stands
    (`correction_live.resolves`), so a field a human or another road wrote
    meanwhile is never put back, a hold, a close, a relabel, or an edit landing
    after the notice went out parks nothing over it, and an attempt is never
    resolved behind a park that did not land: the notice it posted carries the
    receipt a later tick records the park over. A park over no attempt is
    written as it always has been.
    """
    if attempt is None:
        gh.write_pinned_state(issue, state)
        return True
    still = partial(_live.resolves, gh, issue, state, attempt.source)
    if _record_admission.strictly_written(gh, issue, state, still=still):
        return True
    log.warning("issue=#%d its manifest correction's park did not land; resolving nothing behind it", issue.number)
    return False


def owed(state: PinnedState, attempt: _records.CorrectionAttempt) -> str | None:
    """The notice a park over `attempt` was about to post when its tick ended, or None where the record holds none."""
    held = state.get(_OWED)
    nonce = attempt.source.invocation.nonce
    if not isinstance(held, dict) or held.get(_SOURCE) != nonce:
        return None
    message = held.get(_MESSAGE)
    return message if isinstance(message, str) and message else None


def parks_once(
    gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt, message: str,
) -> _live.Live:
    """Park on `message` for `attempt`, or record the park a notice of ours already said; what the issue read as.

    STANDS where the park was taken. Anything else is the answer the pinned
    comment and the issue gave, read afresh behind the thread's read and ahead
    of any post or write (`correction_live.answers`), and nothing is said or
    written: a hold, a reading GitHub would not answer, a comment moved since
    the tick read it or no longer carrying this attempt bound to its record
    and cycle, or a move -- the saved context, the owner, or the requirements
    -- whose road is not this park's.

    The park is written whole either way, and bounded wherever a reply
    boundary stands to walk from: it records the thread read through our own
    comments and no further, so a reply written while the correction was out
    -- below the notice, which landed after it -- stays past the boundary for
    the resume to deliver. A thread with no boundary stands the park on its
    notice, as the run's own park would have. Only a park this call posts is
    announced on the event stream: one recorded over an earlier notice was
    announced as that notice went out.
    """
    floor = state.get(_state._LAST_ACTION_COMMENT_ID)
    try:
        thread = list(gh.comments_after(issue, floor, state_comment_id=state.comment_id))
    except Exception:
        log.exception("issue=#%d could not be read for its manifest correction's park; holding it", issue.number)
        return _live.Live.UNREAD
    said = _ready_readings.found(gh, state, thread, _receipt(attempt))
    live = _live.answers(gh, issue, state, attempt.source)
    if live is not _live.Live.STANDS:
        log.info("issue=#%d reads %s ahead of its correction's park; parking nothing", issue.number, live.value)
        return live
    bounded = isinstance(floor, int)
    if said is None:
        _guards._park_awaiting_human(
            gh, issue, state, receipted(message, attempt),
            bounded=bounded,
            reason="decomposer_invalid_manifest",
            agent_role="decomposer",
            session_id=attempt.source.session,
            retry_count=_guards._safe_int(state.get("retry_count")),
        )
    else:
        _recorded_over(gh, issue, state, said, bounded=bounded)
    state.state_data.pop(_OWED, None)
    return live if recorded(gh, issue, state, attempt) else _live.Live.UNREAD


def _recorded_over(gh: GitHubClient, issue: Issue, state: PinnedState, said: int, *, bounded: bool) -> None:
    """Stage the park the notice `said` already announced: the notice taken into our ledger, and the boundary moved."""
    before = _comments._orchestrator_ids(state)
    _comments._track_orchestrator_comment(state, said)
    state.set(_state._AWAITING_HUMAN, True)
    state.set(_state._PARK_REASON, None)
    if bounded:
        _park_watermarks._stamp_read_this_far(gh, issue, state, before)
    else:
        state.set(_state._LAST_ACTION_COMMENT_ID, said)


def _receipt(attempt: _records.CorrectionAttempt) -> str:
    """The hidden receipt a park over `attempt` ends on."""
    source = attempt.source.invocation
    return _RECEIPT.format(issue=source.issue, nonce=source.nonce)
