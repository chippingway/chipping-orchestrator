# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The transaction a landed rewrite's finish captured, proved or abandoned where a recovery keeps or drops its attempt.

A recovery park that keeps the attempt -- a reset that did not land, an issue relabelled out of the stages the refresh
drives, a landing made for another publication or one its record does not account for -- keeps the evidence for the
human reply that brings the recovery back to finish the landing once what the park read is put right, so the git owner
proves it again before every such park (`rewrite_landing_retirement.retires_unproved`): the transaction over the issue
and comment read afresh, held to the last word (`proves_captured`), with no fetch an abort could not take, and abandoned
now where anything it rests on moved, a configuration or pull request repointed among the reasons, so putting that back
before the reply revives nothing. One still proving, or held only by a reading nobody could take, stays for that finish.
A snapshot reading the landing off the head (`rewrite_landing_moved`) hands the proof that movement as already read.

A reset alone moves the checkout off the landed head itself, and the git owner's park behind it drops the attempt in one
write (`git/base_sync/persistence._reset_clear_and_park`). `abandons_over_the_reset`, the transaction's half of the
answer that owner stages on that state once the reset landed (`rewrite_landing_retirement.retires_over_the_reset`, the
recovery context's `settles_over_a_reset`), makes the transaction go with the attempt's release or neither go: a failed
park write leaves both, and a failed reset moved nothing and keeps both.

Only a transaction a finish of the attempt recorded is read (`rewrite_landing_records.captured`): the one under the
receipt that finish put on the attempt as it recorded it (`pending_auto_base_rebase_evidence_receipt`) or, for an
attempt older than that receipt whose finish recorded evidence only behind its announcement mark, one about the head
that mark names. A finish resolves the landed head's evidence before announcing it, so no mark need be down, and the
replay the attempt's record names -- written before the push, or not yet in the window git leaves -- says nothing either
way. Any other pending transaction is another road's, for a newer head it published or a newer record about the same
one, kept as that road wrote it with its revision floor whatever this recovery reads or road it takes. Settled evidence
(`rewrite_landing_records.settled`) is the attempt's where it settled under that receipt or is about the head its record
or mark names: the anchor keeps every other road off that head's evidence while the attempt stands.

The finish built only for the recovery's proofs (`_finish`), which retire or prove that evidence, is held to the
settled-evidence policy (`LandedFinish.proves_settled`) whatever policy the routing finish selects, so what those proofs
retire, a settlement another road made meanwhile, and a successor's own binding read as that policy reads them.
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
    the landed head, movement under the transaction. Staged on the state the park lands, the abandonment lands with the
    attempt's release or not at all, so no cleared attempt leaves the transaction for the reconciliation to settle once
    the checkout is put back. With no room for its history entry, the transaction is dropped and refused for good, as
    the finish's own abandonment refuses one (`rewrite_finish_captured`), and the base tip the attempt recorded its
    replay as made onto is blanked with it: where the attempt outlives that write -- the park over a checkout gone from
    disk keeps it -- every later reading of the base proves nothing (`rewrite_evidence_proof.standing_refusal`), and no
    finish of this landing runs or carries the evidence again, no transaction or history entry left to say a run was
    captured. A reset's release drops the tip with the attempt either way. `why`, logged, names the write it rides.
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
    beside it (`rewrite_evidence_proof.last_word`), neither needing the fetch a failed abort could not take; where
    either reads movement, the last word abandons the transaction unrun with that movement as its proof -- or, with no
    room, refuses it for good, or invalidates its settlement another finish made meanwhile, taking in an announcement
    that finish put on the attempt beside it. `moved`, movement the caller already read under the transaction -- a
    record a park's own commit adopted while its notice was posted -- stands as that proof in place of the one read
    again, so no reading taken now hides it by finding it put back. `asks`, handed in by the recovery's proof before a
    park (`rewrite_landing_retirement.retires_unproved`), is asked of every comment the proof and the last word read,
    under the transaction's receipt, so a base tip read blank or repointed there moves it however soon it is put back.
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
