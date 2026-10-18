# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The transaction a landed rewrite's finish captured, proved or abandoned where a recovery keeps or drops its attempt.

A recovery park that keeps the attempt keeps the evidence with it, for the human reply that brings the recovery back: a
reset that did not land, an issue relabelled out of the stages the refresh drives, a landing made for another
publication or one its record does not account for. A human puts right what such a park read, and the reply then
finishes the landing, so the git owner has the evidence proved again before every such park
(`rewrite_landing_retirement.retires_unproved`): the transaction over the issue and comment read afresh, held to the
last word (`proves_captured`), none of it needing the fetch an abort could not take, and abandoned now where anything it
rests on moved, a configuration or a pull request repointed among the reasons, so putting that back before the reply
revives nothing. One that still proves, or that only a reading nobody could take holds, is kept for that finish. A
snapshot that read the landing off the head hands the same proof that movement as already read
(`rewrite_landing_moved`).

A reset is the one road that moves the checkout off the landed head itself, and the git owner's park behind it drops the
attempt in one write (`git/base_sync/persistence._reset_clear_and_park`). `abandons_over_the_reset` is the transaction's
half of the answer that owner stages on that very state once the reset landed
(`rewrite_landing_retirement.retires_over_the_reset`, the recovery context's `settles_over_a_reset`), so the transaction
goes with the attempt's release or neither goes: a park write that fails leaves both standing, and a reset that failed
moved nothing and keeps both.

Only a transaction a finish of the attempt recorded is read (`rewrite_landing_records.captured`): the one under the
receipt the finish put on the attempt in the very write that recorded it (`pending_auto_base_rebase_evidence_receipt`),
or -- for an attempt from before that receipt existed, whose finish recorded evidence only behind its announcement
mark -- one about the head that mark names. A finish resolves the landed head's evidence before it announces it, so no
mark need be down, and the replay the attempt's record names -- written before the push, or not yet written in the
window git leaves -- says nothing either way. Any other pending transaction was recorded by another road -- a newer head
it published, or a newer record about the same one -- and is kept as that road wrote it, with its revision floor,
whatever this recovery reads, on every road it takes. Settled evidence is the attempt's where it settled under that
receipt, or is about the head the attempt's record or mark names (`rewrite_landing_records.settled`): the anchor keeps
every other road off that head's evidence while the attempt stands.

The finish built for the recovery's proofs alone, to retire or prove that evidence (`_finish`), is held to the
settled-evidence policy (`LandedFinish.proves_settled`) whichever policy the finish the recovery routes a landing
through selects, so what those proofs retire, a settlement another road made meanwhile, and a successor's own binding
are read as that policy reads them.
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
    rewrite_landing_records as _landing_records,
    verification_carries as _carries,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_evidence_proof import Asks, last_word
from orchestrator.workflow.engine.rewrite_finish_models import FinishRoad, LandedFinish

log = logging.getLogger("orchestrator.workflow")

_RELEASED = "in the write that releases its attempt, the checkout taken off it"

_CHECKOUT_GONE = "in the write that parks its attempt, the checkout it was captured on gone"


def abandons_over_the_reset(context: _AutoRebaseContext | _AutoRebaseRecoveryContext, why: str = _RELEASED) -> None:
    """Stage the abandonment of what a finish captured for the landed head on the state a landed reset's park writes.

    The transaction's half of the recovery's answer to a reset (`rewrite_landing_retirement.retires_over_the_reset`),
    asked once the reset landed and before the attempt is dropped from `context.state`: the reset took the checkout off
    the landed head, which is movement under the transaction. Staged on the state the park then lands, the abandonment
    lands with the attempt's release or not at all, so no cleared attempt leaves the transaction behind it for the
    reconciliation to settle once the checkout is put back. With no room for its history entry, the transaction is
    dropped instead and refused for good, as the finish's own abandonment refuses one (`rewrite_finish_captured`): the
    base tip the attempt recorded its replay as made onto is blanked with it, so where the attempt outlives that
    write -- the park over a checkout gone from disk keeps it -- every later reading of the base proves nothing
    (`rewrite_evidence_proof.standing_refusal`), and no finish of this landing runs or carries the evidence again, with
    neither the transaction nor its history entry left to say a run was captured. A reset's release drops the tip with
    the attempt either way. `why` names the write it rides, logged.
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


def proves_captured(
    context: _AutoRebaseRecoveryContext,
    snapshot: _AutoRebaseRecoverySnapshot,
    moved: ReportEvidence | None = None,
    *,
    asks: Asks | None = None,
) -> bool:
    """Prove the transaction a finish captured for the landed head, abandoning it where it moved; whether none stands.

    Over the landing as `snapshot` read it, a checkout with no head read among it. The transaction's binding is proved
    again over the issue and comment read afresh (`rewrite_finish_captured.proved_again`) and held to the last word
    beside it (`rewrite_evidence_proof.last_word`), neither of which needs the fetch a failed abort could not take;
    where either reads movement, the transaction is abandoned unrun -- or, with no room, refused for good, or its
    settlement another finish made meanwhile invalidated -- through the last word with that movement as its proof.
    `moved` is movement the caller already read under the transaction -- a record a park's own commit adopted while its
    notice was posted -- which stands as that proof in place of the proof read again, so no reading taken now hides it
    by finding it put back. An announcement another finish put on the attempt beside that settlement is taken in.
    `asks`, which the recovery's proof before a park hands in (`rewrite_landing_retirement.retires_unproved`), is asked
    of every comment the proof and the last word read, under the transaction's receipt, so a base tip read blank or
    repointed there moves it however soon it is put back.
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

    Still recorded -- no write landed the abandonment, a successor settled under another receipt meanwhile or a comment
    nobody could read among the reasons -- or settled by another finish while it was asked and taken in with the
    invalidation the last word made over the movement (`rewrite_finish_captured.stands_before_the_route`) not landed,
    the movement recorded against it instead: either way the caller holds.
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
        proves_settled=True,
    )
