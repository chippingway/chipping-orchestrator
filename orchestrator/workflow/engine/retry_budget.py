# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist a daily retry-cap park, reconcile its notice, and grant continuation.

The ledger decides whether a launch slot is available. A refusal records its
park before notice delivery, and a later held tick replays only the sentence
still owed. Continuation grants one bounded attempt and clears that park alone."""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    retry_ledger as _retry_ledger,
    retry_notices as _retry_notices,
    retry_park_state as _retry_park_state,
    retry_values as _retry_values,
    usage as _usage,
)

log = logging.getLogger("orchestrator.workflow")


def _stage_retry_cap_park(state: PinnedState, decision: _retry_values.RetryDecision) -> bool:
    """Record the park an exhausted budget takes, and what it owes a thread.

    In memory only, like every other field a refused tick stages: what makes
    it durable is the caller's own write, which is what keeps the park and the
    obligation it carries in one write rather than two.

    Returns whether the thread is now owed a sentence. A park already standing
    whose notice has been said is not announced again -- that repeat is the
    whole failure this protocol exists to stop, and the budget is re-decided
    on every eligible tick, so nothing else would ever stop it. Nor is such a
    park rewritten: the flag, the reason, and the stage under it are already
    what this refusal would say, and the refusal is the same one.

    A park whose sentence was never said is still owed it, and what it is owed
    is the sentence it was taken with -- kept verbatim rather than rewritten
    from this refusal. The obligation is a claim about a comment that may
    already be on the thread, and the thread is searched for exactly the text
    the park recorded: a sentence reworded by a later tick under a different
    stage or a retuned cap would find nothing, post a second notice, and
    attribute the park to a stage that did not take it. Only a standing park
    with no stage of its own -- an issue parked before this field, or hand
    edited out of it -- takes this refusal's, since a park nobody can name is
    worse than one named late.
    """
    if not _retry_park_state._park_stands(state):
        state.set(_retry_values._AWAITING_HUMAN, True)
        state.set(_retry_values._PARK_REASON, _retry_values.PARK_RETRY_CAP)
        state.set(_retry_values.RETRY_CAP_STAGE, decision.stage)
        state.set(_retry_values.RETRY_CAP_NOTICE, _retry_park_state._cap_message(decision))
        return True
    if _retry_park_state._park_stage(state) is None:
        state.set(_retry_values.RETRY_CAP_STAGE, decision.stage)
    return _retry_park_state._owed_notice(state) is not None


def _charge_or_park(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    *,
    stage: str,
) -> bool:
    """Gate a fresh agent spawn, and park the issue itself when it is refused.

    The parking form of the budget, for the stages whose park carries nothing
    of their own. Everything it decides is decided by `_consume_retry_slot`;
    what is here is the tail those callers would otherwise each have to write
    -- stage the park, settle the sentence it owes against the thread, and say
    it once.

    Returns True if the spawn is allowed (and the budget was charged); False
    if the budget is out. On that branch the park is made DURABLE here, before
    a word of it is said: a notice on a thread that no pinned state backs is
    the worst of both endings -- nothing reconciles it, because nothing knows
    it is owed, and the window under it rolls over a day later with the issue
    running again beneath a comment saying it had stopped. The caller's own
    write follows and carries whatever the delivery settled.

    A park already standing for an exhausted budget is re-taken silently: the
    budget is re-decided on every eligible tick, so announcing it again would
    say the same sentence to the same thread once a poll until a human
    arrived. The thread is asked before anything is said, so a comment that
    landed under a write that failed is recorded as said rather than repeated
    -- and a thread this tick could not read is said nothing to at all, since
    the sentence it may already carry is exactly the one about to go out.
    The park stands and the notice stays owed, so the next tick reads again.

    `stage` is required rather than defaulted. It is what the park is
    attributed to and what the notice quotes, the budget is shared, and a
    default here would be one stage's name answering for another's spawn.
    """
    decision = _retry_ledger._consume_retry_slot(state, stage=stage)
    if decision.allowed:
        return True
    if not _stage_retry_cap_park(state, decision):
        _retry_notices._emit_phase(gh, issue, state, _retry_values.RetryCapPhase.STANDING)
        return False
    gh.write_pinned_state(issue, state)
    if _retry_notices._reconcile_notice(gh, issue, state) is _retry_values.NoticeReading.UNSAID:
        _retry_notices._deliver_notice(gh, issue, state)
    return False


def _replay_owed_notice(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Say what a standing retry-cap park is for, if nothing ever did.

    The retry the durable half of a park earns, and the reason the obligation
    is written down at all. A park is exactly the state that stops a tick
    reaching anything: the stages this budget gates route an awaiting-human
    issue to a resume or to nothing, and neither of those roads passes the
    gate that took the park -- so a sentence a refused post or an unreadable
    thread left owed would stay owed for as long as the issue is parked, which
    is unbounded. The human would be waiting on a comment nobody was ever
    going to write.

    So it is asked at the top of the tick, ahead of every gate a park routes
    past, and it is idempotent by what it clears: the obligation is dropped by
    the post that discharges it, so a notice reaches the thread once per park
    rather than once per tick. A thread that could not be read is left for the
    next tick rather than posted over.

    The write is taken here rather than left to the caller, because the caller
    is a tick that may be about to return without writing anything at all --
    which is exactly how the sentence was stranded. It rides the same mention
    and watermark every park in this repository does, so what it consumes is
    what a park taken now would have consumed.
    """
    if not _retry_park_state._park_stands(state) or _retry_park_state._owed_notice(state) is None:
        return False
    reading = _retry_notices._reconcile_notice(gh, issue, state)
    if reading is _retry_values.NoticeReading.UNREADABLE:
        return False
    if reading is _retry_values.NoticeReading.UNSAID:
        _retry_notices._deliver_notice(gh, issue, state)
    gh.write_pinned_state(issue, state)
    return True


def _grant_continuation(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Clear a standing retry-cap park and buy it one more attempt.

    The renewal the park's own notice asks for, and the only one there is: the
    window reopens HERE, at a human's word, and what it holds is a single
    slot. A whole fresh day would let one reply spend the cap over again with
    nobody watching, which is the runaway the budget exists to bound; one
    attempt makes every retry past the cap a decision somebody took.

    What it grants is written down as a count of attempts rather than as a
    counter to compare against the setting later. The setting is a global an
    operator moves while issues are in flight, and a grant expressed against
    it is worth whatever it has become by the time the spawn is asked for:
    nothing at all once the budget is turned off, and several attempts once it
    is widened. One is one, so it is stored as one -- and from here to the
    spawn that spends it, nothing this issue is answered with reads the cap.

    Whether the caller is entitled to grant it -- that a park stands, and that
    the comment asking is a trusted `/orchestrator continue` -- is the
    caller's to establish. What is here is what granting one does.
    """
    _retry_notices._emit_phase(gh, issue, state, _retry_values.RetryCapPhase.CONTINUED)
    state.set(_retry_values.RETRY_CAP_CONTINUED, _retry_values._GRANTED_ATTEMPTS)
    state.set(_retry_values._RETRY_WINDOW_START, _usage._now_iso())
    state.set(_retry_values._RETRY_COUNT, 0)
    state.set(_retry_values._AWAITING_HUMAN, False)
    state.set(_retry_values._PARK_REASON, None)
    state.data.pop(_retry_values.RETRY_CAP_STAGE, None)
    _retry_park_state._settle_notice(state)
