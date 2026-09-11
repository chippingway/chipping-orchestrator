# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Guard a completed late run before settling or publishing its verdict.

Every completion, including a reused answer or a park, re-reads the issue
owner. Only the settlement that clears this guard may hand a split to the
transaction; deferred runs leave durable state as they found it.
"""
from __future__ import annotations

from orchestrator.workflow.stages.decomposition import (
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_settlement as _late_settlement,
    late_transaction as _late_transaction,
)
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
    _OwnerState,
)


def _guarded(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _LateAdjudicationRun:
    """Read the owner again now this run is over, then act on what it left.

    Every completion comes through here, not only the ones that decided
    something: a question, a timeout, an unusable reply, and a reply refused
    for a moved candidate are all runs the issue paid for, and a closure
    during any of them strands the same generation and the same hold.

    A run the tick DECLINED is the one exception, and it is not a completion:
    an operator's `paused` label and a shutdown sweep both mean this tick did
    not happen, and durable state has to be left exactly as the prior tick
    left it -- which a write here would break.

    A split is the one verdict the settlement does not finish. It hands back
    an outcome carrying the guarantee the transaction cannot check for itself
    -- that this verdict was re-checked against an owner read taken after the
    agent finished -- and the transaction that creates the children runs from
    here, past that read, on that handoff and on no other shape.
    """
    if finished.disposition == _LateDisposition.DEFERRED:
        return finished
    reading = _late_owner._guarded_owner(context)
    if reading == _OwnerState.CLOSED:
        return _late_outcome._finished(context, _LateDisposition.CANCELLED)
    if reading == _OwnerState.UNREADABLE:
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    settled = _late_settlement._settle_adjudication(context, finished)
    if settled.guarded_split is None:
        return settled
    return _late_transaction._run_late_split(context, settled)
