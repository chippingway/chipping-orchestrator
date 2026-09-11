# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Admission to late adjudication: recover owed effects, prove evidence, then hold the PR.

These gates run before a recorded answer is reused or a new run is bought. A
failed read, a standing budget park, or an unprovable frozen pair stops every
later effect; the pull-request hold is taken only after the evidence is proved.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.git.measurement import commits as _measurement_commits
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.late_split import formats as _formats, validation as _late_validation
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
    LatePhase,
)
from orchestrator.workflow.stages.decomposition import (
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

log = logging.getLogger("orchestrator.workflow")


_HOLD_FAILED_PARK = (
    "could not put the adjudication hold on the pull request this issue's "
    "candidate stands on, so no late decomposer was spawned and the committed "
    "candidate stays unpublished. Settle the pull request, then the next tick "
    "retries the same reconciliation against the same frozen commit."
)


_INCOMPLETE_PARK = (
    "this issue records an oversized committed candidate that cannot be "
    "adjudicated: {reason}. Nothing was spawned and no pull request was "
    "touched. The recorded generation has to be repaired -- what an agent "
    "would be shown is derived from those fields, and a diff taken against a "
    "commit nobody froze is not a reading of this candidate."
)


_MISSING_OBJECTS_PARK = (
    "this issue's frozen pair is not on this host: {missing} cannot be read "
    "here. Nothing was held on a pull request and no late decomposer was "
    "spawned -- an agent shown a diff between commits this checkout does not "
    "have would answer about nothing, and that answer would be recorded as a "
    "verdict on the candidate. Restore the worktree at the recorded commit "
    "rather than re-running the developer; the recorded commits are the "
    "evidence, and a fresh checkout is not them."
)


_MISSING_WORKTREE_PARK = (
    "the committed candidate for this issue is not on this host: its "
    "worktree is gone, and the frozen commit cannot be adjudicated without "
    "it. Restore the worktree on this host rather than re-running the "
    "developer -- the recorded commit is the evidence, not the current head."
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
    if not (
        context.generation.is_present
        and context.generation.is_oversized
        and not context.generation.cancelled
    ):
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
        or not _has_frozen_evidence(context)
        or not _holds_the_objects(context)
        or not _hold_pull_request(context)
    )


def _holds_the_objects(context: _LateContext) -> bool:
    """Prove this host really has the two commits the record names.

    The step between the record being well SHAPED and it being usable, and it
    runs before the hold for the same reason the shape check does:
    everything past this point is an external effect. The hold rewrites a
    human-visible description, and the spawn behind it puts an agent on
    somebody's repository for as long as an agent runs -- both spent on a
    generation whose evidence turns out not to be here.

    Each end fails differently and each failure is one nothing may substitute
    around. A checkout that is gone takes the frozen commit with it. A
    candidate the checkout cannot peel is work made on another host, and the
    prompt would send the agent to diff a commit it does not have. And a base
    this host does not hold is the subtler one, because the run would look
    fine: the agent is shown a `git diff <base>...<candidate>` that cannot
    resolve, and a verdict returned over a diff nobody could read would be
    accepted as an answer about this candidate.

    So it parks instead, naming the worktree rather than another run: the
    recorded commits are the evidence, and a fresh checkout somewhere else is
    not them.
    """
    worktree = _worktree_paths._worktree_path(
        context.spec, context.issue.number,
    )
    if not worktree.exists():
        _late_parks._park(
            context, _MISSING_WORKTREE_PARK,
            reason=_late_park_state.PARK_WORKTREE_MISSING,
        )
        return False
    missing = _absent_object(context, worktree)
    if missing is None:
        return True
    log.error(
        "issue=#%d records a frozen pair this host cannot show (%s); parking "
        "rather than holding a pull request or spawning over it",
        context.issue.number, missing,
    )
    _late_outcome._emit_failure(context, LateFailure.MEASUREMENT_FAILED)
    _late_parks._park(
        context, _MISSING_OBJECTS_PARK.format(missing=missing),
        reason=_late_park_state.PARK_EVIDENCE_MISSING,
    )
    return False


def _absent_object(context: _LateContext, worktree: Path) -> str | None:
    """Which end of the frozen pair this checkout cannot show, or None.

    Named rather than counted, because the two are repaired differently: a
    candidate is work that has to come back with its branch, while a base is
    an object a fetch can still bring.

    What the fetch said for itself is logged rather than named, because the
    two readers want different things: the park tells a human which end to
    restore, while the transport's own line is for the operator following the
    plumbing beside it and would only crowd the instruction out.
    """
    generation = context.generation
    candidate = _measurement_commits._prove_candidate_commit(
        worktree, generation.candidate_sha,
    )
    if not candidate.is_frozen:
        return f"candidate {generation.candidate_sha}"
    base = _measurement_commits._base_object_present(
        context.spec, worktree, generation.base_sha,
    )
    if base.present:
        return None
    log.error(
        "issue=#%d cannot read base %s here: %s",
        context.issue.number, generation.base_sha, base.detail,
    )
    return f"base {generation.base_sha}"


def _has_frozen_evidence(context: _LateContext) -> bool:
    """Prove this generation is one that may be acted on, or park loudly.

    Everything past this point is derived from the record: the prompt names
    both commits and tells the agent to diff between them, the hold marks a
    pull request in the generation's name, and the verdict is reported under
    its identities. A generation missing one of those does not produce a
    smaller reading of the candidate -- it produces a `git diff` against
    nothing and a record two sinks would refuse afterwards, having already
    paid for the run that made it.

    Nothing is emitted for the refusal. A record with no usable identity is
    exactly what the sinks may not carry, so the report is the park and the
    log line, which name the field and not its content.
    """
    unusable = _incomplete_evidence(context.generation, context.issue.number)
    if unusable is None:
        return True
    log.error(
        "issue=#%d has an oversized late generation that cannot be "
        "adjudicated (%s); parking rather than spawning",
        context.issue.number, unusable,
    )
    _late_parks._park(
        context,
        _INCOMPLETE_PARK.format(reason=unusable),
        reason=_late_park_state.PARK_INCOMPLETE,
    )
    return False


def _incomplete_evidence(
    generation: LateGeneration, issue_number: int,
) -> str | None:
    """Why this generation may not be adjudicated here, or None if it may.

    The domain's own record gate answers the first part -- the identities a
    later record is correlated by, and the shape of every field one would
    carry. Both frozen commits are required beside it: they are optional to
    that gate because a restart's fresh cycle has deliberately let them go,
    and they are not optional here, because they are the two ends of the diff
    this whole adjudication is about.

    The last part is the one the gate cannot ask, because it does not know
    which issue is being adjudicated. A generation is a record ABOUT an issue,
    and a positive `late_current_issue` is not the same claim as one naming
    THIS issue: a record carrying somebody else's number would show the agent
    a prompt that names two issues, mark a pull request in a foreign
    generation's name, and file the verdict against the issue it names rather
    than the one it ran on.
    """
    try:
        _late_validation.check_generation(generation)
    except _formats.InvalidLateValue as refused:
        return str(refused)
    if not generation.candidate_sha or not generation.base_sha:
        return "the frozen candidate and base commits are not both recorded"
    if generation.current_issue != issue_number:
        return f"it was recorded against issue #{generation.current_issue}"
    return None


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
