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
issue and pinned comment read afresh: its whole binding
(`rewrite_evidence_proof.proves_again`) -- the pull request, the remote branch
and the checkout still on the head, the configuration it was recorded under,
the review subject and settled report it answers for, and the issue's
requirements. A record something moved under since is a decision no route may
take, so it is abandoned into history (`verification_carries.abandons`, a
carry's approval with it) in the evidence write ahead of the route, and the
head goes to the fresh reviewer, which owes the evidence: no rerun, since the
run was captured, and no carry made again. A reading nobody could take holds
the route, and so does an abandonment the pinned comment has no room for. A
record that proves is held once more to the last word behind every request
(below), and then routed only while the comment still carries every record it
is bound through: the retirement behind the route is decided on them
(`rewrite_finish_writes.FINISH`), so a review that moved while the proof ran
refuses the route, and the next finish proves the record against it.

An abandoned record stays this landing's captured run (`retired`): it is in
the evidence history with its whole binding, so a finish whose route the
abandonment stopped short of is followed by one that still decides nothing
afresh and runs nothing again.

Every route the evidence step takes -- these, a recorded failure notice's, and
a fresh decision's once written -- ends in the last word behind every request
made for it (`stands_before_the_route`, over
`rewrite_evidence_proof.last_word`): a landing that moved, or a base gone
elsewhere or unreadable, holds the route, and a transaction the route would
carry is abandoned, unrun, where its binding is refused there or the landing
moved under it.

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
    rewrite_finish_writes as _writes,
    verification_carries as _carries,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_evidence_proof import LEFT_THE_LANDING, last_word, proves_again
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish

log = logging.getLogger("orchestrator.workflow")

_ADVANCED = "the base advanced past the head it was recorded for"


def recorded(finish: LandedFinish, *, logged: bool = True) -> _records.PendingEvidence | None:
    """The transaction a finish of this landing recorded for its head, or None; logged where there is one."""
    pending = _record_state.read_pending_evidence(finish.state)
    if pending is None or pending.binding.target.target_head != finish.head:
        return None
    if logged:
        log.info(
            "issue=#%d finds verification evidence revision %d an earlier finish recorded for %.8s",
            finish.issue.number, pending.revision, finish.head,
        )
    return pending


def retired(finish: LandedFinish) -> bool:
    """Whether an earlier finish of this landing recorded a transaction for its head that has since been retired.

    Read off the evidence history, which keeps every retired record's whole
    binding: a transaction a finish abandoned because something moved under
    it is a run or carry this landing already captured, so a later finish
    whose route that abandonment stopped short of decides nothing afresh and
    runs nothing again. Logged where there is one; a history nobody can read
    says nothing either way.
    """
    about_the_head = (
        entry for entry in _settlement.read_evidence_history(finish.state) or ()
        if entry.binding.target.target_head == finish.head
    )
    entry = next(about_the_head, None)
    if entry is not None:
        log.info(
            "issue=#%d already retired verification evidence revision %d recorded for %.8s (%s); "
            "running nothing again, and the fresh reviewer owes the evidence",
            finish.issue.number, entry.revision, finish.head, entry.retired.value,
        )
    return entry is not None


def proved_again(
    finish: LandedFinish, staged: PinnedState, pending: _records.PendingEvidence,
) -> FinishOutcome | None:
    """Prove `pending` again over what `finish` reads; None to go on, its abandonment staged where refused.

    The binding is proved over the issue and pinned comment read afresh
    (`rewrite_evidence_proof.proves_again`). A reading nobody could take holds
    the route, as does a refusal whose abandonment `staged` has no room for;
    any other refusal abandons it, and the fresh reviewer owes the evidence. A
    record that proves goes on to the last word every route of the evidence
    step takes (`stands_before_the_route`), behind whatever is written first.
    """
    found = proves_again(finish, pending.binding)
    if found.proved:
        return None
    if found.holds:
        log.warning(
            "issue=#%d holding the route of %.8s: verification evidence revision %d could not be proved again (%s)",
            finish.issue.number, finish.head, pending.revision, found.refusal,
        )
        return FinishOutcome.HELD
    return None if _abandons(finish, staged, pending, found.refusal) else FinishOutcome.HELD


def stands_before_the_route(finish: LandedFinish, *, landing: bool = True) -> FinishOutcome | None:
    """The last word on `finish`'s route, behind every request its evidence step made; None to route.

    Asked on every route the step takes -- a fresh or carried decision once
    its write and any failure notice are behind it, a captured transaction
    proved again, a recorded failure notice published, an abandoned
    transaction -- over the transaction the route would carry, where one is
    still recorded for the head (`rewrite_evidence_proof.last_word`). The
    landing itself is read again for every route that carries or follows a
    recorded decision or ran the configured commands, `landing` False sparing
    only a fresh decision that ran nothing and recorded nothing. A landing
    that moved, or a base gone elsewhere or unreadable, holds the route with
    the attempt standing, so the next tick classifies the branch
    and counts the head again. A transaction the last word refuses is
    abandoned first, in its own evidence write, where the refusal is its
    binding's -- requirements, configuration, or a base no longer the tip its
    replay was made onto -- or the landing's, which no later route can take it
    over; a base that is only gone elsewhere keeps it, for the next tick's
    continued rebase to set aside. Nothing runs again.
    """
    pending = recorded(finish, logged=False)
    binding = None if pending is None else pending.binding
    refused = last_word(finish, binding, landing=landing or binding is not None)
    if refused is None:
        return None
    if pending is not None and (refused is LEFT_THE_LANDING or not refused.holds):
        staged = _writes.staging(finish)
        if not _abandons(finish, staged, pending, refused.refusal):
            return FinishOutcome.HELD
        stopped = _writes.lands(finish, staged, _writes.EVIDENCE)
        if stopped is not None:
            return stopped
    if not refused.holds:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s behind its evidence step: %s",
        finish.issue.number, finish.head, refused.refusal,
    )
    return FinishOutcome.HELD


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
