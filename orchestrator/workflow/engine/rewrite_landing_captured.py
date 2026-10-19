# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The transaction a landed rewrite's finish captured, proved or abandoned where a recovery keeps or drops its attempt.

A recovery park that keeps the attempt -- a reset that did not land, an ineligible label, a landing made for another
publication or one its record does not account for -- keeps the evidence for the reply that brings the recovery back,
so the git owner proves it again first (`rewrite_landing_retirement.retires_unproved`): the transaction held to the
last word over the issue and comment read afresh (`proves_captured`), no fetch needed, and abandoned where anything
it rests on moved, so putting that back revives nothing. A snapshot reading the landing off the head
(`rewrite_landing_moved`) hands the proof that movement as already read.

A reset moves the checkout off the landed head, and the git owner's park behind it drops the attempt in one write
(`git/base_sync/persistence._reset_clear_and_park`); `abandons_over_the_reset` stages the transaction's abandonment
on that state (`rewrite_landing_retirement.retires_over_the_reset`), so both go or neither does.

Only a transaction a finish of the attempt recorded is read (`rewrite_landing_records.captured`): the one under the
attempt's receipt (`pending_auto_base_rebase_evidence_receipt`) or, for an older attempt, one about the head its
announcement mark names; any other is another road's, kept with its revision floor. Settled evidence
(`rewrite_landing_records.settled`) is the attempt's where it settled under that receipt or is about the head its
record or mark names. The finish built only for these proofs (`_finish`) is held to the settled-evidence policy
(`LandedFinish.proves_settled`) whatever policy the routing finish selects.
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

    The transaction's half of a landed reset's answer (`rewrite_landing_retirement.retires_over_the_reset`): abandoned
    on the state releasing the attempt, so it goes with that release or neither does; with no room it is dropped and
    refused for good, the base tip blanked, so later readings prove nothing. `why` names the write, logged.
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
    context: _AutoRebaseRecoveryContext, snapshot: _AutoRebaseRecoverySnapshot, moved: ReportEvidence | None = None,
    *, asks: Asks | None = None,
) -> bool:
    """Prove the transaction a finish captured for the landed head, abandoning it where it moved; whether none stands.

    Proved again over the issue and comment read afresh (`rewrite_finish_captured.proved_again`) and held to the last
    word (`rewrite_evidence_proof.last_word`), no fetch needed; movement abandons it unrun, refuses it with no room, or
    invalidates another finish's settlement. `moved`, already read, stands as proof; `asks` is asked of every reading.
    """
    pending = _landing_records.captured(context.state)
    if pending is None:
        return True
    finish = _finish(context, pending.binding.target.target_head, snapshot, None)
    proof = moved or _captured.proved_again(finish, pending, asks)
    moved = last_word(
        finish, pending.binding, earlier=proof, records=None if asks is None else (
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
    context: _AutoRebaseRecoveryContext, head: str, snapshot: _AutoRebaseRecoverySnapshot,
    candidate: _RewriteCandidate | None,
) -> LandedFinish:
    """The finish of `head`'s landing as `snapshot` read it, over `candidate` or the checkout read now."""
    read = candidate or _recovery_push._recovered_candidate(context, snapshot)
    return LandedFinish(
        gh=context.gh, spec=context.spec, issue=context.issue, state=context.state,
        landed=_LandedRewrite(
            candidate=replace(read, checkout=replace(read.checkout, head=head)),
            outcome=_PushOutcome.OBSERVED,
            remote=_RefRead(sha=snapshot.remote_head),
        ),
        label=_replay_evidence._recovered_stage(context.label),
        road=FinishRoad.RECOVERY, proves_settled=True,
    )
