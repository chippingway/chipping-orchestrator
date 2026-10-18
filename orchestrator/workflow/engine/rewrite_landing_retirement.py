# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed rewrite's finish captured or settled, retired whole where its recovery resets or parks the attempt.

A finish that recorded the landed head's evidence transaction and stopped
short of its route leaves it pending beside the attempt
(`rewrite_landing_records.captured`), and one that settled it and then died
in the tail of its route -- before the announcement, the relabel, or the
retirement -- leaves it current beside the attempt
(`rewrite_landing_records.settled`). These hold both to the same readings
on the two roads that end a recovery without that landing's route -- a reset
that releases the attempt, and a park that keeps it -- and on a snapshot that
reads the landing moved, whose helpers (`rewrite_landing_moved`) hand the
park's proof that movement as read; every recovery context the workflow builds
carries them: each recovery road's (`rewrite_recovery.recovers`), the abort
over an unreadable checkout's, the eligibility gate's park of a label the
refresh does not drive (`base_rewrite`), and the dispatcher's held anchor
(`rewrite_recovery_parks.answers_a_held_anchor`).

- Over a reset that landed, or a clear over a checkout back on the anchor
  (`retires_over_the_reset`, the answer a recovery context's
  `settles_over_a_reset` carries): the transaction is abandoned on the state
  the park or the clear lands, as its own half stages it
  (`rewrite_landing_captured.abandons_over_the_reset`), and settled evidence is
  invalidated into history whole on that same state, its revision, binding,
  and provenance kept, so it goes with the attempt's release or neither goes.
  With no room for its history entry it is never dropped: it stays current and
  whole beside the attempt that keeps every reader off it, the base tip the
  attempt recorded its replay as made onto blanked in a write of its own, so
  every later proof of it reads movement
  (`rewrite_evidence_proof.standing_refusal`) and invalidates it whole once
  the comment has room, however the checkout is put back meanwhile -- and the
  answer is False, for the git owner to keep the attempt and hold the tick
  with nothing released or parked
  (`git/base_sync/persistence._releases_over_the_reset`,
  `git/base_sync/snapshot._clear_ineligible_recovery`).
- Before a park that keeps the attempt (`retires_unproved`): the transaction
  is proved again and abandoned where it moved
  (`rewrite_landing_captured.proves_captured`), and settled evidence is proved
  ready (`rewrite_finish_readiness.settled_word`) and invalidated whole where
  it moved (`rewrite_finish_readiness.invalidates`), both by a finish of the
  landed head held to the settled-evidence policy -- the mark of
  movement an earlier finish left under its receipt read as movement, a
  settlement another finish made of the transaction while its abandonment
  was asked invalidated over the same movement, and an announcement another
  finish put on the attempt meanwhile taken in -- over the checkout as it
  reads now and the branch the comment names, none of it needing the fetch an
  abort could not take. Movement the caller already read -- a record a park's
  own commit adopted while its notice was posted -- stands as that proof of
  the evidence under the receipt it was read under, and of none other, so no
  reading taken now hides it by finding it put back; and every comment the
  proof's finishes read -- their abandonment's, invalidation's, and rechecks'
  own readings among them -- is read through a client that hands it to the
  proof's classifier first (`rewrite_recovery_readings`), so movement any of
  them read stands for every step behind. With no checkout on
  disk there is nothing to prove the landing over, so both are retired as
  over a reset, on the state the park lands; the movement is recorded against
  them first, in a write of its own, by the proof every recovery context
  carries (`rewrite_recovery_parks.proves_before_a_park`). The landed road's
  own holds ask it too (`rewrite_landed`), ahead of a hold's write.

The guarded records a recovery park or hold lands behind that proof
(`rewrite_recovery_parks`) read three more things here. The receipts of what
stands (`receipts`) name the evidence movement a caller read before a write
is keyed under, the proof asking it only of evidence standing under that
very receipt; a record that did not land has the evidence the comment
carries now laid over the tick's state (`reconciles`), so what the proof
behind it proves is that, a successor another road settled meanwhile among
it, with the movement that very reading records under it kept for that proof
-- save a slot the comment carries nothing in where movement was read under
what the tick held there, by that reading or by the record's own refusal,
which is kept from the tick's state for the proof to abandon or invalidate
however soon it is put back, every other record laid all the same; and the
movement a comment such a record read carries under each evidence it records
for the head -- or, where it records no transaction captured or no evidence
settled for the head, under what the tick held there -- is read off that very comment
(`moved_under`), however soon it is put back: a report or review record moved
off that evidence's binding, a revision spent past it, or the base tip the
attempt recorded its replay as made onto read blank or repointed beside every
other member of the attempt as the tick read it (`attempt_as_read`).

Nothing here posts, parks, resets, or routes anything.
"""
from __future__ import annotations

import json
import logging

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    models as _base_sync_models,
    state as _base_sync_state,
)
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    report_commits as _commits,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_writes as _writes,
    rewrite_landing_captured as _landing_captured,
    rewrite_landing_records as _landing_records,
    verification_durable as _durable,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.pinned_commit_models import PinnedCommit, spelled
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_finish_rechecks import invalidates_rechecked, lays
from orchestrator.workflow.engine.rewrite_recovery_readings import (
    LEFT_THE_CHECKOUT,
    LosesTheCheckout,
    asks_every_reading,
    owed_moves,
    stands_as_recovered,
    tip_moves,
)
from orchestrator.workflow.engine.verification_records import (
    CURRENT_EVIDENCE,
    PENDING_EVIDENCE,
    CurrentEvidence,
    PendingEvidence,
)

log = logging.getLogger("orchestrator.workflow")

# The attempt's members a tip move is read against (`attempt_as_read`): every
# one but the bookkeeping a finish of the landing puts down as it announces
# and relabels -- the record of its event, the mark, and the record of its
# relabel -- which advances the attempt rather than replacing it.
_AS_READ = tuple(
    member for member in _attempts._ATTEMPT_KEYS if member not in {
        _base_sync_state._PENDING_ANNOUNCED_EVENT,
        _base_sync_state._PENDING_ANNOUNCED_SHA,
        _base_sync_state._PENDING_RELABELLED,
    }
)

# The record each of what a finish captured and what it settled for the landed
# head stands in, in that order, beside how a comment is read for it -- the
# slot a reconciliation keeps from the tick's own reading where the comment
# carries nothing there and what the tick held there moved.
_SLOTS = ((PENDING_EVIDENCE, _landing_records.captured), (CURRENT_EVIDENCE, _landing_records.settled))


def retires_over_the_reset(
    context: _base_sync_models._AutoRebaseContext | _base_sync_models._AutoRebaseRecoveryContext,
    why: str = _landing_captured._RELEASED,
) -> bool:
    """Stage the retirement of what a finish captured or settled for the landed head; whether the attempt may go.

    A recovery's answer to a reset that landed, asked by the git owner before
    the attempt is dropped from `context.state`: the reset took the checkout
    off the landed head, which is movement under both -- and so is a checkout
    standing back on the anchor under a label the refresh does not drive,
    whose clear asks it too
    (`git/base_sync/snapshot._clear_ineligible_recovery`). The transaction is
    abandoned (`rewrite_landing_captured.abandons_over_the_reset`),
    and settled evidence is
    invalidated on the same state, into history whole, its revision and
    binding kept, so both land with the attempt's release or neither does.
    With no room for its history entry the settled evidence is not dropped:
    it stays current, whole, beside the attempt that keeps every reader off
    it, and the movement is recorded instead by blanking the base tip the
    attempt recorded its replay as made onto, so every later proof of the
    evidence reads movement (`rewrite_evidence_proof.standing_refusal`) and
    invalidates it whole once the comment has room -- putting the checkout
    back first revives nothing. A reset recorded ahead of it has that blank
    landed already (`rewrite_recovery_parks.records_the_reset`); a checkout
    gone from disk has it landed here. It only shrinks the comment, so it
    lands at once, guarded as the finish's own abandonment is
    (`rewrite_finish_writes.ABANDONMENT`), with whatever else this answer
    staged. False then, for the git owner to keep the attempt and hold the
    tick with nothing parked until room is made. `why` names the write it
    rides, logged.
    """
    _landing_captured.abandons_over_the_reset(context, why)
    settled = _landing_records.settled(context.state)
    if settled is None:
        return True
    log.info(
        "issue=#%d invalidating verification evidence revision %d settled for %.8s, %s",
        context.issue.number, settled.revision, settled.binding.target.target_head, why,
    )
    if _settlement.retire_current_evidence(context.state):
        return True
    context.state.set(_base_sync_state._PENDING_REWRITE_BASE, None)
    recorded = _commits.ReportCommit(context.gh, context.issue, context.state).lands(
        context.state, _writes.ABANDONMENT,
    )
    log.error(
        "issue=#%d the pinned comment has no room to retire verification evidence revision %d settled for %.8s; "
        "keeping it current beside the attempt, its base tip blanked (%s), and holding until room is made",
        context.issue.number, settled.revision, settled.binding.target.target_head, recorded.status.value,
    )
    return False


def retires_unproved(
    context: _base_sync_models._AutoRebaseRecoveryContext, moved: dict[str, ReportEvidence] | None = None,
) -> bool:
    """Prove what a finish captured or settled for the landed head before a park keeps it, retiring what moved.

    Whether the park may go on -- or, asked by a snapshot that read the
    landing moved (`rewrite_landing_moved.abandons`), its road. The
    transaction is proved first (`rewrite_landing_captured.proves_captured`),
    and settled evidence then
    proved ready again and invalidated whole where it moved; nothing is read
    or written where neither stands and no movement was read, and what
    nothing moved under is kept. Movement read under a receipt the tick holds
    nothing under -- a successor a record's refusal read, put back only after
    the reconciliation read none -- is proved all the same.
    `moved` is movement the caller already read under that evidence, by the
    receipt it was read under (`moved_under`), which is the proof the
    transaction under that receipt is abandoned with, or that invalidates the
    settled evidence under it outright -- movement read under one receipt
    proving nothing about evidence standing under another, which is proved on
    its own readings. Both are proved by a finish of the landed head held to
    the settled-evidence policy, built here for the proof alone: the
    mark of movement an earlier finish left under its receipt is read as the
    movement it is; a transaction another finish settled while its
    abandonment was asked has that settlement invalidated over the same
    movement in its place (`rewrite_finish_unconfirmed.reconciles_the_abandonment`);
    and an announcement another finish of the landing put on the attempt
    meanwhile is taken in before the invalidation lands over it, rather than
    refusing it and leaving the evidence current for a later poll to route.
    Each is proved whatever the other's proof answered, so a captured run
    whose abandonment could not land -- one another road took off the comment
    meanwhile among them -- leaves no settled successor unproved beside it.
    Every comment either proof reads is asked what it records moving under
    any receipt there (`moved_under`, over what the tick holds), into the
    movement both share, so a successor read moving while the captured run
    was proved -- beside a blank of the base tip, say -- is retired by the
    settled proof however soon what moved is put back -- every comment their
    finishes read of their own accord included, through a client that asks
    each first (`rewrite_recovery_readings.AsksEveryReading`). Where both may
    go on while evidence still standing carries movement read only behind its
    own proof, both are asked again with it; a proof that reads movement
    retires what moved or answers False, so the asking stops there.
    With no checkout on disk -- gone before the proof, or while it was asked,
    one of its requests finding nothing there -- nothing proves the landing,
    so the reset is recorded against both and both retired as over it, each
    in a write of its own, by the recorder `context` carries
    (`_AutoRebaseRecoveryContext.records_before_a_reset`,
    `rewrite_recovery_parks.records_the_reset`, which hands it every proof it
    and the proof before a park ask), its answer the proof's; a context with
    no recorder has both retired on the state the park lands
    (`retires_over_the_reset`); one back on disk by then has that loss asked
    again as movement under each receipt held. False only where evidence still
    stands once its retirement was asked -- settled evidence with no room for
    its history entry among it, its movement recorded instead -- or where the
    comment the proof read carries another attempt in place of the one
    `context` recovers, laid over the tick's state by its rechecks
    (`rewrite_recovery_readings.stands_as_recovered`): either way for the git
    owner to hold the tick with nothing reset, cleared, or parked over it.
    """
    moved = dict(moved or {})
    if not (moved or receipts(context.state)):
        return True
    unread = _base_sync_models._AutoRebaseRecoverySnapshot(
        branch=_naming._resolve_branch_name(context.state, context.spec, context.issue.number), local_head="",
    )
    asked = asks_every_reading(
        context, lambda reading: moved_under(reading, tick=context.state, into=moved),
    )
    proved = None
    with LosesTheCheckout(context):
        proved = context.worktree.is_dir() and all((
            _landing_captured.proves_captured(
                asked,
                unread,
                moved.get(getattr(_landing_records.captured(context.state), "receipt", None)),
                asks=lambda reading, receipt: (
                    moved_under(reading, tick=context.state, into=moved).get(receipt)
                ),
            ),
            _proves_settled(asked, unread, moved),
        ))
    if not context.worktree.is_dir():
        records = context.records_before_a_reset
        return (
            retires_over_the_reset(context, _landing_captured._CHECKOUT_GONE)
            if records is None else records(context)
        )
    moved.update({
        receipt: LEFT_THE_CHECKOUT for receipt in receipts(context.state) if proved is None
    })
    if proved is not False and moved.keys() & receipts(context.state):
        return retires_unproved(context, moved)
    if proved and not stands_as_recovered(context):
        log.warning(
            "issue=#%d another auto-rebase attempt stands in place of the one its recovery read; holding with "
            "nothing reset, cleared, or parked, for the next tick to recover the attempt the comment carries",
            context.issue.number,
        )
        return False
    return bool(proved)


def receipts(state) -> frozenset[str]:
    """The receipts of what a finish captured or settled for the landed head, as `state` carries them.

    What a caller that read movement before a write took another road's
    records in keys that movement under: movement read under one receipt is
    no proof about evidence standing under another.
    """
    recorded = (_landing_records.captured(state), _landing_records.settled(state))
    return frozenset(record.receipt for record in recorded if record is not None)


def reconciles(
    context: _base_sync_models._AutoRebaseRecoveryContext, moved: dict[str, ReportEvidence] | None = None,
) -> dict[str, ReportEvidence]:
    """Lay the evidence records the comment read afresh carries over `context.state`; the movement read under them.

    For a caller whose record did not land -- refused, or sent and never
    confirmed -- or whose notice raised, whose state still holds the evidence
    as the tick read it: a successor another road recorded or settled
    meanwhile is the evidence the proof behind that record has to take, on its
    own binding, each record taken in as read. That very reading is asked what
    it records moving under the evidence it carries for the head
    (`moved_under`, the attempt as the tick last read it beside it), by
    receipt, which is the answer, for the caller to hand the proof behind it
    as movement already read, so a record put back between this reading and
    that proof revives nothing. A reading that carries no transaction
    captured, or no evidence settled, for the head is asked of what
    `context.state` held there in its place (`moved_under`); where it reads
    movement under a receipt it carries nothing in the place of -- a base tip
    blanked, or a revision spent past settled evidence, beside that evidence
    taken off -- that record's slot (`_SLOTS`) is not laid, so the state keeps that
    evidence for the proof to abandon or invalidate under the receipt the
    movement was read under, however soon another road puts it back. Every
    other record is laid all the same, so a successor settled in its place,
    and the movement read under it, are proved on their own beside it.
    `moved` is movement the caller's own record already read under the
    evidence the tick held -- the comment its refusal was read over, the base
    tip blank there beside that evidence taken off among it -- which keeps
    that record's slot just as movement this reading reads does, however
    soon what moved was put back before this reading, and is answered beside
    it. A comment that would not read is read
    once more, so one failed request does not leave the proof behind it
    classifying the tick's older evidence while its own reading carries a
    successor. Each member of the attempt the comment carries as
    `context.state` staged it -- a record sent with its answer lost that
    landed the tick's own staging, a base tip staged back behind a reset git
    refused among it -- is taken in as read too, so the proof behind takes
    that attempt for this tick's own rather than one another road put in its
    place. Empty where nothing moved; `moved` alone, laying nothing,
    where the comment would not read either time.
    """
    moved = dict(moved or {})
    durable = _durable.durable_comment(context.gh, context.issue, context.state)[0]
    if durable is None:
        durable = _durable.durable_comment(context.gh, context.issue, context.state)[0]
    if durable is None:
        return moved
    moved_under(durable, tick=context.state, into=moved)
    lays(context.state, durable, _durable._EVIDENCE_RECORDS - {
        slot for slot, reads in _SLOTS
        if reads(durable) is None and (
            getattr(reads(context.state), "receipt", None) in moved
        )
    })
    _commit.takes_in(context.state, durable.data, [
        member for member in _attempts._ATTEMPT_KEYS
        if spelled(durable.data, member) == spelled(context.state.data, member)
    ])
    return moved


def attempt_as_read(state: PinnedState) -> PinnedCommit | None:
    """The attempt `state` was last read carrying, for `moved_under` to read a move of its base tip against.

    As the comment carried it when the tick last read it, not as the tick
    holds it now: a tip the tick staged back over its own blank -- a reset git
    refused, whose recorded blank landed -- is no tip another road moved.
    Captured without the announcement's bookkeeping (`_AS_READ`), so a comment
    carrying a finish of the landing's event record, mark, or relabel record
    beside the moved tip is still this attempt. None where that reading
    records no tip, so names no base to move.
    """
    read = state
    if state.synced is not None:
        synced = json.loads(state.synced)
        read = PinnedState(comment_id=state.comment_id, state_data=synced, parsed=state.parsed)
    if not _attempt_records._recorded_onto(read):
        return None
    return PinnedCommit.capture(read, prerequisites=_AS_READ)


def moved_under(
    comment: PinnedState,
    attempt: PinnedCommit | None = None,
    held: tuple[PendingEvidence | None, CurrentEvidence | None] = (None, None),
    *,
    tick: PinnedState | None = None,
    into: dict[str, ReportEvidence],
) -> dict[str, ReportEvidence]:
    """The movement `comment` records under each evidence it carries for the landed head, by that evidence's receipt.

    `comment` is one a record's commit read -- the record it landed or sent,
    or the comment a refusal was read over -- and the movement is a review or
    report record it spells off that evidence's own binding
    (`verification_proof.recorded_verdict`) -- under a transaction captured for
    the head, a revision spent past it as well (`rewrite_recovery_readings.owed_moves`)
    -- and, under evidence settled for
    the head, whatever else the records alone refuse it over as the
    settled-evidence policy reads them (`rewrite_finish_readiness._records_heard`):
    the mark of movement an earlier finish left under its receipt in the
    handoff's place among them, and a revision spent past it. Each is asked
    of that very reading, so it stands however soon the record is put back.
    `held` is what the caller's state carried for the head before the
    record, where it hands it in -- the transaction a finish captured and the
    evidence one settled, either None: a `comment` carrying no transaction
    captured for the head is asked of the one held in its place, and one
    carrying no evidence settled for the head -- none current, or another
    head's -- of the evidence held, so the base tip moved, or a revision
    spent past that evidence, read there is movement under it however soon
    the comment is put back with it again.
    `attempt` is the attempt the tick read (`attempt_as_read`), where the
    caller has one: `comment` reading its base tip moved, every other member
    as the tick read it, is movement under every evidence it is asked of
    (`rewrite_recovery_readings.tip_moves`) -- a blank another road recorded and put
    back right behind, which no proof taken over the comment as it then
    stands would read -- and evidence `held` does not name, read beside an
    attempt that still stands recording no tip, is moved by that blank even
    where the tick read it too. `tick`, where a caller hands the tick's state instead,
    is read for both: the attempt as it last read it, and what it holds. Empty
    where `comment` carries no evidence for the head that moved. `into` is
    what the answer is added to, and is: a proof's every reading adds what it
    reads moving under any receipt there to the one the caller holds, so
    movement one reading read stands for every step behind it, the first
    movement read under a receipt kept.
    """
    if tick is not None:
        return moved_under(
            comment,
            attempt_as_read(tick),
            (_landing_records.captured(tick), _landing_records.settled(tick)),
            into=into,
        )
    tipped, unbased = tip_moves(comment, attempt)
    for record in filter(None, (
        _landing_records.captured(comment) or held[0],
        _landing_records.settled(comment) or held[1],
    )):
        heard = owed_moves(comment, record)
        if isinstance(record, CurrentEvidence):
            heard = _readiness._records_heard(record, comment, settled=True)
        heard = (tipped if record in held else unbased, *heard)
        refused = [verdict for verdict in heard if verdict and not verdict.holds]
        if refused:
            into.setdefault(record.receipt, refused[0])
    return into


def _proves_settled(
    context: _base_sync_models._AutoRebaseRecoveryContext,
    unread: _base_sync_models._AutoRebaseRecoverySnapshot,
    moved: dict[str, ReportEvidence],
) -> bool:
    """Prove evidence a finish settled for the landed head ready again, invalidated whole where it moved; may it go.

    By a finish of the landed head held to the settled-evidence policy,
    built for the proof alone, over the landing as `unread` reads it. Movement
    `moved` holds under that evidence's own receipt stands as the proof;
    movement under any other receipt says nothing about it. A successor
    another road settled in its place only after `context.state` was read is
    asked of its own binding in the proof's own readings of the comment
    (`rewrite_finish_readiness.settled_word`), and retired whole or marked
    where it moved there. Where `context.state` holds none settled for the
    head -- a captured run alone, proved just before -- or `moved` holds
    movement under a receipt `context.state` does not, the comment is first
    read afresh and reconciled (`reconciles`), read once more where it would
    not read: evidence another road settled for the head since -- beside or
    in place of that run, or a successor a record's refusal read moving, gone
    from an earlier reading and put back behind it -- is taken in and proved
    on its own binding, whatever that run's proof answered, the movement that
    reading records kept beside `moved`. Each reading the readiness proof
    then takes is asked the same (`moved_under`, handed to
    `rewrite_finish_readiness.settled_word` to ask) under whichever receipt
    that reading carries -- the evidence, or a successor in its place -- so a
    base tip it reads blank or repointed beside the attempt as the tick last
    read it moves that evidence however soon it is put back. The invalidation is read behind as
    that policy's evidence phase reads it
    (`rewrite_finish_rechecks.invalidates_rechecked`); where that reading
    cannot say the route is free -- unread, or the evidence put back -- it is
    asked once more, its own fresh reading retiring the receipt again over the
    comment as it stands, or marking its movement, and only a comment read
    afresh carrying nothing current under it then lets the proof go on --
    where that reading carries a successor in the evidence's place, one the
    invalidation could not land over, it is laid over the tick's state and
    proved the same way on its own binding, what that very reading, or any
    the invalidation and its rechecks took, records moving kept for it: each
    is read through the client `context` carries, which adds it to `moved`
    (`retires_unproved`), the one record every step here reads. A successor
    the recheck behind a landed invalidation takes in is proved the same way,
    so a reading that leaves the route free never stands for its proof. True
    where none stands, or where nothing moved.
    """
    settled = _landing_records.settled(context.state)
    if settled is None or moved.keys() - receipts(context.state):
        moved.update(reconciles(context, moved))
        settled = _landing_records.settled(context.state)
    if settled is None:
        return True
    finish = _landing_captured._finish(context, settled.binding.target.target_head, unread, None)
    word = moved.get(settled.receipt) or _readiness.settled_word(
        finish,
        settled,
        lambda reading, receipt: moved_under(reading, tick=context.state, into=moved).get(receipt),
    )[0]
    if word is None:
        return True
    if any(invalidates_rechecked(finish, settled) for _asked in range(2)):
        return _landing_records.settled(context.state) is None or _proves_settled(context, unread, moved)
    durable = _durable.durable_comment(context.gh, context.issue, context.state)[0]
    if durable is not None:
        lays(context.state, durable, _durable._EVIDENCE_RECORDS)
    if durable is None or (
        getattr(_landing_records.settled(context.state), "receipt", None) == settled.receipt
    ):
        return False
    return _proves_settled(context, unread, moved)
