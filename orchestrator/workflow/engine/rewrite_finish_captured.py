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
These helpers read, prove, and abandon such a record.

`recorded` reads the transaction about the landed head, and `retired` whether
one was recorded for it and has since been retired into the evidence history,
which keeps every retired record's whole binding: an abandoned record is
still this landing's captured run, so a finish behind the abandonment decides
nothing afresh and runs nothing again. `proved_again` proves what a record
continues on over the issue and pinned comment read afresh
(`rewrite_evidence_proof.proves_again`) -- the pull request, the remote branch
and the checkout still on the head, the configuration it was recorded under,
the review subject and settled report it answers for, and the issue's
requirements -- and hands its verdict on rather than acting on it alone.

`stands_before_the_route` is the last word behind every request a route made
(`rewrite_evidence_proof.last_word`), over the transaction the route would
carry, beside a verdict the caller already read it with and behind wherever
the route already stopped: the finish asks it at the end of its evidence step
and behind a park or a checkpoint the comment refuses (`rewrite_finish`) --
a finish held to the dormant settled-evidence policy ahead of the park a debt
with no room takes as well, and with the transaction proved again whole
first each time (`whole`), since nothing proved it since the requests the
finish made before -- and once more behind the publication and settlement of the transaction it
recorded where that left it owed or retired it (`rewrite_finish_settlement`),
so a record moved while the artifact was posted abandons the transaction
before anything announces or routes the head or the anchor goes. A transaction under which any reading establishes
movement -- its binding refused, the review and report records the comment
carries moved, the landing moved, or the base read elsewhere -- is abandoned
unrun, however the readings beside it came out, so no later route takes it
even once everything is back where it was; one recorded for a head the base
advanced past is abandoned the same way (`sets_aside`). A reading nobody
could take holds the route and keeps the transaction for a later proof.

The abandonment (`_abandoned`) is staged on the comment read afresh and
committed guarded by that reading, so a review, report, or approval another
road wrote meanwhile neither refuses it nor is written over -- only an attempt
put in place of the one the finish read does, since its records are none of
this transaction's to write; where that write does not land, it is staged on
the tick's own copy and landed as `rewrite_finish_writes.ABANDONMENT` instead,
which is decided on the attempt too. Through
`verification_carries.abandons`, a carry takes the approval of exactly the
review it answers for with it. Where the comment has no room for the
abandonment's history entry, the transaction is dropped instead and the base
tip its replay was recorded as made onto blanked with it, in a write that only
shrinks the comment: every later reading of the base proves nothing
(`rewrite_evidence_proof.standing_refusal`), so nothing could run or carry
the landing's evidence again or route over it. Every other record on the
comment stays as it reads. Under the dormant settled-evidence policy
(`rewrite_finish_models.LandedFinish.proves_settled`), an abandonment another
finish refused by settling that very transaction meanwhile retires the
settlement instead, taken in off the comment read afresh
(`verification_durable.takes_in_a_settlement`) and invalidated over what the
abandonment was asked on, so putting what moved back revives neither; a
successor settled under another receipt is kept as its road wrote it. Every
other finish holds the route there, the settlement left standing.

Only a record about the landed head is read here: while the attempt stands the
anchor holds every other road, so nothing but a finish of this landing records
evidence for that head. The recovery's answer to a landing read moving before
any finish is reached is `rewrite_landing_moved`, which abandons through the
same last word.
"""
from __future__ import annotations

import logging
from functools import partial

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_writes as _writes,
    rewrite_landing_records as _landing_records,
    verification_carries as _carries,
    verification_durable as _durable,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_evidence_proof import last_word, proves_again
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.rewrite_finish_readiness import invalidates

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
    runs nothing again. The history keeps only its latest entries, though, so
    one that records another road wrote since pushed out of it is read off
    the receipt the finish put on the attempt beside it instead
    (`rewrite_landing_records.capture_answered`) -- and current evidence an
    earlier finish settled for the head counts the same, so evidence the
    configuration has since moved past is invalidated with nothing run again.
    Logged where there is one; a history nobody can read says nothing either
    way.
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
        return True
    current = _settlement.read_current_evidence(finish.state)
    settled = current is not None and current.binding.target.target_head == finish.head
    if not settled and not _landing_records.capture_answered(finish.state):
        return False
    log.info(
        "issue=#%d already settled or retired the verification evidence it recorded for %.8s; "
        "deciding and running nothing again",
        finish.issue.number, finish.head,
    )
    return True


def proved_again(finish: LandedFinish, pending: _records.PendingEvidence) -> ReportEvidence:
    """The proof of `pending` again over what `finish` reads, logged where it refuses; nothing is staged.

    The binding is proved over the issue and pinned comment read afresh
    (`rewrite_evidence_proof.proves_again`), and the verdict is for the last
    word (`stands_before_the_route`, as `proof`), asked behind whatever the
    route writes first, which reads it beside everything else that moves.
    """
    found = proves_again(finish, pending.binding)
    if not found.proved:
        log.warning(
            "issue=#%d verification evidence revision %d recorded for %.8s does not prove again: %s",
            finish.issue.number, pending.revision, finish.head, found.refusal,
        )
    return found


def stands_before_the_route(
    finish: LandedFinish,
    *,
    landing: bool = True,
    proof: ReportEvidence | None = None,
    behind: FinishOutcome | None = None,
    whole: bool = False,
) -> FinishOutcome | None:
    """The last word on `finish`'s route, behind every request its evidence step made; None to route.

    Asked on every route an evidence step takes -- a fresh or carried
    decision once its write and any failure notice are behind it, a captured
    transaction proved again, a recorded failure notice published, an
    abandoned transaction -- and read over the transaction the route would
    carry, where one is still recorded for the head
    (`rewrite_evidence_proof.last_word`), beside `proof`, the verdict a
    captured transaction was just proved again with, or the movement a
    recovery already read leaving the landing. `whole` has a transaction
    recorded for the head proved again whole first (`proved_again`) where no
    `proof` was handed in, for a caller that has not proved it since its own
    requests were made -- the last word alone never reads the settled report
    again at its location, so an edit to it shows only to that proof. The
    landing itself is read again whenever a transaction is recorded,
    `landing` False sparing only a fresh decision that ran nothing and
    recorded nothing.
    `behind` is where the route already stopped -- a write that did not land,
    the checkpoint's among them, a hold for want of room, a failure notice
    nobody could confirm -- and is the answer whatever this reads: the last
    word is asked all the same over a transaction still recorded for the
    head, so one something moved under is abandoned behind any stop rather
    than left for a later route once the record moves back.
    With none recorded, a stop has nothing to abandon and nothing is read.

    Every reading is taken, and none nobody could take hides one that read
    movement. Any that establishes movement -- a refusal of the transaction's
    binding, a landing off its head, a base read elsewhere -- abandons the
    transaction the route would carry, in its own write (`_abandoned`): a
    decision something moved under is no decision any later route may take,
    even one finding everything back where it was -- nor, under the
    settled-evidence policy, is a settlement another finish made of it while
    that abandonment was asked, which is invalidated over the same movement
    instead. Any reading nobody could
    take, a landing that moved, or a base gone elsewhere holds the route with
    the attempt standing, so the next tick classifies the branch and counts
    the head again; a transaction nothing established movement under is kept
    for that tick to prove again. Nothing runs again.
    """
    pending = recorded(finish, logged=False)
    if pending is None and behind is not None:
        return behind
    if whole and pending is not None and proof is None:
        proof = proved_again(finish, pending)
    moved, held = last_word(
        finish,
        None if pending is None else pending.binding,
        landing=landing or pending is not None,
        earlier=proof,
    )
    stopped = None
    if pending is not None and moved is not None:
        stopped = _abandoned(finish, pending, moved.refusal)
    if stopped is None and held is not None:
        log.warning(
            "issue=#%d holding the route of %.8s behind its evidence step: %s",
            finish.issue.number, finish.head, held.refusal,
        )
        stopped = FinishOutcome.HELD
    return behind or stopped


def sets_aside(finish: LandedFinish) -> FinishOutcome | None:
    """Abandon a record made for a landed head the base advanced past, in its own write; None to go on.

    The same abandonment a movement read under the record takes
    (`_abandoned`), staged on the comment read afresh, so an approval or a
    review another road wrote meanwhile neither refuses it nor is written
    over; one that does not land, or that has no room and only refuses the
    record for good, holds the continuation with the attempt standing. Under
    the settled-evidence policy, a settlement another finish made of the
    record while that was asked is invalidated in its place, so the
    continuation carries none of the run, as it would carry none of a record
    abandoned.
    """
    pending = recorded(finish)
    return None if pending is None else _abandoned(finish, pending, _ADVANCED)


def _abandoned(finish: LandedFinish, pending: _records.PendingEvidence, why: str) -> FinishOutcome | None:
    """Abandon `pending` in its own write, or refuse it for good where that has no room; None to go on.

    Staged on the pinned comment read afresh (`verification_durable`) rather
    than on the tick's copy, and committed guarded by that reading: whatever
    another road wrote meanwhile -- a review subject, a report, an approval of
    its own -- is the movement this answers or none of its business, so it
    neither refuses the abandonment nor is written over. Only a carry's own
    approval goes with it (`verification_carries.abandons`), and only while
    the comment still carries that approval. The attempt is the one exception:
    the fresh comment has to carry the very attempt `finish` read, since a
    replacement attempt is none of this transaction's business, and its
    records -- the base tip its replay was made onto among them -- are never
    written over. Where that write does not land
    -- a comment that would not read again, a record moved under the write --
    the abandonment is staged on the tick's own copy instead and landed as
    `rewrite_finish_writes.ABANDONMENT`, decided only on the records it
    retires and the attempt, so one failed reading or one move does not leave
    the transaction standing for a later route to take once the landing is
    put back. Another finish that settled `pending` while this was asked
    refuses both, yet what this abandons it over was read under it all the
    same: a finish held to the settled-evidence policy takes in the evidence
    the comment read afresh carries current under `pending`'s receipt
    (`verification_durable.takes_in_a_settlement`) and invalidates it whole
    over that reading (`rewrite_finish_readiness.invalidates`), which lets the
    route go on as a landed abandonment does; where the comment has no room
    for that, the movement is recorded against it by blanking the base tip,
    and the route is held. Only where nothing lands is the route held with
    the transaction kept, logged: the comment taking no write at all,
    carrying another attempt -- which every write here is decided on -- or
    no longer recording `pending` with no settlement of it current that the
    policy takes in, a successor settled under another receipt kept as its
    road wrote it.

    A comment with no room for the abandonment's history entry still takes a
    write that only shrinks it, and that write refuses the transaction for
    good with the records it already carries. The transaction is dropped with
    no entry -- an artifact the finish already posted under its receipt is
    never settled once its record is gone, and the revision floor it raised
    keeps its revision from being reused -- and the base tip the attempt
    recorded its replay as made onto (`pending_auto_base_rebase_rewrite_base`)
    is blanked with it. Every later reading of the base then proves nothing
    (`rewrite_evidence_proof.standing_refusal`, UNPROVEN), so no finish of
    this landing runs or carries the evidence again or routes a transaction
    over it, however the base, the landing, or the issue reads by then. The
    route is held behind that write.
    """
    fits = None
    # The bound records another road moved are no refusal here; only the attempt is.
    durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    replaced = durable is None or _commit_models.PinnedCommit.capture(
        finish.state, prerequisites=_attempts._ATTEMPT_KEYS,
    ).moved(durable.data)
    if not replaced and _record_state.read_pending_evidence(durable) == pending:
        guard = _durable.guarded(durable, _ABANDONED, _attempts._ATTEMPT_KEYS)
        fits = _abandons(finish, durable, pending, why)
        if _durable.lands(finish.gh, finish.issue, finish.state, guard, durable) is not None:
            fits = None
    if fits is None and recorded(finish, logged=False) == pending:
        fits = _writes.abandons(finish, partial(_abandons, finish, pending=pending, why=why))
    settled = None
    if fits is None and finish.proves_settled:
        settled = _durable.takes_in_a_settlement(finish.gh, finish.issue, finish.state, pending.receipt)
    if settled is not None:
        log.info(
            "issue=#%d invalidating verification evidence revision %d another finish settled for %.8s while its "
            "abandonment was asked: %s",
            finish.issue.number, settled.revision, finish.head, why,
        )
        fits = invalidates(finish, settled)
    if fits is None:
        log.warning(
            "issue=#%d holding the route of %.8s: verification evidence revision %d could not be abandoned over "
            "the pinned comment read again or the tick's own reading of it (%s)",
            finish.issue.number, finish.head, pending.revision, why,
        )
    return None if fits else FinishOutcome.HELD


def _abandons(finish: LandedFinish, staged: PinnedState, pending: _records.PendingEvidence, why: str) -> bool:
    """Stage `pending`'s abandonment into history on `staged`, or its drop where that has no room; whether it fit.

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
    staged.set(_records.PENDING_EVIDENCE, None)
    staged.set(_base_sync_state._PENDING_REWRITE_BASE, None)
    return False
