# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed rewrite's finish captured or settled, retired whole where its recovery resets or parks the attempt.

A finish that recorded the landed head's evidence transaction and stopped
short of its route leaves it pending beside the attempt
(`rewrite_landing_records.captured`), and one that settled it and then died
in the tail of its route -- before the announcement, the relabel, or the
retirement -- leaves it current beside the attempt
(`rewrite_landing_records.settled`). The recovery's captured-only helpers
(`rewrite_landing_moved`) abandon the transaction wherever the recovery reads
the landing moved. These hold settled evidence to the same readings on the two
roads that end a recovery without that landing's route -- a reset that
releases the attempt, and a park that keeps it -- and they are dormant: no
recovery road, park, eligibility gate, or dispatcher hold is handed them yet,
so every recovery context still carries the captured-only answers alone.

- Over a reset that landed (`retires_over_the_reset`, the answer a recovery
  context's `settles_over_a_reset` would carry): the transaction is abandoned
  on the state the park lands, as the captured-only answer stages it
  (`rewrite_landing_moved.abandons_over_the_reset`), and settled evidence is
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
  (`git/base_sync/persistence._releases_over_the_reset`).
- Before a park that keeps the attempt (`retires_unproved`): the transaction
  is proved again and abandoned where it moved
  (`rewrite_landing_moved.proves_captured`), and settled evidence is proved
  ready (`rewrite_finish_readiness.settled_word`) and invalidated whole where
  it moved (`rewrite_finish_readiness.invalidates`), over the checkout as it
  reads now and the branch the comment names, none of it needing the fetch an
  abort could not take. Movement the caller already read -- a record a park's
  own commit adopted while its notice was posted -- stands as that proof of
  the evidence under the receipt it was read under, and of none other, so no
  reading taken now hides it by finding it put back. With no checkout on
  disk there is nothing to prove the landing over, so both are retired as
  over a reset, on the state the park lands; the movement is recorded against
  them first, in a write of its own, by the proof that hands this one in
  (`rewrite_recovery_parks.proves_before_a_park`).

The dormant guarded records a recovery park or hold lands behind that proof
(`rewrite_recovery_parks`) read three more things here. The receipts of what
stands (`receipts`) say whether movement a caller read before a write took
another road's records in was read under the evidence still standing behind
that write; a record that did not land has the evidence the comment carries
now laid over the tick's state (`reconciles`), so what the proof behind it
proves is that, a successor another road settled meanwhile among it, with the
movement that very reading records under it kept for that proof; and the
movement a comment such a record read carries under each evidence it records
for the head is read off that very comment (`moved_under`), however soon it is
put back -- a report or review record moved off that evidence's binding, or
the base tip the attempt recorded its replay as made onto read blank or
repointed beside every other member of the attempt as the tick read it
(`attempt_as_read`).

Nothing here posts, parks, resets, or routes anything.
"""
from __future__ import annotations

import json
import logging
from dataclasses import replace

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    state as _base_sync_state,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_commits as _commits,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_writes as _writes,
    rewrite_landing_moved as _landing_moved,
    rewrite_landing_records as _landing_records,
    verification_durable as _durable,
    verification_proof as _proof,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.pinned_commit_models import PinnedCommit
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.rewrite_finish_rechecks import lays

log = logging.getLogger("orchestrator.workflow")

# The base tip the attempt recorded its replay as made onto, the one member of
# the attempt a comment may read moved -- blanked, as a reset is recorded, or
# repointed -- beside every other member as the tick read it, where any other
# member moved is another attempt (`moved_under`).
_TIP_ALONE = (_base_sync_state._PENDING_REWRITE_BASE,)

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

# What that move, read by a record's commit, is under the evidence the comment
# carries for the landed head: no base the tick read proves which one its head
# was replayed onto, however soon the tip is put back.
_TIP_MOVED_UNDER_THE_RECORD = ReportEvidence(
    ReportEvidenceVerdict.DEFER, "the base tip the attempt recorded its replay as made onto moved under a record",
)


def retires_over_the_reset(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext, why: str = _landing_moved._RELEASED,
) -> bool:
    """Stage the retirement of what a finish captured or settled for the landed head; whether the attempt may go.

    A recovery's answer to a reset that landed, asked by the git owner before
    the attempt is dropped from `context.state`: the reset took the checkout
    off the landed head, which is movement under both. The transaction is
    abandoned as the captured-only answer abandons it
    (`rewrite_landing_moved.abandons_over_the_reset`), and settled evidence is
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
    _landing_moved.abandons_over_the_reset(context, why)
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


def retires_unproved(context: _AutoRebaseRecoveryContext, moved: dict[str, ReportEvidence] | None = None) -> bool:
    """Prove what a finish captured or settled for the landed head before a park keeps it, retiring what moved.

    Whether the park may go on. The transaction is proved first
    (`rewrite_landing_moved.proves_captured`), and settled evidence then
    proved ready again and invalidated whole where it moved; nothing is read
    or written where neither stands, and what nothing moved under is kept.
    `moved` is movement the caller already read under that evidence, by the
    receipt it was read under (`moved_under`), which is the proof the
    transaction under that receipt is abandoned with, or that invalidates the
    settled evidence under it outright -- movement read under one receipt
    proving nothing about evidence standing under another, which is proved on
    its own readings. Settled evidence is proved by a finish of the landed
    head held to the dormant settled-evidence policy, built here for the proof
    alone: the mark of movement an earlier finish left under its receipt is
    read as the movement it is, and an announcement another finish of the
    landing put on the attempt meanwhile is taken in before the invalidation
    lands over it, rather than refusing it and leaving the evidence current
    for a later poll to route. With no checkout on disk both are retired on the state
    the park lands (`retires_over_the_reset`). False only where evidence still
    stands once its retirement was asked -- settled evidence with no room for
    its history entry among it, its movement recorded instead -- for the git
    owner to hold the tick with nothing parked.
    """
    moved = moved or {}
    captured = _landing_records.captured(context.state)
    if captured is None and _landing_records.settled(context.state) is None:
        return True
    if not context.worktree.is_dir():
        return retires_over_the_reset(context, _landing_moved._CHECKOUT_GONE)
    branch = _naming._resolve_branch_name(context.state, context.spec, context.issue.number)
    unread = _AutoRebaseRecoverySnapshot(branch=branch, local_head="")
    proof = None if captured is None else moved.get(captured.receipt)
    if not _landing_moved.proves_captured(context, unread, proof):
        return False
    return _proves_settled(context, unread, moved)


def receipts(state) -> frozenset[str]:
    """The receipts of what a finish captured or settled for the landed head, as `state` carries them.

    What a caller that read movement before a write took another road's
    records in compares across that write: movement read under one receipt is
    no proof about evidence standing under another.
    """
    recorded = (_landing_records.captured(state), _landing_records.settled(state))
    return frozenset(record.receipt for record in recorded if record is not None)


def reconciles(context: _AutoRebaseRecoveryContext) -> dict[str, ReportEvidence]:
    """Lay the evidence records the comment read afresh carries over `context.state`; the movement it reads under them.

    For a caller whose record did not land -- refused, or sent and never
    confirmed -- or whose notice raised, whose state still holds the evidence
    as the tick read it: a successor another road recorded or settled
    meanwhile is the evidence the proof behind that record has to take, on its
    own binding, each record taken in as read. That very reading is asked what
    it records moving under the evidence it carries for the head
    (`moved_under`, the attempt as the tick last read it beside it), by
    receipt, which is the answer, for the caller to hand the proof behind it
    as movement already read, so a record put back between this reading and
    that proof revives nothing. A comment that would not read is read
    once more, so one failed request does not leave the proof behind it
    classifying the tick's older evidence while its own reading carries a
    successor. Empty where nothing moved, or where the comment would not read
    either time, which lays nothing.
    """
    attempt = attempt_as_read(context.state)
    durable = _durable.durable_comment(context.gh, context.issue, context.state)[0]
    if durable is None:
        durable = _durable.durable_comment(context.gh, context.issue, context.state)[0]
    if durable is None:
        return {}
    lays(context.state, durable, _durable._EVIDENCE_RECORDS)
    return moved_under(durable, attempt)


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


def moved_under(comment: PinnedState | None, attempt: PinnedCommit | None = None) -> dict[str, ReportEvidence]:
    """The movement `comment` records under each evidence it carries for the landed head, by that evidence's receipt.

    `comment` is one a record's commit read -- the record it landed or sent,
    or the comment a refusal was read over -- and the movement is a review or
    report record it spells off that evidence's own binding
    (`verification_proof.recorded_verdict`), and, under evidence settled for
    the head, whatever else the records alone refuse it over as the dormant
    settled-evidence policy reads them (`rewrite_finish_readiness._records_heard`):
    the mark of movement an earlier finish left under its receipt in the
    handoff's place among them. Each is asked of that very reading, so it
    stands however soon the record is put back. `attempt` is the attempt the
    tick read (`attempt_as_read`), where the caller has one: `comment` reading
    its base tip moved, every other member as the tick read it, is movement
    under every evidence it carries for the head (`_TIP_MOVED_UNDER_THE_RECORD`)
    -- a blank another road recorded and put back right behind, which no
    proof taken over the comment as it then stands would read. Empty where
    `comment` is None or carries no evidence for the head that moved.
    """
    if comment is None:
        return {}
    if attempt is not None and attempt.moved(comment.data) == _TIP_ALONE:
        return dict.fromkeys(receipts(comment), _TIP_MOVED_UNDER_THE_RECORD)
    moved = {}
    settled = _landing_records.settled(comment)
    for record in filter(None, (_landing_records.captured(comment), settled)):
        heard = (_proof.recorded_verdict(comment, record.binding),)
        if record is settled:
            heard = _readiness._records_heard(record, comment, settled=True)
        heard = [refused for refused in heard if refused and not refused.holds]
        if heard:
            moved[record.receipt] = heard[0]
    return moved


def _proves_settled(
    context: _AutoRebaseRecoveryContext, unread: _AutoRebaseRecoverySnapshot, moved: dict[str, ReportEvidence],
) -> bool:
    """Prove evidence a finish settled for the landed head ready again, invalidated whole where it moved; may it go.

    By a finish of the landed head held to the dormant settled-evidence policy,
    built for the proof alone, over the landing as `unread` reads it. Movement
    `moved` holds under that evidence's own receipt stands as the proof;
    movement under any other receipt says nothing about it. A successor
    another road settled in its place only after `context.state` was read is
    asked of its own binding in the proof's own readings of the comment
    (`rewrite_finish_readiness.settled_word`), and retired whole or marked
    where it moved there. True where none stands, or where nothing moved;
    otherwise whether its invalidation landed.
    """
    settled = _landing_records.settled(context.state)
    if settled is None:
        return True
    finish = replace(
        _landing_moved._finish(context, settled.binding.target.target_head, unread, None), proves_settled=True,
    )
    word = moved.get(settled.receipt)
    word = word or _readiness.settled_word(finish, settled)[0]
    return word is None or _readiness.invalidates(finish, settled)
