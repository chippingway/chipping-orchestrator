# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dormant settled-evidence policy's readiness step over a landed rewrite's head, beside the one every road selects.

A finish is held to one of two policies: the one every production road hands
over, which proves again only a transaction an earlier finish captured for the
landed head, and a dormant one a caller selects only by building the finish
with `rewrite_finish_models.LandedFinish.proves_settled`. The dormant policy
proves evidence already settled for the head ready again
(`rewrite_finish_readiness.stands_ready`), and invalidates it into history
whole wherever anything it is bound to moved since it settled.

`stands_ready_if_settled` is that policy's step: it proves evidence settled
current for the head ready, where any is, and -- asked for the base -- holds a
head with none to the base its replay was made onto, or the base the tick
counted it against. It answers for both policies: a finish not held to the
dormant one goes on with nothing read. It is a primitive a caller holding
such a finish asks directly, announcing, relabelling, parking, and retiring
nothing; neither the evidence phase (`rewrite_finish_settlement.resolves`)
nor the coordinator (`rewrite_finish.finalizes`) asks it yet.

Nothing here runs the configured commands, posts an artifact, launches a
developer, or announces anything.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import attempt_records as _attempt_records
from orchestrator.workflow.engine import (
    rewrite_finish_captured as _captured,
    rewrite_finish_readiness as _readiness,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import standing_refusal
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish

log = logging.getLogger("orchestrator.workflow")


def stands_ready_if_settled(finish: LandedFinish, *, or_the_base: bool = False) -> FinishOutcome | None:
    """`stands_ready` over evidence settled current for `finish`'s landed head, where any is; None to go on.

    Asked only of a finish held to the dormant settled-evidence policy: any
    other finish goes on from here with nothing read. `or_the_base` asks for
    the proof a route's last write needs, behind requests that took time: a
    base advanced meanwhile holds the route with the attempt standing, a head
    with no evidence current held to the base tip its replay was made onto
    (`rewrite_finish_captured.stands_before_the_route`), so the recovery
    continues it to another rebase. An attempt that records no tip -- blanked
    to record movement, blanked because the base moved while git ran, or a
    legacy attempt -- proves no base, so its head is held to the base this
    tick counted it against (`rewrite_evidence_proof.standing_refusal`): one
    advanced, rewound or repointed under the local ref, or unreadable holds
    the route for the next tick's fetch to count the head again.
    """
    if not finish.proves_settled:
        return None
    current = _settlement.read_current_evidence(finish.state)
    stopped = None
    if current is not None and current.binding.target.target_head == finish.head:
        stopped = _readiness.stands_ready(finish, current)
    elif or_the_base:
        stopped = _captured.stands_before_the_route(finish, landing=False)
    unproven = not _attempt_records._recorded_onto(finish.state)
    if stopped is not None or not (or_the_base and unproven):
        return stopped
    counted = finish.landed.candidate.checkout
    moved = standing_refusal(finish, onto=counted.base.tip)
    if moved is None:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s: its attempt records no base tip, and the base this tick counted "
        "it against reads otherwise now (%s)",
        finish.issue.number, finish.head, moved.refusal,
    )
    return FinishOutcome.HELD
