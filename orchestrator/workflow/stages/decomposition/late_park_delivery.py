# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Deliver and reconcile the notice a durable late park owes its issue.

The park decision and generation are already persisted before release. The
notice is settled only after the comment succeeds, so an interrupted write
leaves evidence a later tick can match against the thread without announcing
it twice. A refused comment leaves the durable result available for recovery.

Retry-cap delivery and reconciliation keep their existing audit phases beside
the effects they describe. Park reasons, watermark updates, and the shared
pinned write are read directly from ``late_park_state``; this owner never calls
back into the decisions in ``late_parks``.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.workflow.engine import guards as _guards, retry_budget as _retry_budget
from orchestrator.workflow.stages.decomposition import late_notice as _late_notice, late_park_state as _late_park_state
from orchestrator.workflow.stages.decomposition.late_models import _LateContext, _StagedPark

log = logging.getLogger("orchestrator.workflow")


def _release_staged_park(context: _LateContext) -> None:
    """Say what a park already recorded is for, if it still owes a sentence.

    Called once the owner has been read and came back open, so nothing is said
    to a thread whose issue this tick could not prove is still there. A park
    whose notice this drops is not lost: the park itself is durable, and
    whatever re-takes it announces the reason it fails for THEN, which is the
    current one rather than one an outage ago.

    The mention goes through the shared park so the watermark it ratchets is
    the one every other park in this repository ratchets -- that id is the
    response boundary a reply is measured against, and a notice that did not
    move it would let a comment written before it read as an answer to it.

    The obligation is dropped between the post and the write, which is the
    only order that fails the right way: a crash in that window leaves the
    sentence owed by a thread that already has it, so the next tick repeats
    one comment -- the same window every park in this repository has -- rather
    than dropping one nobody ever said.

    What goes out is the sentence with whatever it NAMES put back, so a notice
    that leaves the recorded explanation on the record rather than copying it
    reaches the thread whole -- and reaches it identically here and on a
    redelivery, which is what the reconciliation that looks for it depends on.
    """
    staged = context.staged_park
    if staged is None:
        return
    context.staged_park = None
    _guards._park_awaiting_human(
        context.gh,
        context.issue,
        context.state,
        f"{config.HITL_MENTIONS} {_late_notice._filled(context, staged)}",
        reason=staged.reason,
    )
    context.state.set(_late_park_state._PARK_REASON, staged.reason)
    _late_notice._notice_settled(context)
    _audit_retry_cap(context, staged, _retry_budget.RetryCapPhase.DELIVERED)
    _late_park_state._persist(context)


def _reconcile_notice_delivery(context: _LateContext) -> None:
    """Discharge an obligation the thread shows was already discharged.

    The first thing a tick asks, ahead of even the owed owner read, because
    everything that reads the obligation afterwards would read it wrong. The
    post and the write that records it are two operations, so a write that
    failed after a post that landed leaves pinned state claiming a sentence is
    owed to a thread that already has it -- and two different steps then draw
    two different wrong conclusions from it. The redelivery repeats a comment,
    which is cheap; the guard's own recovery reads it as proof that nobody was
    ever told and clears the park WITHOUT the follow-up it promised, which is
    a sentence nothing else will ever say.

    So both halves the failed write was carrying are put back: the obligation
    is dropped, and the consumed watermark is ratcheted to the comment that
    actually carried it -- the id a park's own mention is supposed to move it
    to, and the one the follow-up's own at-most-once check is scoped by.

    Nothing is said here and nothing is decided. A notice the thread does not
    carry is left exactly as it was, for the retry below to say.
    """
    owed = _late_notice._owed_notice(context)
    if owed is None:
        return
    delivered = _late_notice._delivered_id(context, owed)
    if delivered is None:
        return
    log.info(
        "issue=#%d already carries the notice for park %s; recording it as "
        "said rather than saying it twice",
        context.issue.number, owed.reason,
    )
    _late_notice._notice_settled(context)
    _late_park_state._mark_replies_read(context, delivered)
    _audit_retry_cap(context, owed, _retry_budget.RetryCapPhase.RECONCILED)
    _late_park_state._persist(context)


def _redeliver_park_notice(context: _LateContext) -> None:
    """Say what a standing park is for, if a refused comment never did.

    The retry the durable half of a park earns. It runs at the top of a tick,
    ahead of every gate a park routes past, because a park is exactly the
    state that stops a tick reaching anything: the drift park consumes
    nothing and returns, the stalled revision waits for a reply, and the
    recorded question is answered from the record -- so a sentence hung off
    any of them would never be said.

    The tick's own snapshot is what it is said on, which is the same standing
    every park taken BEFORE a run has: the issue was fetched seconds ago by
    the poll that routed it here, and nothing has been paid for since. A
    cancelled cycle is the one exception -- its parks explain a candidate
    nobody is adjudicating any more, and its issue is one somebody closed.

    A park a fresh attempt supersedes is left to that attempt, which runs
    just below this and either retires the park or re-takes it and says the
    reason it fails for now. Saying the old sentence first would announce a
    wall this tick is about to walk through.

    Idempotent by what it clears: the obligation is dropped by the post that
    discharges it, so a notice reaches the thread once per park rather than
    once per tick.
    """
    generation = context.generation
    if not generation.is_present or generation.cancelled:
        return
    owed = _late_notice._owed_notice(context)
    if owed is None or owed.reason in _late_park_state._SUPERSEDED_PARKS:
        return
    log.info(
        "issue=#%d is parked as %s with its notice unsaid; posting it now",
        context.issue.number, owed.reason,
    )
    context.staged_park = owed
    _release_staged_park(context)


def _audit_retry_cap(
    context: _LateContext,
    staged: _StagedPark,
    phase: _retry_budget.RetryCapPhase,
) -> None:
    """Report a spent-budget park's step on the budget's own stream.

    Only that park's. Every other reason this owner takes is a fact about the
    candidate, and what those report is a late verdict or a typed late
    failure; this one is a fact about the issue's day of tokens, and what an
    operator counts it beside is every other stage's refusal on the same
    budget.

    Emitted from the two seams where a sentence actually reaches the thread
    rather than from the refusal that owes it, because that is what the two
    phases claim: one comment paid for, and one found already posted by a tick
    whose write did not land.
    """
    if staged.reason != _late_park_state.PARK_RETRY_CAP:
        return
    _retry_budget._emit_phase(context.gh, context.issue, context.state, phase)
