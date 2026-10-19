# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The transaction a landed rewrite's finish captured, proved or abandoned where a recovery keeps or drops its attempt.

A recovery park that keeps the attempt -- a reset that did not land, an ineligible label, a landing made for another
publication or one its record does not account for -- keeps the evidence for the reply that brings the recovery back, so
the git owner proves it again before every such park (`rewrite_landing_retirement.retires_unproved`): the transaction
over the issue and comment read afresh, held to the last word (`proves_captured`) with no fetch an abort could not take,
and abandoned where anything it rests on moved, a configuration or pull request repointed among the reasons, so putting
that back revives nothing; one still proving, or held only by an unread reading, stays for that finish. A snapshot
reading the landing off the head (`rewrite_landing_moved`) hands the proof that movement as already read.

A reset alone moves the checkout off the landed head, and the git owner's park behind it drops the attempt in one write
(`git/base_sync/persistence._reset_clear_and_park`). `abandons_over_the_reset`, the transaction's half of the answer
staged on that state once the reset landed (`rewrite_landing_retirement.retires_over_the_reset`, the context's
`settles_over_a_reset`), makes it go with the attempt's release or neither go; a failed park or reset keeps both.

Only a transaction a finish of the attempt recorded is read (`rewrite_landing_records.captured`): the one under the
receipt that finish put on the attempt (`pending_auto_base_rebase_evidence_receipt`) or, for an attempt older than that
receipt, one about the head its announcement mark names; the replay the attempt's record names says nothing either way.
Any other pending transaction is another road's, kept as it wrote it with its revision floor. Settled evidence
(`rewrite_landing_records.settled`) is the attempt's where it settled under that receipt or is about the head its record
or mark names: the anchor keeps every other road off that head's evidence while the attempt stands. The finish built
only for the recovery's proofs (`_finish`) is held to the settled-evidence policy (`LandedFinish.proves_settled`)
whatever policy the routing finish selects, so what they retire is read as that policy reads it.
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
    asked before the attempt is dropped from `context.state`: the reset took the checkout off the landed head, movement
    under the transaction, whose abandonment lands with the attempt's release or not at all, so no cleared attempt
    leaves it for the reconciliation to settle. With no room for its history entry it is dropped and refused for good
    (`rewrite_finish_captured`), the attempt's base tip blanked with it, so where the attempt outlives that write every
    later reading of the base proves nothing (`rewrite_evidence_proof.standing_refusal`). `why` names the write, logged.
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

    Over the landing as `snapshot` read it. The binding is proved again over the issue and comment read afresh
    (`rewrite_finish_captured.proved_again`) and held to the last word (`rewrite_evidence_proof.last_word`), neither
    needing a fetch; where either reads movement the last word abandons the transaction unrun -- or, with no room,
    refuses it for good, or invalidates another finish's settlement of it, taking in that finish's announcement.
    `moved`, movement the caller already read under it, stands as that proof however soon it is put back. `asks`,
    from the proof before a park (`rewrite_landing_retirement.retires_unproved`), is asked of every comment read.
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

    Still recorded -- the abandonment not landed, a successor or an unread comment among the reasons -- or settled by
    another finish meanwhile, its invalidation (`rewrite_finish_captured.stands_before_the_route`) not landed and the
    movement recorded instead: either way the caller holds.
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
