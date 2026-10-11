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

The abandonment is a write of its own, over the comment read afresh, and it
can fail: a comment nobody could read again, or one another road moved under
the write. Until it lands, the transaction is still the attempt's to answer,
so the coordinator takes none of those roads -- nothing is reset, cleared, or
parked -- and holds the tick with the attempt standing
(`abandons_off_the_landing` answers whether it may go on); the anchor keeps the
dispatcher's reconciliation off the transaction meanwhile, and the next tick's
recovery reads the landing and abandons it again. A landing put back before
that tick reads as one nothing moved under, since nothing durable could record
the movement.

A snapshot nobody could take is the git owner's to answer, and its answer is
an abort that resets the checkout onto the anchor and clears the attempt
(`git/base_sync/snapshot.py`). Where that reset landed, the recovery itself has
moved the checkout off the landed head, and nothing is left to route the
transaction, so it is abandoned behind the abort
(`abandons_behind_the_reset`); where the reset failed, the attempt and every
record stand, nothing was read moving, and the transaction waits for the next
proof. An abandonment behind a landed reset that cannot itself land is logged
and leaves the transaction pending beside a cleared attempt, with the checkout
reset off its head, so the reconciliation's proof of it defers until something
puts the checkout back. A checkout nobody could read beside a remote it
disagrees with abandons the transaction all the same, since every road that
snapshot takes resets the checkout off the head itself.

Only a transaction about the head the attempt's finish announced
(`pending_auto_base_rebase_announced_sha`) is read: a finish records evidence
only behind the checkpoint that writes that mark, and while the attempt stands
nothing else records evidence for the head. The mark is read before the
snapshot (`announced`), since an abort clears it with the attempt.
"""
from __future__ import annotations

import logging
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

log = logging.getLogger("orchestrator.workflow")


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
    if not abandons(context, _AutoRebaseRecoverySnapshot(branch=branch, local_head=""), head=head):
        log.error(
            "issue=#%d the verification evidence captured for %.8s could not be abandoned behind the reset that "
            "took the checkout off it; it stays recorded beside a cleared attempt",
            context.issue.number, head,
        )


def abandons_off_the_landing(context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot) -> bool:
    """Abandon the transaction captured for the announced head unless `snapshot` reads both heads on it; may it go on.

    Asked by the recovery's coordinator of every snapshot it reads, before
    the road the snapshot chooses is taken; a remote and a checkout both on
    the announced head are the landed road's to finish, which reads them
    again itself. False only where a transaction still stands that the
    abandonment could not retire, logged: the coordinator then holds the tick
    rather than take a road that would leave it behind.
    """
    head = announced(context)
    if not head or (snapshot.local_head, snapshot.remote_head) == (head, head):
        return True
    if abandons(context, snapshot):
        return True
    log.warning(
        "issue=#%d holding the recovery of %.8s: the verification evidence captured for it could not be "
        "abandoned yet, so nothing is reset, cleared, or parked until a later tick abandons it",
        context.issue.number, head,
    )
    return False


def abandons(
    context: _AutoRebaseRecoveryContext,
    snapshot: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate | None = None,
    *,
    head: str = "",
) -> bool:
    """Abandon what an earlier finish recorded for the announced head the landing was read leaving; whether none stands.

    `candidate` is the checkout as the caller already read it, read here
    where the caller has none, and `head` the announced head where the
    comment no longer carries the mark. The landing is handed, named against the
    announced head, to the last word behind the evidence step
    (`rewrite_finish_captured.stands_before_the_route`) with the movement
    already read (`rewrite_evidence_proof.LEFT_THE_LANDING`), however its own
    readings come out -- the heads may be back by then -- so it abandons the
    transaction unrun, or, with no room for that, refuses it for good. Nothing
    is routed either way, and nothing is read or written where no transaction
    is recorded for that head. False where one is still recorded once that
    write was asked: a comment nobody could read again, or a write refused or
    never confirmed.
    """
    landed = head or announced(context)
    if not landed:
        return True
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
    if _captured.recorded(finish, logged=False) is None:
        return True
    _captured.stands_before_the_route(finish, proof=LEFT_THE_LANDING)
    return _captured.recorded(finish, logged=False) is None
