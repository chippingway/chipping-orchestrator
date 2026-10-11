# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed rewrite's finish captured, abandoned wherever its recovery reads the landing moved.

A finish that recorded the landed head's evidence transaction and stopped
short of its route leaves it pending beside the attempt
(`rewrite_finish_captured`), and only the recovery of the push already landed
-- over a remote and a checkout both still on that head -- may take the route
it carries (`rewrite_landed`). Every other road the recovery is sent down
reads the landing somewhere else and clears, resets, or parks the attempt
without that route: an unmoved checkout back on the anchor, a remote that is
not on the checkout -- rolled back, or moved out of band -- and a remote and
checkout that agree on another head. These are the helpers that abandon the
transaction before any such road is taken, so that movement under a decision
leaves no decision a later route, or the dispatcher's reconciliation once the
attempt is cleared, may take. They are dormant: the recovery
(`rewrite_recovery`, `rewrite_landed`) asks none of them yet, and no recovery
road hands the reset answer on.

`abandons_off_the_landing` answers whether a road may go on: True where the
snapshot reads no head off the announced head, or where nothing captured for
that head stands once the abandonment was asked (`abandons`), and False where
a transaction still stands that no write could retire, for the coordinator to
hold the tick with nothing reset, cleared, or parked. A head the snapshot could
not read -- a checkout whose head would not prove, or a remote not yet read --
establishes no movement, so the transaction is kept: the road such a snapshot
takes resets the checkout, and that reset, once it lands, is the movement the
abandonment answers (`abandons_over_the_reset`), while one that fails keeps the
attempt and the transaction both. `abandons` hands the
landing, named against the announced head, to the last word
(`rewrite_finish_captured.stands_before_the_route`) with the movement already
read (`rewrite_evidence_proof.LEFT_THE_LANDING`), however its own readings
come out -- the heads may be back by then -- so the transaction is abandoned
unrun, or refused for good where the comment has no room for that. The
abandonment is a write of its own over the comment read afresh, landed over
the tick's own reading where that write does not land; only where no write
lands at all is the transaction still standing.

A reset is the one road that moves the checkout off the landed head itself,
and the git owner's park behind it drops the attempt in one whole write of the
issue's state (`git/base_sync/persistence._reset_clear_and_park`).
`abandons_over_the_reset` is the answer that owner stages on that very state
once the reset landed (`_AutoRebaseRecoveryContext.settles_over_a_reset`), so
the transaction goes with the attempt's release or neither goes: a park write
that fails leaves both standing, and a reset that failed moved nothing and
keeps both.

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
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
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


def announced(context: _AutoRebaseContext | _AutoRebaseRecoveryContext) -> str:
    """The head the attempt's finish announced, or ""."""
    return context.state.get(_base_sync_state._PENDING_ANNOUNCED_SHA) or ""


def abandons_over_the_reset(context: _AutoRebaseContext | _AutoRebaseRecoveryContext) -> None:
    """Stage the abandonment of what a finish captured for the announced head on the state a landed reset's park writes.

    The recovery's answer to a reset (`_AutoRebaseRecoveryContext.settles_over_a_reset`),
    for the git owner to ask once the reset landed and before the attempt is
    dropped from `context.state`: the reset took the checkout off the landed
    head, which is movement under the transaction. Staged on the state the
    park then writes whole, the abandonment lands with the attempt's release
    or not at all, so no cleared attempt leaves the transaction behind it for
    the reconciliation to settle once the checkout is put back. With no room
    for its history entry, the transaction is dropped instead.
    """
    pending = _captured_for(context)
    if pending is None:
        return
    head = pending.binding.target.target_head
    log.info(
        "issue=#%d abandoning verification evidence revision %d recorded for %.8s, in the write that releases "
        "its attempt behind the reset that took the checkout off it",
        context.issue.number, pending.revision, head,
    )
    if not _carries.abandons(context.state, pending):
        context.state.set(_records.PENDING_EVIDENCE, None)


def abandons_off_the_landing(context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot) -> bool:
    """Abandon the transaction captured for the announced head where `snapshot` reads a head off it; may it go on.

    For the recovery's coordinator to ask of every snapshot it reads, before
    the road the snapshot chooses is taken; a remote and a checkout both on
    the announced head are the landed road's to finish, which reads them
    again itself. A head the snapshot holds as "" is one nobody read, which
    establishes no movement, so the transaction is kept for a reset that
    lands to abandon (`abandons_over_the_reset`). False only where a
    transaction still stands that the abandonment could not retire, logged:
    the coordinator is to hold the tick then rather than take a road that
    would leave it behind.
    """
    head = announced(context)
    if not head or not {snapshot.local_head, snapshot.remote_head} - {"", head}:
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
    if _captured_for(context) is None:
        return True
    landed = announced(context)
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
    _captured.stands_before_the_route(finish, proof=LEFT_THE_LANDING)
    return _captured.recorded(finish, logged=False) is None


def _captured_for(context: _AutoRebaseContext | _AutoRebaseRecoveryContext) -> _records.PendingEvidence | None:
    """The transaction `context`'s comment records for the head the attempt's finish announced, or None."""
    head = announced(context)
    pending = _record_state.read_pending_evidence(context.state)
    if not head or pending is None or pending.binding.target.target_head != head:
        return None
    return pending
