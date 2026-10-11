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

A reset is the one road that moves the checkout off the landed head itself:
the git owner's park behind a snapshot nobody could take, and every other
road's that resets, drops the attempt in one whole write of the issue's state
(`git/base_sync/persistence._reset_clear_and_park`). The recovery hands that
owner its answer to the movement (`abandons_over_the_reset`), which stages the
abandonment on the very state the park writes once the reset landed, so the
transaction goes with the attempt's release or neither goes: a park write that
fails leaves both standing for the next recovery, and a reset that failed
moved nothing and keeps both. A checkout nobody could read beside a remote it
disagrees with abandons the transaction all the same, since every road that
snapshot takes resets the checkout off the head itself.

Only a transaction about the head the attempt's finish announced
(`pending_auto_base_rebase_announced_sha`) is read: a finish records evidence
only behind the checkpoint that writes that mark, and while the attempt stands
nothing else records evidence for the head.
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
from orchestrator.workflow.engine import (
    rewrite_finish_captured as _captured,
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import LEFT_THE_LANDING
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad, LandedFinish

log = logging.getLogger("orchestrator.workflow")


def announced(context: _AutoRebaseRecoveryContext) -> str:
    """The head the attempt's finish announced, or ""."""
    return context.state.get(_base_sync_state._PENDING_ANNOUNCED_SHA) or ""


def abandons_over_the_reset(context: _AutoRebaseRecoveryContext) -> None:
    """Stage the abandonment of what a finish captured for the announced head on the state a landed reset's park writes.

    The recovery's answer to a reset (`_AutoRebaseRecoveryContext.settles_over_a_reset`),
    asked by the git owner once the reset landed and before the attempt is
    dropped from `context.state`: the reset took the checkout off the landed
    head, which is movement under the transaction. Staged on the state the
    park then writes whole, the abandonment lands with the attempt's release
    or not at all, so no cleared attempt leaves the transaction behind it for
    the reconciliation to settle once the checkout is put back. With no room
    for its history entry, the transaction is dropped instead.
    """
    head = announced(context)
    pending = _record_state.read_pending_evidence(context.state)
    if not head or pending is None or pending.binding.target.target_head != head:
        return
    log.info(
        "issue=#%d abandoning verification evidence revision %d recorded for %.8s, in the write that releases "
        "its attempt behind the reset that took the checkout off it",
        context.issue.number, pending.revision, head,
    )
    if not _carries.abandons(context.state, pending):
        context.state.set(_records.PENDING_EVIDENCE, None)


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
) -> bool:
    """Abandon what an earlier finish recorded for the announced head the landing was read leaving; whether none stands.

    `candidate` is the checkout as the caller already read it, read here
    where the caller has none. The landing is handed, named against the
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
    landed = announced(context)
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
