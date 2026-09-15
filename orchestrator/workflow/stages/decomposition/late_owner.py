# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Guard late outcomes and child activation with the current owner reading.

Completion is claimed before reading the owner. Open, closed, and unreadable
answers settle through their corresponding effects before a staged park
is released or discarded.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.decomposition import (
    late_outcome as _late_outcome,
    late_owner_reading as _late_owner_reading,
    late_owner_settlement as _late_owner_settlement,
    late_park_delivery as _late_park_delivery,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext, _OwnerState
from orchestrator.workflow.stages.decomposition.late_result_models import _LateDisposition

log = logging.getLogger("orchestrator.workflow")


def _reconcile_pending_owner_check(
    context: _LateContext,
) -> _LateDisposition | None:
    """Take again the owner read an earlier tick could not, if one is owed.

    The first thing a tick asks, ahead of the live-generation gate and the
    hold, because the marker it reads is exactly the state those two
    would route past: a revised candidate that came back under the ceiling is
    not adjudicable and an issue parked for a human is not adjudicating, and
    on either of them a pending read would otherwise stand for good.

    Answers None when there is nothing owed, and also when the read succeeded
    -- the tick carries on with the park cleared and its follow-up said. A
    closed owner and one that still cannot be read are the whole of what the
    tick did.
    """
    generation = context.generation
    if not generation.is_present or generation.cancelled:
        return None
    if not generation.owner_check_pending:
        return None
    reading = _guarded_owner(context)
    if reading == _OwnerState.CLOSED:
        return _LateDisposition.CANCELLED
    if reading == _OwnerState.UNREADABLE:
        return _LateDisposition.PARKED
    return None


def _still_wanted(context: _LateContext) -> _LateDisposition | None:
    """Whether the split may take its next irreversible step, or why not.

    None is the only answer that lets one happen. Asked immediately before
    each of them rather than once for all of them, because the steps are not
    one moment: a push and a fetch stand between the verdict and the first
    child, and a create, a record, and a seed stand between every child and
    the next, so a human can close the issue inside any of those gaps.

    What makes asking necessary at all is who else could see the close. A
    poll that observes one while this worker holds the issue cannot hand it
    anywhere -- the scheduler admits no second worker for an issue one is
    already running -- so the observation is deferred to a later tick, and
    until that tick comes THIS run is the only thing standing between a
    closed issue and another real issue created against it.

    The three answers are the guard's own, unchanged. A closed owner is
    marked and the cycle ends where it stands, with everything already put on
    the remote left on the ledger for the cleanup path. An unreadable one
    parks: a read that established nothing is not "still open", and the read
    stays owed on the record, which is what brings the next tick back to it
    ahead of anything else it would do.
    """
    reading = _guarded_owner(context)
    if reading == _OwnerState.OPEN:
        return None
    if reading == _OwnerState.CLOSED:
        return _LateDisposition.CANCELLED
    return _LateDisposition.PARKED


def _guarded_owner(context: _LateContext) -> _OwnerState:
    """Read this generation's owner fresh, and record what the answer costs.

    The one call every completed late run passes through before it is acted
    on, and it is entered PAST a claim rather than making one. The obligation
    is written by the completion itself, in the same write that recorded what
    the run left, so a process that dies anywhere between the run and this
    read -- inside it, or before a line of it has run -- leaves an issue that
    still owes the read and a park a human can already see. Deriving the
    obligation from the failure would mean a read that never came back left
    nothing behind at all, and taking it here would mean a tick that died on
    the way here left nothing either.

    Asked rather than assumed all the same, because "claimed" is the one thing
    the read may not be taken without: a caller whose own write did not carry
    it gets the claim here, which costs a write and is not the same as reading
    an owner nothing would bring a tick back to.

    Each answer then persists what it means before anything external happens:
    an open owner drops the claim and releases what was staged, a closed one
    persists the cancellation, and an unreadable one leaves the claim exactly
    where it was written.
    """
    if not _already_claimed(context.generation):
        _late_outcome._completed(context)
    reading = _late_owner_reading._read_owner(context)
    if reading == _OwnerState.CLOSED:
        _late_owner_settlement._cancelled(context)
    elif reading == _OwnerState.UNREADABLE:
        _late_owner_settlement._unreadable(context)
    else:
        _late_owner_settlement._cleared(context)
        _late_park_delivery._release_staged_park(context)
    context.staged_park = None
    return reading


def _already_claimed(generation: LateGeneration) -> bool:
    """Whether the read this guard is about to take is already owed durably.

    The precondition every caller is supposed to arrive having met, asked
    rather than assumed. A completion writes its own result and this claim as
    one thing -- that write is what a crash before the read leaves behind, and
    what stops the next tick paying for an agent that already answered -- and
    a reconciliation of an owed read is here BECAUSE the claim is standing.

    So the answer is normally yes and the guard writes nothing. It is asked at
    all because "claimed" is the thing the read may not be taken without, and
    a caller whose own write did not carry it gets the claim here rather than
    a read nobody would come back to. The phase is part of the question for
    the same reason it is part of the claim: a generation that recorded the
    obligation at an earlier boundary still owes this one its name.

    Which phases those are is the completion's own answer, not a single one.
    A claim never writes over a boundary the split transaction owns -- doing
    so would tell the reclamation that nothing had been cut from the ref yet
    -- so a transaction re-entered after a crash carries its claim under the
    boundary it interrupted, and that is as standing a claim as `owner_check`.
    """
    return (
        generation.owner_check_pending
        and generation.phase in _late_outcome._CLAIM_PHASES
    )


def _latch_stops(context: _LateContext) -> _LateDisposition | None:
    """Whether a latched close forbids the step that is about to happen.

    The barrier for every irreversible step whose own moment is too tight for
    a request: the create at the bottom of the child loop, the spawn, the
    write that erases a settled cycle. It is the LATCH alone rather than the
    whole guard, because those steps sit where a claim would be wrong -- a
    claim names `owner_check`, and writing it over whatever boundary the tick
    actually reached is the rewind the record refuses -- and because it costs
    nothing: no request, and no write at all on an issue still reading open.

    A cycle already cancelled answers None, because there is nothing left
    here to end and the gate above routes it to its ending anyway.
    """
    if not context.generation.is_present or context.generation.cancelled:
        return None
    if not _late_owner_reading._latched_close(context):
        return None
    _late_owner_settlement._cancelled(context)
    return _LateDisposition.CANCELLED


def _still_activating(context: _LateContext) -> _LateDisposition | None:
    """Whether the children this transaction made may be started.

    The last gap of all and the only one past the retirement, so it is asked
    without the claim every earlier barrier takes: the generation now stands
    at `cleaning_up`, and a claim writes `owner_check` over that -- the very
    boundary the whole-ledger rule reads to decide whether a ref may go.

    Three answers still, and the two that stop are not the same stop. A closed
    owner -- latched, or reported so by GitHub between the retirement write
    and this read -- ends the cycle: the mark goes down, no child is started,
    and the ending settles what the transaction already put on the remote. An
    unreadable one starts nothing and ends nothing; the umbrella's own walk
    takes the same reading on its next dependency poll, which is the retry the
    activation always had.
    """
    reading = _late_owner_reading._read_owner(context)
    if reading == _OwnerState.OPEN:
        return None
    if reading == _OwnerState.CLOSED:
        _late_owner_settlement._cancelled(context)
        return _LateDisposition.CANCELLED
    log.warning(
        "issue=#%d could not be re-read before its children were started; "
        "leaving them where they are for the umbrella's own walk",
        context.issue.number,
    )
    return _LateDisposition.SETTLED
