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

A snapshot nobody could take is the git owner's to answer, and its answer is
an abort that resets the checkout onto the anchor and clears the attempt
(`git/base_sync/snapshot.py`). Where that reset landed, the recovery itself has
moved the checkout off the landed head, and nothing is left to route the
transaction, so it is abandoned behind the abort
(`abandons_behind_the_reset`); where the reset failed, the attempt and every
record stand, nothing was read moving, and the transaction waits for the next
proof. A checkout nobody could read beside a remote it disagrees with abandons
the transaction all the same, since every road that snapshot takes resets the
checkout off the head itself.

Only a transaction about the head the attempt's finish announced
(`pending_auto_base_rebase_announced_sha`) is read: a finish records evidence
only behind the checkpoint that writes that mark, and while the attempt stands
nothing else records evidence for the head. The mark is read before the
snapshot (`announced`), since an abort clears it with the attempt.
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
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import rewrite_finish_captured as _captured
from orchestrator.workflow.engine.rewrite_evidence_proof import LEFT_THE_LANDING
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad, LandedFinish


def announced(context: _AutoRebaseRecoveryContext) -> str:
    """The head the attempt's finish announced, or ""; read before anything the recovery does can clear it."""
    return context.state.get(_base_sync_state._PENDING_ANNOUNCED_SHA) or ""


def abandons_behind_the_reset(context: _AutoRebaseRecoveryContext, head: str) -> None:
    """Abandon the transaction captured for `head`, announced before the snapshot, where its abort reset the checkout.

    Asked where the recovery's snapshot could not be taken. The abort behind
    it clears the attempt only once its reset onto the anchor landed, so an
    attempt still pinned is a reset that failed, which moved nothing and
    keeps the transaction for the next proof.
    """
    if not head or context.state.get(_base_sync_state._PENDING_PUSH_SHA):
        return
    branch = _naming._resolve_branch_name(context.state, context.spec, context.issue.number)
    abandons(context, _AutoRebaseRecoverySnapshot(branch=branch, local_head=""), head=head)


def abandons_off_the_landing(context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot) -> None:
    """Abandon the transaction captured for the announced head unless `snapshot` reads both heads on it.

    Asked by the recovery's coordinator of every snapshot it reads, before
    the road the snapshot chooses is taken; a remote and a checkout both on
    the announced head are the landed road's to finish, which reads them
    again itself.
    """
    head = announced(context)
    if head and (snapshot.local_head, snapshot.remote_head) != (head, head):
        abandons(context, snapshot)


def abandons(
    context: _AutoRebaseRecoveryContext,
    snapshot: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate | None = None,
    *,
    head: str = "",
) -> None:
    """Abandon a transaction an earlier finish recorded for the announced head the landing was read leaving.

    `candidate` is the checkout as the caller already read it, read here
    where the caller has none, and `head` the announced head where the
    comment no longer carries the mark. The landing is handed, named against the
    announced head, to the last word behind the evidence step
    (`rewrite_finish_captured.stands_before_the_route`) with the movement
    already read (`rewrite_evidence_proof.LEFT_THE_LANDING`), however its own
    readings come out -- the heads may be back by then -- so it abandons the
    transaction unrun, or, with no room for that, refuses it for good. Nothing
    is routed either way, and nothing is read or written where no transaction
    is recorded for that head.
    """
    landed = head or announced(context)
    if not landed:
        return
    read = candidate or _recovery_push._recovered_candidate(context, snapshot)
    finish = LandedFinish(
        gh=context.gh,
        spec=context.spec,
        issue=context.issue,
        state=context.state,
        landed=_LandedRewrite(
            candidate=replace(read, checkout=replace(read.checkout, head=landed)),
            outcome=_PushOutcome.OBSERVED,
            remote=_RefRead(sha=snapshot.remote_head),
        ),
        label=_replay_evidence._recovered_stage(context.label),
        road=FinishRoad.RECOVERY,
    )
    if _captured.recorded(finish, logged=False) is not None:
        _captured.stands_before_the_route(finish, proof=LEFT_THE_LANDING)
