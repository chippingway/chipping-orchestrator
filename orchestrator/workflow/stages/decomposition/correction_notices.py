# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The receipt a park over a manifest correction ends on, and the park a later tick owes without saying it twice.

Every park taken over an attempt -- the correction's own answer parked, or an
attempt armed with no launch granted and given up behind the ordinary park --
ends on a hidden receipt naming the issue and the source invocation's random
nonce (`receipted`), which no agent answer can know to forge. Each of those
parks lands before the attempt is resolved (`correction_settlement`), and a
park whose write was lost leaves its notice on the thread with nothing
recording it. The tick that finds that attempt owed a park it does not stand
on (`correction_reconcile`) asks the thread past the reply boundary for the
receipt first (`parks_once`), saying the notice the record still holds where
one was about to be posted when a tick ended (`owing`, `owed`), so a post that
never landed is said in its own words -- the latest error and rejected answer
-- rather than in what the attempt alone recalls: where a comment of ours carries it, the park is
recorded over that notice and nothing is said again; otherwise the notice is
posted, receipt and all. Either way the park is bounded wherever a reply
boundary stands: it records the thread read through our own comments and no
further, so a reply written while the correction was out -- below a notice
that landed after it -- stays past the boundary for the resume to deliver. A
thread nobody could read says nothing and records nothing, and the next tick
asks again; so does a pinned comment or an issue that no longer stands as the
rejected run left them, read afresh behind the thread's read and ahead of any
post or write (`correction_live.answers`) -- a hold or an unread reading
holds the tick, and a moved context, owner, or requirements is left to the
road that answers it, so no notice is posted, or park written, over it.
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    park_watermarks as _park_watermarks,
    record_admission as _record_admission,
)
from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_live as _live,
    correction_records as _records,
    correction_standing as _standing,
    ready_readings as _ready_readings,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_RECEIPT = "<!--orchestrator-decomposer-correction:issue={issue}:source={nonce}-->"

_OWED = _state._DECOMPOSER_CORRECTION_NOTICE

# What a reading of the attempt says where it is no longer the tick's to park over.
_NOT_ITS_OWN = frozenset((_standing.Standing.DISPLACED, _standing.Standing.DAMAGED, _standing.Standing.ABSENT))

# The members of an owed notice: the source it is the park of, and its words.
_SOURCE = "source"
_MESSAGE = "message"


def receipted(message: str, attempt: _records.CorrectionAttempt | None) -> str:
    """`message` ending on `attempt`'s receipt, or as it is where the park is over no attempt."""
    if attempt is None:
        return message
    return f"{message}\n\n{_receipt(attempt)}"


@contextlib.contextmanager
def owing(
    gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt | None, message: str,
) -> Iterator[None]:
    """Hold `message`, the park over `attempt` the block posts, on the record before it is posted.

    Written whole ahead of the post, and dropped from `state` once the block
    has posted it, for the write recording the park to land without it. A post
    that raises leaves it on the record, which the next tick's park is said
    from (`owed`) -- the latest error and rejected answer included -- under the
    same receipt and boundary. A park over no attempt, or a record that would
    not take the write, posts as it always has.
    """
    if attempt is not None:
        state.set(_OWED, {_SOURCE: attempt.source.invocation.nonce, _MESSAGE: message})
        if not _record_admission.written(gh, issue, state):
            log.warning("issue=#%d its manifest correction's park could not be held before its notice", issue.number)
    yield
    state.state_data.pop(_OWED, None)


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
    written: a hold, a reading GitHub would not answer, or a move -- the saved
    context, the owner, or the requirements -- whose road is not this park's.
    Ahead of those the comment is read back (`_still_its_own`): one moved
    since the tick read it, or no longer carrying this attempt bound to its
    record and cycle, holds the tick as UNREAD, with nothing said or written.

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
    if not _still_its_own(gh, issue, state, attempt):
        return _live.Live.UNREAD
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
    gh.write_pinned_state(issue, state)
    return live


def _still_its_own(gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt) -> bool:
    """Whether the comment, read back, is the tick's reading and still carries `attempt` bound to its record and cycle.

    A comment another road or a human wrote since the tick read it withholds
    the tick's state, whose whole-state write would put back what that write
    replaced -- a cycle moved, a pin changed -- and one whose attempt names
    another record or cycle, or is no longer this one, is no park of this
    attempt's to take.
    """
    back = _checkpoint.read_back(gh, issue, state).reading
    own = back is not None and back.attempt == attempt and back.standing not in _NOT_ITS_OWN
    if state.withheld or not own:
        log.info("issue=#%d its manifest correction's record moved under the tick; parking nothing", issue.number)
        return False
    return True


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
