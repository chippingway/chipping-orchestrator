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

What a record continues on is proved again first (`proved_again`), the verdict
handed to the last word below rather than acted on alone, over the
issue and pinned comment read afresh: its whole binding
(`rewrite_evidence_proof.proves_again`) -- the pull request, the remote branch
and the checkout still on the head, the configuration it was recorded under,
the review subject and settled report it answers for, and the issue's
requirements. A record something moved under since is a decision no route may
take, so it is abandoned into history (`verification_carries.abandons`, a
carry's approval with it) in its own write ahead of the route, and the
head goes to the fresh reviewer, which owes the evidence: no rerun, since the
run was captured, and no carry made again. A reading nobody could take holds
the route, and so does an abandonment the pinned comment has no room for. A
record that proves is held once more to the last word behind every request
(below), which reads the review and report records again and abandons it where
they moved while the proof ran, and then routed only while the comment still
carries every record it is bound through: the retirement behind the route is
decided on them (`rewrite_finish_writes.FINISH`), so a review that moved after
the last word refuses the route, and the next finish proves the record against
it.

An abandoned record stays this landing's captured run (`retired`): it is in
the evidence history with its whole binding, so a finish whose route the
abandonment stopped short of is followed by one that still decides nothing
afresh and runs nothing again.

Every route the evidence step takes that carries or follows a recorded
decision -- these, a recorded failure notice's, and a fresh decision's once
written, a hold for want of room to invalidate the current evidence included --
ends in the last word behind every request made for it
(`stands_before_the_route`, over `rewrite_evidence_proof.last_word`). Only a
fresh decision held before anything is written, which recorded nothing, ends
without it. A landing that moved, or a base gone elsewhere or unreadable, holds
the route, and a transaction the route would carry is abandoned, unrun,
wherever any reading there establishes movement -- its binding refused, the
review and report records the comment carries moved, the landing moved, or the
base read elsewhere -- however the readings beside it came out, so no later
route takes it even once everything is back where it was. The abandonment is
staged on the comment read afresh and committed guarded by that reading
(`_abandoned`), so a review, report, or approval another road wrote meanwhile
neither refuses it nor is written over. Where the comment has no room for the
abandonment, the transaction is dropped instead and the base tip its replay
was recorded as made onto blanked with it, in a write that only shrinks the
comment: every later reading of the base proves nothing, so no finish of this
landing runs or carries the evidence again or routes over it.

A head the base advanced past again is not routed at all: the caller's next
rebase replaces it. A record made for it is abandoned the same way
(`sets_aside`) before the attempt retires, so no decision about a head that
rebase replaces is settled as current behind it -- as the failure notice a
failed run recorded for it is cleared by that retirement
(`rewrite_finish_writes.retirement`).

Only a record about the landed head is read here: while the attempt stands the
anchor holds every other road, so nothing but a finish of this landing records
evidence for that head; a recovery that reads the landing moved before any
finish is reached abandons it through the same last word
(`rewrite_landing_moved`). A record set aside is staged on the caller's copy,
and the caller's evidence write (`rewrite_finish_writes.EVIDENCE`) lands it.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_carries as _carries,
    verification_durable as _durable,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_evidence_proof import last_word, proves_again
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish

log = logging.getLogger("orchestrator.workflow")

_ADVANCED = "the base advanced past the head it was recorded for"

# What an abandonment writes: the transaction, the history it enters, a carry's
# approval, and -- with no room for the entry -- the recorded base tip.
_ABANDONED = (*_carries.ABANDONS, _base_sync_state._PENDING_REWRITE_BASE)


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


def proved_again(finish: LandedFinish, pending: _records.PendingEvidence) -> ReportEvidence:
    """The proof of `pending` again over what `finish` reads, logged where it refuses; nothing is staged.

    The binding is proved over the issue and pinned comment read afresh
    (`rewrite_evidence_proof.proves_again`), and the verdict is handed to the
    last word the evidence step ends in (`stands_before_the_route`), behind
    whatever is written first -- or, with no room to write it, behind nothing
    -- which reads it beside everything else that moves.
    """
    found = proves_again(finish, pending.binding)
    if not found.proved:
        log.warning(
            "issue=#%d verification evidence revision %d recorded for %.8s does not prove again: %s",
            finish.issue.number, pending.revision, finish.head, found.refusal,
        )
    return found


def stands_before_the_route(
    finish: LandedFinish, *, landing: bool = True, proof: ReportEvidence | None = None,
) -> FinishOutcome | None:
    """The last word on `finish`'s route, behind every request its evidence step made; None to route.

    Asked on every route the step takes -- a fresh or carried decision once
    its write and any failure notice are behind it, a captured transaction
    proved again, a recorded failure notice published, an abandoned
    transaction -- over the transaction the route would carry, where one is
    still recorded for the head (`rewrite_evidence_proof.last_word`), beside
    `proof`, the verdict a captured transaction was just proved again with,
    or the movement a recovery already read leaving the landing.
    The landing itself is read again for every route that carries or follows
    a recorded decision or ran the configured commands, `landing` False
    sparing only a fresh decision that ran nothing and recorded nothing.

    Every reading is taken, and none masks another. Any that establishes
    movement -- a refusal of the transaction's binding, a landing off its
    head, a base read elsewhere -- abandons the transaction the route would
    carry, in its own write (`_abandoned`): a decision something
    moved under is no decision any later route may take, even one finding
    everything back where it was. Any reading nobody could take, a landing
    that moved, or a base gone elsewhere holds the route with the attempt
    standing, so the next tick classifies the branch and counts the head
    again; a transaction nothing established movement under is kept for that
    tick to prove again. Nothing runs again.
    """
    pending = recorded(finish, logged=False)
    moved, held = last_word(
        finish,
        None if pending is None else pending.binding,
        landing=landing or pending is not None,
        earlier=proof,
    )
    if pending is not None and moved is not None:
        stopped = _abandoned(finish, pending, moved.refusal)
        if stopped is not None:
            return stopped
    if held is None:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s behind its evidence step: %s",
        finish.issue.number, finish.head, held.refusal,
    )
    return FinishOutcome.HELD


def sets_aside(finish: LandedFinish, staged: PinnedState) -> FinishOutcome | None:
    """Stage the abandonment of a record made for a landed head the base advanced past; HELD where it has no room."""
    pending = recorded(finish)
    if pending is None or _abandons(finish, staged, pending, _ADVANCED):
        return None
    return FinishOutcome.HELD


def _abandoned(finish: LandedFinish, pending: _records.PendingEvidence, why: str) -> FinishOutcome | None:
    """Abandon `pending` in its own write, or refuse it for good where that has no room; None to go on.

    Staged on the pinned comment read afresh (`verification_durable`) rather
    than on the tick's copy, and committed guarded by that reading: whatever
    another road wrote meanwhile -- a review subject, a report, an approval of
    its own -- is the movement this answers or none of its business, so it
    neither refuses the abandonment nor is written over. Only a carry's own
    approval goes with it (`verification_carries.abandons`), and only while
    the comment still carries that approval; a comment that will not read
    again, or no longer records `pending`, abandons nothing and holds the
    route.

    A comment with no room for the abandonment's history entry still takes a
    write that only shrinks it, and that write refuses the transaction for
    good with the records it already carries. The transaction is dropped with
    no entry -- its artifact waits behind the standing anchor, so nothing was
    posted under it, and the revision floor it raised keeps its revision from
    being reused -- and the base tip the attempt recorded its replay as made
    onto (`pending_auto_base_rebase_rewrite_base`) is blanked with it. Every
    later reading of the base then proves nothing
    (`rewrite_evidence_proof.standing_refusal`, UNPROVEN), so no finish of
    this landing runs or carries the evidence again or routes a transaction
    over it, however the base, the landing, or the issue reads by then. The
    route is held behind that write.
    """
    durable, _moved = _durable.durable_comment(finish.gh, finish.issue, finish.state)
    if durable is None or _record_state.read_pending_evidence(durable) != pending:
        log.warning(
            "issue=#%d holding the route of %.8s: the pinned comment read again no longer records verification "
            "evidence revision %d to abandon (%s)",
            finish.issue.number, finish.head, pending.revision, why,
        )
        return FinishOutcome.HELD
    guard = _durable.guarded(durable, _ABANDONED, _attempts._ATTEMPT_KEYS)
    fits = _abandons(finish, durable, pending, why)
    if not fits:
        durable.set(_records.PENDING_EVIDENCE, None)
        durable.set(_base_sync_state._PENDING_REWRITE_BASE, None)
    refused = _durable.lands(finish.gh, finish.issue, finish.state, guard, durable)
    if refused is not None:
        log.warning(
            "issue=#%d holding the route of %.8s: abandoning verification evidence revision %d did not land (%s)",
            finish.issue.number, finish.head, pending.revision, refused.refusal,
        )
    return None if fits and refused is None else FinishOutcome.HELD


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
        "verification evidence revision %d (%s); dropping it with the base tip it rests on instead",
        finish.issue.number, finish.head, pending.revision, why,
    )
    return False
