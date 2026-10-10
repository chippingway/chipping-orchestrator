# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The evidence an earlier finish of a landing made durable, proved again before a later finish routes with it.

A finish that recorded the landed head's evidence transaction -- a fresh run of
the configured commands, or a carry onto the head -- and then stopped short of
its route leaves the attempt standing beside that record, and the recovery of
the push already landed finishes it on a later tick (`rewrite_finish_evidence`).
The record is a completed decision durably captured, so the commands are never
run for that landing again: it continues with its own transcript and its tested
and source provenance, or nothing continues. A finish that died before the
record landed -- before its commands ran, or after they completed -- captured
nothing, and the policy decides afresh, running them again where it runs them.

What a record continues on is proved again first (`proved_again`), over the
issue and pinned comment this finish reads: its whole binding
(`verification_proof.binding_verdict`) -- the pull request, the remote branch
and the checkout still on the head, the configuration it was recorded under,
the review subject and settled report it answers for, and the issue's
requirements. A record something moved under since is a decision no route may
take, so it is abandoned into history (`verification_carries.abandons`, a
carry's approval with it) in the evidence write ahead of the route, and the
head goes to the fresh reviewer, which owes the evidence: no rerun, since the
run was captured, and no carry made again. A reading nobody could take holds
the route, and so does an abandonment the pinned comment has no room for.

A head the base advanced past again is not routed at all: the caller's next
rebase replaces it. A record made for it is abandoned the same way
(`sets_aside`) before the attempt retires, so no decision about a head that
rebase replaces is settled as current behind it -- as the failure notice a
failed run recorded for it is cleared by that retirement
(`rewrite_finish_writes.retirement`).

Only a record about the landed head is read here: while the attempt stands the
anchor holds every other road, so nothing but a finish of this landing records
evidence for that head. Staged on the caller's copy; the caller's evidence
write (`rewrite_finish_writes.EVIDENCE`) lands it.
"""
from __future__ import annotations

import logging

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_carries as _carries,
    verification_proof as _proof,
    verification_record_state as _record_state,
    verification_records as _records,
)
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish

log = logging.getLogger("orchestrator.workflow")

_ADVANCED = "the base advanced past the head it was recorded for"


def recorded(finish: LandedFinish) -> _records.PendingEvidence | None:
    """The transaction an earlier finish of this landing recorded for its head, or None; logged where there is one."""
    pending = _record_state.read_pending_evidence(finish.state)
    if pending is None or pending.binding.target.target_head != finish.head:
        return None
    log.info(
        "issue=#%d finds verification evidence revision %d an earlier finish recorded for %.8s",
        finish.issue.number, pending.revision, finish.head,
    )
    return pending


def proved_again(
    finish: LandedFinish, staged: PinnedState, pending: _records.PendingEvidence,
) -> FinishOutcome | None:
    """Prove `pending` again over what `finish` reads; None to route the head, its abandonment staged where refused.

    PROVED routes the record as it was captured. A reading nobody could take
    holds the route, as does a refusal whose abandonment `staged` has no room
    for; any other refusal abandons it, and the fresh reviewer owes the
    evidence.
    """
    reading = _proof.ProofReading(finish.gh, finish.spec, finish.issue, finish.state)
    found = _proof.binding_verdict(reading, pending.binding)
    if found.proved:
        return None
    if found.holds:
        log.warning(
            "issue=#%d holding the route of %.8s: verification evidence revision %d could not be proved again (%s)",
            finish.issue.number, finish.head, pending.revision, found.refusal,
        )
        return FinishOutcome.HELD
    return None if _abandons(finish, staged, pending, found.refusal) else FinishOutcome.HELD


def sets_aside(finish: LandedFinish, staged: PinnedState) -> FinishOutcome | None:
    """Stage the abandonment of a record made for a landed head the base advanced past; HELD where it has no room."""
    pending = recorded(finish)
    if pending is None or _abandons(finish, staged, pending, _ADVANCED):
        return None
    return FinishOutcome.HELD


def _abandons(finish: LandedFinish, staged: PinnedState, pending: _records.PendingEvidence, why: str) -> bool:
    """Stage `pending`'s abandonment into history on `staged`; whether it fit, logged either way.

    Through the abandonment every transaction that will never settle takes
    (`verification_carries.abandons`), so a carry takes the approval of
    exactly the review it answers for with it, as the reconciliation's would.
    """
    if _carries.abandons(staged, pending):
        log.info(
            "issue=#%d abandoning verification evidence revision %d recorded for %.8s, running nothing again: %s",
            finish.issue.number, pending.revision, finish.head, why,
        )
        return True
    log.error(
        "issue=#%d holding the route of %.8s: the pinned comment has no room to abandon "
        "verification evidence revision %d (%s)",
        finish.issue.number, finish.head, pending.revision, why,
    )
    return False
