# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Record supersession obligations and park publications whose proof or effects failed.

Resource state is persisted before the failure park, retaining enough
evidence for the next tick to resume the same split without another run.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split import (
    formats as _formats,
)
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateResource,
    LateResourceKind,
    LateResourceState,
)
from orchestrator.workflow.stages.decomposition import (
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext

log = logging.getLogger("orchestrator.workflow")



_SUPERSESSION_FAILED_PARK = (
    "the committed candidate for this issue was split and its snapshot and "
    "children are safe, but pull request #{number} -- the one carrying the "
    "superseded work, whether this cycle held it or the candidate was "
    "measured on it -- could not be superseded. So no child was activated "
    "while it is still open. The next tick retries the same supersession, "
    "which posts nothing twice."
)


def _parked_publication(
    context: _LateContext, number: int, disagreement: str, park: str,
) -> bool:
    """Park with the children durable and the pull request left alone.

    Nothing is activated and nothing is reclaimed, so the retry finds the same
    world: the snapshot and the children are on the remote, the pull request
    is where its human left it, and the same recorded verdict is settled again
    once the disagreement is reconciled.

    Parked with the disagreement in the notice rather than with the write
    failure's sentence, because this is not a supersession that failed. It is
    one this transaction refuses to finish -- and past the close it is one it
    already MADE -- so telling the human it "could not be superseded" would
    send them looking for a write that never went wrong. Which of the two the
    human is reading is `park`: a pull request that may not be superseded and
    one whose supersession came undone are different things to reconcile, and
    only the caller knows which side of the close it is on.
    """
    log.error(
        "issue=#%d was adjudicated as a split against PR #%d and %s; "
        "refusing to finish that split behind it",
        context.issue.number, number, disagreement,
    )
    return _unsuperseded(
        context, number, park.format(disagreement=disagreement),
    )


def _recorded_supersession(context: _LateContext, number: int) -> bool:
    """Write the supersession this pass either made or found already made."""
    _recorded_resource(
        context,
        LateResourceKind.PLAN_PR,
        str(number),
        LateResourceState.RECONCILED,
    )
    return True


def _recorded_resource(
    context: _LateContext,
    kind: LateResourceKind,
    target: str,
    resource_state: LateResourceState,
) -> None:
    """Move one obligation to the state this step left it in, durably.

    A ledger update this binary cannot apply is logged and stepped over rather
    than raised: by the time most of these run the children are already live,
    and taking the tick out over a bookkeeping entry would strand them behind
    an exception instead of behind a retry.
    """
    try:
        context.generation = context.generation.with_resource(LateResource(
            kind=kind, target=target, resource_state=resource_state,
        ))
    except _formats.InvalidLateValue:
        log.exception(
            "issue=#%d could not record the %s obligation %r",
            context.issue.number, kind, target,
        )
        return
    _late_park_state._persist(context)


def _unsuperseded(
    context: _LateContext, number: int, message: str = "",
) -> bool:
    """Park with the children durable and none of them activated.

    One reason key for every way the supersession does not land, because what
    the issue is waiting on is the same in all of them: a pull request this
    workflow may not act on behind. `message` is the sentence the human reads
    when a caller has a sharper one than "the write failed".
    """
    _recorded_resource(
        context,
        LateResourceKind.PLAN_PR,
        str(number),
        LateResourceState.FAILED,
    )
    _parked(
        context,
        message or _SUPERSESSION_FAILED_PARK.format(number=number),
        LateFailure.SUPERSESSION_FAILED,
        _late_park_state.PARK_SUPERSESSION_FAILED,
    )
    return False


def _parked(
    context: _LateContext, message: str, failure: LateFailure, reason: str,
) -> None:
    """Hand the issue back with the recorded verdict and ledgers standing."""
    _late_outcome._emit_failure(context, failure)
    _late_parks._park(context, message, reason=reason)
