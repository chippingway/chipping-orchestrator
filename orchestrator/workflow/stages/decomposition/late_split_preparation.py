# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Prepare a guarded split: validate its ledgers, prove a snapshot, then create children.

No snapshot is published for an inadmissible manifest, and no child is created
until the committed candidate is safe on the immutable ref. The owner guard
between those effects leaves cancellation to the boundary it actually reached.
"""
from __future__ import annotations

from dataclasses import dataclass

from orchestrator.workflow.late_split import (
    lineage as _lineage,
)
from orchestrator.workflow.late_split.models import (
    LateFailure,
)
from orchestrator.workflow.stages.decomposition import (
    late_children as _late_children,
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_snapshot as _late_snapshot,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
)
from orchestrator.workflow.stages.decomposition.models import _SplitPlan

_OPAQUE_LEDGER_PARK = (
    "the committed candidate for this issue was adjudicated as a split, but "
    "this issue's external-obligation ledger holds an entry this orchestrator "
    "cannot read. Nothing was snapshotted, created, or superseded: a split "
    "records a snapshot and one consumer per child on exactly that ledger, "
    "and merging into one it cannot read would drop whatever it does not "
    "understand. Settle the ledger by hand, and the next tick continues from "
    "the same recorded verdict."
)


_CONTRADICTED_PARK = (
    "the committed candidate for this issue was adjudicated as a split, but "
    "this issue's recorded lineage does not agree with the generation that "
    "was adjudicated: {reason}. Nothing was created. The generation was "
    "minted without the ancestry this issue was created under, and acting on "
    "it would let the lineage buy itself a generation past the bound -- so "
    "the two have to be reconciled by hand."
)


_FORGED_RECEIPT_PARK = (
    "the committed candidate for this issue was adjudicated as a split, but "
    "{described}. Nothing was created. Those markers are how a child created "
    "into a crash is recognized again, so a slice declaring one could be "
    "adopted for a slice it was never created for -- push a new commit to "
    "have the candidate re-read, or split it by hand."
)


_AT_BOUND_PARK = (
    "the committed candidate for this issue was adjudicated as a split, but "
    "its lineage may not split any further. Nothing was created. This is a "
    "contradiction between a recorded verdict and the lineage bound, and it "
    "has to be resolved by hand: land the candidate as one change, or split "
    "it manually."
)


def _prepare_split(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _PreparedSplit | _LateAdjudicationRun:
    """Prepare the snapshot and children for one guarded split verdict.

    Entered only with a split the post-agent owner read cleared, which is the
    guarantee the guarded handoff carries: nothing between that read and the
    snapshot re-asks it.

    Past the snapshot the owner is read again before EVERY step that puts
    something on the remote nobody takes back: before each child the loop
    creates, and again before the announcement, the supersession, and the
    activation behind them. What separates those steps from the snapshot is
    not time but consequence -- a ref is an object a later pass can reclaim,
    and a child is a real issue somebody will work.

    Asked repeatedly rather than once because the steps are not one moment,
    and because of who else can see a close while they run: a poll that
    observes one cannot hand it anywhere, since the scheduler admits no
    second worker for an issue one is already running. That observation is
    deferred to a later tick, and until it arrives this run is the only thing
    standing between a closed issue and another child created against it.

    Fails closed, like the guard it repeats: an owner that cannot be read
    parks where it stands, with the read owed on the record and the verdict
    still recorded, so the next tick resumes at no agent's cost.
    """
    guarded = finished.guarded_split
    context.generation = guarded.generation
    if _blocked_split(context, guarded.children):
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    snapshot_ref = _late_snapshot._snapshot_for_split(context)
    if snapshot_ref is None:
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    still_wanted = _late_owner._still_wanted(context)
    if still_wanted is not None:
        return _late_outcome._finished(context, still_wanted)
    plan = _late_children._create_late_children(
        context, guarded.children, snapshot_ref,
    )
    if plan is None:
        return _late_outcome._finished(context, _interrupted(context))
    return _PreparedSplit(plan, snapshot_ref)


def _interrupted(context: _LateContext) -> _LateDisposition:
    """What a step that created nothing means: a cancelled cycle, or a park.

    The loop below reports both as "no plan", because to its caller they are
    the same instruction -- create nothing further. Which of the two happened
    is on the record it just wrote, and the mark is the one that says the
    cycle is over rather than waiting.
    """
    if context.generation.cancelled:
        return _LateDisposition.CANCELLED
    return _LateDisposition.PARKED


def _blocked_split(context: _LateContext, children: tuple) -> bool:
    """Whether this verdict was refused before anything external happened."""
    refusal = _refused_split(context, children)
    if refusal is None:
        return False
    _late_outcome._emit_failure(context, LateFailure.CHILD_CREATE_FAILED)
    _late_parks._park(
        context, refusal, reason=_late_park_state.PARK_CHILDREN_FAILED,
    )
    return True


def _refused_split(
    context: _LateContext, children: tuple,
) -> str | None:
    """Why this split may not run at all, or None when it may.

    Four refusals, and each is about state no step below could repair. A
    lineage at the bound is checked again here even though the verdict was
    already converted to a question where it was read: this is the transaction
    that creates a generation, so the cap is enforced where the children would
    be born as well as where the reply is parsed.

    An ancestry that disagrees with the generation is the second, and it is
    the same cap read from the other side. A child born of an earlier split
    carries the lineage it was created under; its own generation is minted
    from that record, so a generation naming a different root or a shallower
    depth is one minted without it -- and a shallower depth is exactly how a
    lineage buys itself another generation past the bound.

    An opaque ledger is the third. A split records a snapshot and one consumer
    per child on ledgers whose unreadable entries are written back verbatim, so
    an update merged into the typed view would vanish at the next write --
    taking with it either the ref nobody would then reclaim or the consumer the
    reclamation would stop waiting for.

    A manifest declaring one of this orchestrator's own receipt markers is the
    fourth, and it is refused HERE rather than where the child body is built
    for two reasons. It is a fact about the manifest, not about one slice: the
    slice that declares another slice's marker is fine, and it is the other
    slice's lookup that then finds the wrong issue. And this is the last point
    at which refusing costs nothing -- past it the snapshot is pushed, and a
    generation holding a snapshot may no longer be revised, so the same
    refusal below would need a human where here it needs a new commit.
    """
    if not context.generation.may_split:
        return _AT_BOUND_PARK
    if context.generation.has_opaque_ledger:
        return _OPAQUE_LEDGER_PARK
    contradicted = _lineage.contradicted_lineage(
        context.state, context.generation,
    )
    if contradicted is not None:
        return _CONTRADICTED_PARK.format(reason=contradicted)
    forged = _late_children._forged_receipt(children)
    if forged is not None:
        return _FORGED_RECEIPT_PARK.format(described=forged)
    return None


@dataclass(frozen=True)
class _PreparedSplit:
    """The durable children and snapshot a transaction may announce."""

    plan: _SplitPlan
    snapshot_ref: str
