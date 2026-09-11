# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Admission to late adjudication: recover owed effects, prove evidence, then hold the PR.

These gates run before a recorded answer is reused or a new run is bought.
The live-generation predicate leaves ordinary decomposition to its own budget
gate. Eligible generations reach `late_evidence` before the pull-request hold,
so no hold or spawn runs over a record or frozen pair this host cannot prove.
"""
from __future__ import annotations

from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
    LatePhase,
)
from orchestrator.workflow.stages.decomposition import (
    late_evidence as _late_evidence,
    late_hold as _late_hold,
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_park_delivery as _late_park_delivery,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_retry_cap as _late_retry_cap,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateContext,
    _LateDisposition,
)

_HOLD_FAILED_PARK = (
    "could not put the adjudication hold on the pull request this issue's "
    "candidate stands on, so no late decomposer was spawned and the committed "
    "candidate stays unpublished. Settle the pull request, then the next tick "
    "retries the same reconciliation against the same frozen commit."
)


def _blocked_before_running(
    context: _LateContext,
) -> _LateDisposition | None:
    """What stops this tick before any agent could run, if anything does.

    The owner read this generation still owes is asked ahead of every other
    gate, because a read that is owed is owed whether or not the candidate is
    adjudicable: a revision that came back under the ceiling routes past the
    size gate, and an issue parked for a human routes past everything, so a
    retry hung off either would never run at all.

    A park notice a refused comment stranded is redelivered next, for the
    same reason and one step later: it is owed whether or not the candidate
    is adjudicable, and every gate below this one is a gate a parked issue
    routes past. One step later because the read comes first -- an owner that
    turns out to be closed cancels the cycle, and a cancelled cycle's parks
    explain a candidate nobody is adjudicating any more.

    What comes before BOTH is reconciling that obligation against the thread,
    since the read is one of the steps that would otherwise read it wrong: a
    notice whose post landed and whose write did not is owed by the record and
    not by the issue, and the guard would take it as proof that nobody was
    told and clear its park without the follow-up it promised.

    Everything below the live-generation gate is one short circuit, because
    every one of them parks on its own and every one of them stops the tick.
    """
    _late_park_delivery._reconcile_notice_delivery(context)
    owed = _late_owner._reconcile_pending_owner_check(context)
    if owed is not None:
        return owed
    _late_park_delivery._redeliver_park_notice(context)
    if not _is_adjudicable(context.generation):
        return _LateDisposition.NOT_LATE
    if _parks_before_running(context):
        return _LateDisposition.PARKED
    return None


def _parks_before_running(context: _LateContext) -> bool:
    """Whether something hands this issue back before an agent could run.

    Ordered, and each step is only reached because the one above it passed. A
    spent spawn budget stops the tick first: what stands there is not about
    this generation at all -- the budget is the issue's day of tokens, shared
    with every other agent run -- but what it stops is every step below, each
    of which either probes the host, rewrites a pull request, or reads a
    thread as an answer to a question nobody asked there. It is asked BEHIND
    the live-generation gate for the opposite reason: an issue whose
    generation is not adjudicable falls through to the initial decomposition,
    and holding it here would keep that road's own park owner from ever
    seeing it.

    Then the record has to be usable, then this host has to hold the two
    commits it names, and only then is the pull request standing over the
    candidate marked -- the one step of the four that changes anything a
    human can see.
    """
    return (
        _late_retry_cap._park_owns_the_tick(context)
        or not _late_evidence._has_frozen_evidence(context)
        or not _late_evidence._holds_the_objects(context)
        or not _hold_pull_request(context)
    )


def _hold_pull_request(context: _LateContext) -> bool:
    """Reconcile the cycle-marked hold, or park without spawning.

    The boundary goes down through the record's own rule, because this runs
    on EVERY tick a live generation gets -- including one re-entering a split
    transaction that crashed mid-loop, where writing this boundary over
    `splitting` would erase the only evidence the loop was ever in flight.
    """
    context.generation = context.generation.at_phase(
        LatePhase.HOLDING_PLAN_PR,
    )
    hold = _late_hold._reconcile_hold(
        context.gh, context.issue, context.state, context.generation,
    )
    context.generation = hold.generation
    context.displaced_hold = hold.displaced
    if not hold.failed:
        return True
    _late_outcome._emit_failure(context, LateFailure.PLAN_PR_HOLD_FAILED)
    _late_parks._park(
        context, _HOLD_FAILED_PARK, reason=_late_park_state.PARK_HOLD_FAILED,
    )
    return False


def _is_adjudicable(generation: LateGeneration) -> bool:
    """Whether this issue carries a live oversized generation to adjudicate.

    An absent generation is an issue that never entered the gate, a measured
    candidate at or below its ceiling is one that publishes as it always did,
    and a cancelled cycle is cleanup-only -- none of the three may spawn.
    """
    return (
        generation.is_present
        and generation.is_oversized
        and not generation.cancelled
    )
