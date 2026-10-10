# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed rewrite's finish captured, abandoned wherever its recovery reads the landing moved.

A finish that recorded the landed head's evidence transaction and stopped
short of its route leaves it pending beside the attempt
(`rewrite_finish_captured`), and only the recovery of the push already landed
-- over a remote and a checkout both still on that head -- takes the route it
carries (`rewrite_landed`). Every other road the recovery is sent down reads
the landing somewhere else, and none of them routes the transaction: an
unmoved checkout back on the anchor, a remote that is not on the checkout --
rolled back, or moved out of band -- and a remote and checkout that agree on
another head all clear, reset, or park the attempt. So the transaction is
abandoned before any of them is taken (`abandons_off_the_landing`): movement
under a decision is a decision no later route may take, and once the attempt
is cleared nothing but the dispatcher's reconciliation would ever read the
transaction again, which settles whatever proves whole however the heads got
back. The same holds for the checkout or remote the landed road itself reads
leaving the head (`abandons`).

Only a transaction about the head the attempt's finish announced
(`pending_auto_base_rebase_announced_sha`) is read: a finish records evidence
only behind the checkpoint that writes that mark, and while the attempt stands
nothing else records evidence for the head. A snapshot nobody could take is
the git owner's to answer and abandons nothing here. A checkout nobody could
read beside a remote it disagrees with abandons the transaction all the same,
since every road that snapshot takes resets the checkout off the head itself.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.base_sync import (
    recovery_push as _recovery_push,
    replay_evidence as _replay_evidence,
    state as _base_sync_state,
)
from orchestrator.git.base_sync.models import _AutoRebaseRecoveryContext, _AutoRebaseRecoverySnapshot
from orchestrator.git.base_sync.rewrite_handoffs import _LandedRewrite, _PushOutcome, _RewriteCandidate
from orchestrator.git.ref_transport import _RefRead
from orchestrator.workflow.engine import rewrite_finish_captured as _captured
from orchestrator.workflow.engine.rewrite_evidence_proof import LEFT_THE_LANDING
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad, LandedFinish


def abandons_off_the_landing(context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot) -> None:
    """Abandon the transaction captured for the announced head unless `snapshot` reads both heads on it.

    Asked by the recovery's coordinator of every snapshot it reads, before
    the road the snapshot chooses is taken; a remote and a checkout both on
    the announced head are the landed road's to finish, which reads them
    again itself.
    """
    announced = context.state.get(_base_sync_state._PENDING_ANNOUNCED_SHA)
    if announced and (snapshot.local_head, snapshot.remote_head) != (announced, announced):
        abandons(context, snapshot)


def abandons(
    context: _AutoRebaseRecoveryContext,
    snapshot: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate | None = None,
) -> None:
    """Abandon a transaction an earlier finish recorded for the announced head the landing was read leaving.

    `candidate` is the checkout as the caller already read it, read here
    where the caller has none. The landing is handed, named against the
    announced head, to the last word every route of the evidence step ends in
    (`rewrite_finish_captured.stands_before_the_route`) with the movement
    already read (`rewrite_evidence_proof.LEFT_THE_LANDING`), however its own
    readings come out -- the heads may be back by then -- so it abandons the
    transaction unrun, or, with no room for that, refuses it for good. Nothing
    is routed either way, and nothing is read or written where no transaction
    is recorded for that head.
    """
    announced = context.state.get(_base_sync_state._PENDING_ANNOUNCED_SHA)
    if not announced:
        return
    read = candidate or _recovery_push._recovered_candidate(context, snapshot)
    finish = LandedFinish(
        gh=context.gh,
        spec=context.spec,
        issue=context.issue,
        state=context.state,
        landed=_LandedRewrite(
            candidate=replace(read, checkout=replace(read.checkout, head=announced)),
            outcome=_PushOutcome.OBSERVED,
            remote=_RefRead(sha=snapshot.remote_head),
        ),
        label=_replay_evidence._recovered_stage(context.label),
        road=FinishRoad.RECOVERY,
    )
    if _captured.recorded(finish, logged=False) is not None:
        _captured.stands_before_the_route(finish, proof=LEFT_THE_LANDING)
