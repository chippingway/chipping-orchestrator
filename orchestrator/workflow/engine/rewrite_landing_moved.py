# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence a landed rewrite's finish captured or settled, retired wherever its recovery reads the landing moved.

A finish that recorded the landed head's evidence transaction and stopped
short of its route leaves it pending beside the attempt
(`rewrite_finish_captured`), and one that settled it and then died in the
tail of its route -- before the announcement, the relabel, or the retirement
-- leaves it current beside the attempt (`rewrite_landing_records.settled`).
Only the recovery of the push already landed -- over a remote and a checkout
both still on that head -- may take the route either carries
(`rewrite_landed`). Every other road the recovery is sent down
reads the landing somewhere else and clears, resets, or parks the attempt
without that route: an unmoved checkout back on the anchor, a remote that is
not on the checkout -- rolled back, or moved out of band -- and a remote and
checkout that agree on another head. These are the helpers that abandon the
transaction, and invalidate the settled evidence into history whole
(`rewrite_finish_readiness.invalidates`), before any such road is taken, so
that movement under a decision leaves no decision a later route, or a reader
once the attempt is cleared, may take. The recovery's coordinator
(`rewrite_recovery`) asks them of every snapshot before the road it chooses,
and the landed road (`rewrite_landed`) of a checkout or remote it reads
leaving the head.

`abandons_off_the_landing` answers whether a road may go on: True where the
snapshot reads no head off the head a finish captured or settled evidence
for, or where nothing for that head stands once its retirement was asked
(`abandons`), and False where evidence still stands that no write could
retire, for the coordinator to hold the tick with nothing reset, cleared, or
parked. A head the snapshot could
not read -- a checkout whose head would not prove, or a remote not yet read --
establishes no movement, so the evidence is kept: the road such a snapshot
takes resets the checkout, and that reset, once it lands, is the movement the
retirement answers (`rewrite_landing_retirement.retires_over_the_reset`),
while one that fails keeps the attempt and the evidence both. `abandons`
hands the landing, named against a transaction's head, to the last word
(`rewrite_finish_captured.stands_before_the_route`) with the movement already
read (`rewrite_evidence_proof.LEFT_THE_LANDING`), however its own readings
come out -- the heads may be back by then -- so the transaction is abandoned
unrun, or refused for good where the comment has no room for that. The
abandonment is a write of its own over the comment read afresh, landed over
the tick's own reading where that write does not land; only where no write
lands at all is the transaction still standing -- save one another finish
settled while its abandonment was asked, whose settlement the last word
invalidates over the movement already read, a successor under another
receipt kept as its road wrote it. Settled evidence the
snapshot reads the landing leaving is invalidated the same way, whatever is
read next, in a write over the comment read afresh that falls back to the
tick's own reading too, and holds the tick only where neither lands.

A recovery park that keeps the attempt keeps the evidence with it, for the
human reply that brings the recovery back: a reset that did not land, an issue
relabelled out of the stages the refresh drives, a landing made for another
publication or one its record does not account for. What such a park read is
put right by a human, and the reply then finishes the landing, so the git
owner has the evidence proved again before every such park
(`rewrite_landing_retirement.retires_unproved`): the transaction over the
issue and comment read afresh, held to the last word (`proves_captured`),
none of it needing the fetch an abort could not take, and abandoned now where
anything it rests on moved, a configuration or a pull request repointed among
the reasons, so putting that back before the reply revives nothing. One that
still proves, or that only a reading nobody could take holds, is kept for
that finish.

A reset is the one road that moves the checkout off the landed head itself,
and the git owner's park behind it drops the attempt in one write
(`git/base_sync/persistence._reset_clear_and_park`).
`abandons_over_the_reset` is the transaction's half of the answer that owner
stages on that very state once the reset landed
(`rewrite_landing_retirement.retires_over_the_reset`, the recovery context's
`settles_over_a_reset`), so the transaction goes with the attempt's release
or neither goes: a park write that fails leaves both standing, and a reset
that failed moved nothing and keeps both.

Only a transaction a finish of the attempt recorded is read
(`rewrite_landing_records.captured`): the one under the receipt the finish put
on the attempt in the very write that recorded it
(`pending_auto_base_rebase_evidence_receipt`), or -- for an attempt from
before that receipt existed, whose finish recorded evidence only behind its
announcement mark -- one about the head that mark names. A finish resolves
the landed head's evidence before it announces it, so no mark need be down,
and the replay the attempt's record names -- written before the push, or not
yet written in the window git leaves -- says nothing either way. Any other
pending transaction was recorded by another road -- a newer head it
published, or a newer record about the same one -- and is kept as that road
wrote it, with its revision floor, whatever this recovery reads, on every road
it takes. Settled evidence is the attempt's where it settled under that
receipt, or is about the head the attempt's record or mark names
(`rewrite_landing_records.settled`): the anchor keeps every other road off
that head's evidence while the attempt stands.
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
    rewrite_finish_readiness as _readiness,
    rewrite_landing_records as _landing_records,
    verification_carries as _carries,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_evidence_proof import LEFT_THE_LANDING, Asks, last_word
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad, LandedFinish

log = logging.getLogger("orchestrator.workflow")

_RELEASED = "in the write that releases its attempt behind the reset that took the checkout off it"

_CHECKOUT_GONE = "in the write that parks its attempt, the checkout it was captured on gone"


def abandons_over_the_reset(context: _AutoRebaseContext | _AutoRebaseRecoveryContext, why: str = _RELEASED) -> None:
    """Stage the abandonment of what a finish captured for the landed head on the state a landed reset's park writes.

    The transaction's half of the recovery's answer to a reset
    (`rewrite_landing_retirement.retires_over_the_reset`), asked once the
    reset landed and before the attempt is dropped from `context.state`: the
    reset took the checkout off the landed head, which is movement under the
    transaction. Staged on the state the park then lands, the abandonment
    lands with the attempt's release or not at all, so no cleared attempt
    leaves the transaction behind it for the reconciliation to settle once
    the checkout is put back. With no room
    for its history entry, the transaction is dropped instead and refused for
    good, as the finish's own abandonment refuses one (`rewrite_finish_captured`):
    the base tip the attempt recorded its replay as made onto is blanked with
    it, so where the attempt outlives that write -- the park over a checkout
    gone from disk keeps it -- every later reading of the base proves nothing
    (`rewrite_evidence_proof.standing_refusal`), and no finish of this landing
    runs or carries the evidence again, with neither the transaction nor its
    history entry left to say a run was captured. A reset's release drops the
    tip with the attempt either way. `why` names the write it rides, logged.
    """
    pending = _landing_records.captured(context.state)
    if pending is None:
        return
    head = pending.binding.target.target_head
    log.info(
        "issue=#%d abandoning verification evidence revision %d recorded for %.8s, %s",
        context.issue.number, pending.revision, head, why,
    )
    if not _carries.abandons(context.state, pending):
        context.state.set(_records.PENDING_EVIDENCE, None)
        context.state.set(_base_sync_state._PENDING_REWRITE_BASE, None)


def abandons_off_the_landing(context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot) -> bool:
    """Retire what a finish captured or settled for the landed head where `snapshot` reads a head off it; may it go on.

    Asked by the recovery's coordinator of every snapshot it reads, before
    the road the snapshot chooses is taken; a remote and a checkout both on
    the head the evidence answers for are the landed road's to finish, which
    reads them again itself. A head the snapshot holds as "" is one nobody
    read, which establishes no movement, so the evidence is kept for a reset
    that lands to retire (`rewrite_landing_retirement.retires_over_the_reset`).
    False only where evidence still stands that the abandonment or
    invalidation could not retire, logged: the coordinator holds the tick
    then rather than take a road that would leave it behind.
    """
    recorded = (_landing_records.captured(context.state), _landing_records.settled(context.state))
    heads = [record.binding.target.target_head for record in recorded if record is not None]
    read = {snapshot.local_head, snapshot.remote_head}
    moved = any(read - {"", head} for head in heads)
    if not moved or abandons(context, snapshot):
        return True
    log.warning(
        "issue=#%d holding the recovery of %.8s: the verification evidence captured or settled for it could not "
        "be retired yet, so nothing is reset, cleared, or parked until a later tick retires it",
        context.issue.number, heads[0],
    )
    return False


def abandons(
    context: _AutoRebaseRecoveryContext,
    snapshot: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate | None = None,
) -> bool:
    """Retire what an earlier finish recorded or settled for the head the landing was read leaving; whether none stands.

    `candidate` is the checkout as the caller already read it, read here
    where the caller has none. A transaction recorded for the head is handed,
    with the landing named against that head, to the last word behind the
    evidence step (`rewrite_finish_captured.stands_before_the_route`) with the
    movement already read (`rewrite_evidence_proof.LEFT_THE_LANDING`), however
    its own readings come out -- the heads may be back by then -- so it
    abandons the transaction unrun, or, with no room for that, refuses it for
    good -- or invalidates the settlement another finish made of it while that
    was asked. Evidence a finish already settled for the head is invalidated
    into history the same way, whatever is read next
    (`rewrite_finish_readiness.invalidates`), so putting the landing back
    revives no decision taken over it. Nothing is routed either way, and
    nothing is read or written where neither stands. False where either still
    stands once its write was asked: a write refused or never confirmed, over
    a comment nobody could read again as well as over the tick's own reading.
    """
    pending = _landing_records.captured(context.state)
    if pending is not None:
        finish = _finish(context, pending.binding.target.target_head, snapshot, candidate)
        _captured.stands_before_the_route(finish, proof=LEFT_THE_LANDING)
        if _stands(finish, pending):
            return False
    settled = _landing_records.settled(context.state)
    if settled is None:
        return True
    finish = _finish(context, settled.binding.target.target_head, snapshot, candidate)
    return _readiness.invalidates(finish, settled)


def proves_captured(
    context: _AutoRebaseRecoveryContext,
    snapshot: _AutoRebaseRecoverySnapshot,
    moved: ReportEvidence | None = None,
    *,
    asks: Asks | None = None,
) -> bool:
    """Prove the transaction a finish captured for the landed head, abandoning it where it moved; whether none stands.

    Over the landing as `snapshot` read it, a checkout with no head read
    among it. The transaction's binding is proved again over the issue and
    comment read afresh (`rewrite_finish_captured.proved_again`) and held to
    the last word beside it (`rewrite_evidence_proof.last_word`), neither of
    which needs the fetch a failed abort could not take; where either reads
    movement, the transaction is abandoned unrun -- or, with no room, refused
    for good, or its settlement another finish made meanwhile invalidated --
    through the last word with that movement as its proof.
    `moved` is movement the caller already read under the transaction -- a
    record a park's own commit adopted while its notice was posted -- which
    stands as that proof in place of the proof read again, so no reading taken
    now hides it by finding it put back. An announcement another finish put
    on the attempt beside that settlement is taken in. `asks`, which the
    recovery's proof before a park hands in
    (`rewrite_landing_retirement.retires_unproved`), is asked of every comment
    the proof and the last word read, under the transaction's receipt, so a
    base tip read blank or repointed there moves it however soon it is put
    back.
    """
    pending = _landing_records.captured(context.state)
    if pending is None:
        return True
    finish = _finish(context, pending.binding.target.target_head, snapshot, None)
    proof = moved or _captured.proved_again(finish, pending, asks)
    moved = last_word(
        finish,
        pending.binding,
        earlier=proof,
        records=None if asks is None else (
            lambda state, _issue: (asks(state, pending.receipt),)
        ),
    )[0]
    if moved is None:
        return True
    _captured.stands_before_the_route(finish, proof=moved)
    return not _stands(finish, pending)


def _stands(finish: LandedFinish, pending: _records.PendingEvidence) -> bool:
    """Whether anything of `pending` stands once the last word asked its abandonment; logged where it does.

    Still recorded -- no write landed the abandonment, a successor settled
    under another receipt meanwhile or a comment nobody could read among the
    reasons -- or settled by another finish while it was asked and taken in
    with the invalidation the last word made over the movement
    (`rewrite_finish_captured.stands_before_the_route`) not landed, the
    movement recorded against it instead: either way the caller holds.
    """
    current = _settlement.read_current_evidence(finish.state)
    settled = current is not None and current.receipt == pending.receipt
    if not settled and _captured.recorded(finish, logged=False) is None:
        return False
    log.warning(
        "issue=#%d verification evidence revision %d captured for %.8s still stands behind its abandonment",
        finish.issue.number, pending.revision, finish.head,
    )
    return True


def _finish(
    context: _AutoRebaseRecoveryContext,
    head: str,
    snapshot: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate | None,
) -> LandedFinish:
    """The finish of `head`'s landing as `snapshot` read it, over `candidate` or the checkout read now."""
    read = candidate or _recovery_push._recovered_candidate(context, snapshot)
    return LandedFinish(
        gh=context.gh,
        spec=context.spec,
        issue=context.issue,
        state=context.state,
        landed=_LandedRewrite(
            candidate=replace(read, checkout=replace(read.checkout, head=head)),
            outcome=_PushOutcome.OBSERVED,
            remote=_RefRead(sha=snapshot.remote_head),
        ),
        label=_replay_evidence._recovered_stage(context.label),
        road=FinishRoad.RECOVERY,
    )
