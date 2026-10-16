# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dormant settled-evidence policy's steps in a landed rewrite's evidence phase, beside the one every road selects.

A finish is held to one of two policies: the one every production road hands
over, which proves again only a transaction an earlier finish captured for the
landed head, and a dormant one a caller selects only by building the finish
with `rewrite_finish_models.LandedFinish.proves_settled`. The dormant policy
proves evidence already settled for the head ready again
(`rewrite_finish_readiness.stands_ready`), and invalidates it into history
whole wherever anything it is bound to moved since it settled.

Each step here is one the evidence phase (`rewrite_finish_settlement.resolves`)
takes whichever policy holds the finish, and it answers for both: a finish not
held to the dormant policy goes on exactly as the policy every road selects
has it, reading nothing more. That phase is callable on its own, announcing,
relabelling, parking, and retiring nothing; the coordinator
(`rewrite_finish.finalizes`) takes none of the policy's proofs around its
announcement, park, relabel, or retirement yet.

- `stands_ready_if_settled` proves evidence settled current for the head
  ready, where any is -- reading the comment afresh behind an invalidation
  that proof lands (`rewrite_finish_rechecks.rechecks_behind`) -- and, asked
  for the base, holds a head with none to the base its replay was made onto,
  or the base the tick counted it against.
- `out_of_step` says why the records beside settled evidence hold the route,
  and `moves_the_binding` which of the refusals an answer read moved what a
  binding rests on rather than the evidence records or the attempt's own
  members alone, whatever the comment carries by the time it is asked; a
  settlement and announcement another finish made while the answer was asked
  `adopts_the_answer` takes in first -- another road's attempt one of those
  readings carries in place of the captured one taken in too, so the route
  holds over it. What every comment the answer read
  carries is asked the moment it is read (`reads_moving`) -- the one it
  starts from, one a refusal of moved records was read over, the one it
  leaves the tick's state carrying, and those the adoption took: a blank of
  the base tip of the attempt captured, a mark of movement, a revision
  outranking the evidence, or any other movement the readiness proof reads in
  the records under the transaction answered -- or, while it is still owed,
  a review or report record moved off its own binding or a revision spent
  past it -- is kept as the movement it is, however the comment or the
  tick's state reads by the time it is classified; so is a pull request the
  answer read ended (`verification_proof.ProofReading.keeps`).
- `retires_the_adopted` invalidates a settlement the settlement step's answer
  left current -- its own, or another road's it adopted -- over movement the
  answer read under its binding, the announcement a finish of this landing
  made of it aside, before anything is resolved afresh -- and, where another
  finish's route took the attempt off the comment meanwhile or another road
  replaced it, over the comment as it stands -- read afresh once that lands,
  so a successor recorded, or another attempt put in place, right behind it
  holds the route (`rewrite_finish_rechecks.rechecks_behind`). Whether the
  attempt the answer left is the one the finish captured -- unmoved, or
  advanced by its own announcement -- is `rewrite_finish_rechecks.stands_as_read`.

Nothing here runs the configured commands, posts an artifact, launches a
developer, or announces anything.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    state as _base_sync_state,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_captured as _captured,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_unconfirmed as _unconfirmed,
    verification_durable as _durable,
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence, ReportEvidenceVerdict
from orchestrator.workflow.engine.rewrite_evidence_proof import standing_refusal
from orchestrator.workflow.engine.rewrite_finish_marks import retires_as_it_stands
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish
from orchestrator.workflow.engine.rewrite_finish_outranking import outranks_the_owed
from orchestrator.workflow.engine.rewrite_finish_rechecks import rechecks_behind, stands_as_read
from orchestrator.workflow.engine.verification_proof import recorded_verdict

log = logging.getLogger("orchestrator.workflow")

# The base tip the attempt recorded its replay as made onto, which a proof
# blanks to record movement read under the evidence where nothing else has
# room (`rewrite_finish_readiness._invalidates_on_the_tick`).
_TIP = _base_sync_state._PENDING_REWRITE_BASE

# That blank read by an answer (`reads_moving`): the movement it records,
# however soon the tip is put back.
_BLANKED = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "the attempt's base tip was read blanked, recording movement read under the evidence",
)

# A readable revision an answer read spent past the transaction it answers,
# still owed (`reads_moving`): it outranks that transaction for good, however
# soon the floor is put back, so no settlement of it may stand.
_SPENT_PAST = ReportEvidence(
    ReportEvidenceVerdict.DEFER,
    "a revision past the transaction answered was read spent, outranking it",
)


def stands_ready_if_settled(finish: LandedFinish, *, or_the_base: bool = False) -> FinishOutcome | None:
    """`stands_ready` over evidence settled current for `finish`'s landed head, where any is; None to go on.

    Asked only of a finish held to the dormant settled-evidence policy: any
    other finish goes on from here with nothing read. Where that proof
    invalidated the evidence, the comment is read afresh behind its write
    (`_proves_ready`). `or_the_base` asks for
    the proof a route's last write needs, behind requests that took time: a
    base advanced meanwhile holds the route with the attempt standing, a head
    with no evidence current held to the base tip its replay was made onto
    (`rewrite_finish_captured.stands_before_the_route`), so the recovery
    continues it to another rebase. An attempt that records no tip -- blanked
    to record movement, blanked because the base moved while git ran, or a
    legacy attempt -- proves no base, so its head is held to the base this
    tick counted it against (`rewrite_evidence_proof.standing_refusal`): one
    advanced, rewound or repointed under the local ref, or unreadable holds
    the route for the next tick's fetch to count the head again.
    """
    if not finish.proves_settled:
        return None
    current = _settlement.read_current_evidence(finish.state)
    stopped = None
    if current is not None and current.binding.target.target_head == finish.head:
        stopped = _proves_ready(finish, current)
    elif or_the_base:
        stopped = _captured.stands_before_the_route(finish, landing=False)
    unproven = not _attempt_records._recorded_onto(finish.state)
    if stopped is not None or not (or_the_base and unproven):
        return stopped
    counted = finish.landed.candidate.checkout
    moved = standing_refusal(finish, onto=counted.base.tip)
    if moved is None:
        return None
    log.warning(
        "issue=#%d holding the route of %.8s: its attempt records no base tip, and the base this tick counted "
        "it against reads otherwise now (%s)",
        finish.issue.number, finish.head, moved.refusal,
    )
    return FinishOutcome.HELD


def out_of_step(finish: LandedFinish, current: _records.CurrentEvidence | None) -> str:
    """Why a record beside the head's resolved evidence holds the route over `current`, or "".

    Any pending record, and -- beside `current`, where there is one -- a
    handoff that does not name it or a revision floor nobody can read
    (`rewrite_finish_readiness.beside_current`), and, for a finish not held to
    the settled-evidence policy, a revision spent past it. That policy holds
    no route over a readable revision spent past `current`: it outranks the
    evidence for good, which its readiness proof invalidates rather than
    holding every later poll over it.
    """
    beside = _readiness.beside_current(finish.state, current)
    if beside or finish.proves_settled or current is None:
        return beside
    if _record_state._latest_revision(finish.state) == current.revision:
        return ""
    return "a revision past it was spent"


def retires_the_adopted(
    finish: LandedFinish,
    pending: _records.PendingEvidence,
    movements: list[ReportEvidence],
    attempt: _commit_models.PinnedCommit,
) -> bool:
    """Whether the records the answer to `pending` left resolve afresh, evidence it read moving retired first.

    Always, with nothing read, for a finish not held to the settled-evidence
    policy or with nothing current under `pending`'s receipt. Otherwise that
    evidence -- settled by this answer, or adopted from another road -- is
    invalidated whole over movement the answer read under its binding
    (`movements`), however soon it was put back. The evidence records' own
    moves are no such movement, nor the attempt's members
    (`moves_the_binding`), however soon either was put back -- but movement
    the comment was read recording there is, a blank of the captured
    attempt's base tip or a mark under `pending`'s receipt among it
    (`reads_moving`). Where another
    finish's route or another road took `attempt`, the one captured before
    the answer, off the comment (`rewrite_finish_rechecks.stands_as_read`)
    -- holding the route whatever this says -- the evidence is invalidated as
    the comment stands (`rewrite_finish_marks.retires_as_it_stands`). False,
    logged, where that invalidation did not land, and where the comment read
    afresh once it landed carries a pending record or another attempt, or
    would not read (`rewrite_finish_rechecks.rechecks_behind`): a newer
    transaction another road recorded, or an attempt it put in place, right
    behind its strict edit then stands as written, laid over the tick's state,
    never answered or routed past under the movement read here.
    """
    current = _settlement.read_current_evidence(finish.state)
    if not finish.proves_settled or current is None or current.receipt != pending.receipt:
        return True
    if not moves_the_binding(finish, movements):
        return True
    if stands_as_read(finish, attempt, finish.state):
        invalidated = _readiness.invalidates(finish, current)
    else:
        invalidated = retires_as_it_stands(finish, pending.receipt)
    if invalidated:
        return rechecks_behind(finish, pending.receipt)
    log.warning(
        "issue=#%d holding the route of %.8s: verification evidence revision %d was read moving while it "
        "settled, and could not be invalidated",
        finish.issue.number, finish.head, pending.revision,
    )
    return False


def adopts_the_answer(
    finish: LandedFinish, pending: _records.PendingEvidence, attempt: _commit_models.PinnedCommit,
) -> list[ReportEvidence]:
    """Take in what another finish of the landing made of `pending` while this one answered it; the movement read.

    For the policy alone. The announcement that finish put on the attempt
    (`rewrite_finish_unconfirmed.takes_in_the_announcement`), and its
    settlement of `pending`, every evidence record laid over the tick's state
    (`verification_durable.takes_in_a_settlement`) wherever that state does
    not carry `pending` current -- still owed, or retired by this answer,
    whose own retirement another finish's settlement may have landed right
    behind -- both read afresh ahead of classifying what the answer read
    (`moves_the_binding`), so neither is taken for movement under the
    evidence, and the settlement is resolved as this finish's own. A reading
    carrying an attempt other than `attempt`, the one captured before the
    answer, advanced by its own announcement or not
    (`rewrite_finish_rechecks.stands_as_read`) -- another road's in its
    place, a readable base tip other than the one captured among it, or one
    another finish's route cleared, its base tip aside only where that reads
    blank, which records movement rather than another attempt (`_BLANKED`) --
    has that attempt laid over the tick's state
    (`rewrite_finish_unconfirmed.takes_in_the_attempt`), so the settlement
    adopted is never routed past it. Each comment those readings took is asked
    what it records moving behind `attempt` (`reads_moving`), and that
    movement comes back, to be classified beside what the answer read: a mark
    the settlement taken in carries, put back before anything reads the
    comment again, is the movement it is -- and so is movement on the comment
    the settlement's adoption read where it found `pending` still owed, its
    settlement made only behind that reading.
    """
    if not finish.proves_settled:
        return []
    readings = [_unconfirmed.takes_in_the_announcement(finish)]
    current = _settlement.read_current_evidence(finish.state)
    if current is None or current.receipt != pending.receipt:
        _durable.takes_in_a_settlement(finish.gh, finish.issue, finish.state, pending.receipt, readings)
    read = [comment for comment in readings if comment is not None]
    for taken in read:
        if not stands_as_read(finish, attempt, taken, blank_aside=True):
            _unconfirmed.takes_in_the_attempt(finish, taken)
    moved = (reads_moving(finish, pending, attempt, comment) for comment in read)
    return [refused for refused in moved if refused is not None]


def moves_the_binding(finish: LandedFinish, movements: list[ReportEvidence]) -> list[ReportEvidence]:
    """Those of `movements`, read by the answer, that moved what a binding rests on.

    Every one, for a finish not held to the settled-evidence policy. Under it,
    a refusal of moved records naming none but the evidence records and the
    attempt's own members is none (`verification_durable.moves_only_the_evidence`):
    another road recording, settling, or retiring a transaction, a finish of
    this landing announcing it, or another road's attempt in its place moves
    no record a binding rests on -- an attempt another road put in place of
    the one captured holds the route over the comment as it stands instead
    (`rewrite_finish_rechecks.stands_as_read`). Told by the fields the refusal
    names, as the reading it was taken over spelled them, never by what the
    comment carries by the
    time it is asked, so an announcement put back since is none either. What
    those records moved to was asked of that very reading and kept beside the
    refusal (`reads_moving`) -- a blank of the captured attempt's base tip, a
    mark of movement, a revision outranking the evidence -- and is movement
    no refusal's names excuse, however the comment or the tick's state reads
    since.
    """
    if not finish.proves_settled:
        return movements
    return [moved for moved in movements if not _durable.moves_only_the_evidence(moved, _attempts._ATTEMPT_KEYS)]


def reads_moving(
    finish: LandedFinish,
    pending: _records.PendingEvidence,
    attempt: _commit_models.PinnedCommit,
    state: PinnedState,
) -> ReportEvidence | None:
    """The movement `state`, a comment the answer to `pending` read behind `attempt`, records; or None.

    `state` is the comment the answer starts from, one a refusal of moved
    bound records was read over, or the one the answer leaves the tick's
    state carrying -- an artifact's ledger entry committed alone takes the
    comment in whole (`verification_proof.ProofReading.reads`) -- or one the
    adoption of a settlement took (`adopts_the_answer`), and another road may
    have recorded movement on it before putting it back. The blank a proof
    records movement under the evidence with (`_BLANKED`): the base tip
    `attempt`, the one captured before the answer, recorded read blank beside
    every other member as `attempt` captured it -- or advanced by its own
    announcement (`rewrite_finish_rechecks.stands_as_read`). And, where
    `state` carries evidence current under `pending`'s receipt, the readiness
    proof's reading of the
    records alone under the settled-evidence policy
    (`rewrite_finish_readiness.settled_word`): the mark of movement in the
    handoff's place, a handoff naming the evidence that describes another
    head, a readable revision spent past it, or a review or report record
    moved; or, where it still carries `pending` owed -- whatever evidence is
    current beside it -- a review or report record moved off `pending`'s own
    binding (`verification_proof.recorded_verdict`), or a readable revision
    spent past it, the floor's or one a history entry shows beside a floor
    nobody can read (`rewrite_finish_outranking.outranks_the_owed`,
    `_SPENT_PAST`), so a settlement another road makes of
    `pending` once they are put back adopts none of it. Asked of that very
    reading, it is the movement it is however soon the records are put back,
    where a refusal naming the evidence records or the attempt's members alone
    is none (`moves_the_binding`). None for a finish not held to that policy,
    and where nothing moved under it: a plain settlement, `pending` still owed
    over the records it was bound to, or retired or superseded.
    """
    if not finish.proves_settled:
        return None
    unmoved = stands_as_read(finish, attempt, state, blank_aside=True)
    blanked = _TIP in attempt.moved(state.data)
    if unmoved and blanked and not _attempt_records._recorded_onto(state):
        return _BLANKED
    current = _settlement.read_current_evidence(state)
    if current is not None and current.receipt == pending.receipt:
        heard = _readiness._records_heard(current, state, settled=True)
    elif _record_state.read_pending_evidence(state) == pending:
        outranked = outranks_the_owed(state, pending)
        heard = (recorded_verdict(state, pending.binding), _SPENT_PAST if outranked else None)
    else:
        return None
    return next((refused for refused in heard if refused and not refused.holds), None)


def _proves_ready(finish: LandedFinish, current: _records.CurrentEvidence) -> FinishOutcome | None:
    """`current` proved ready again (`rewrite_finish_readiness.stands_ready`), read afresh behind its invalidation.

    Gone from the tick's state, `current` was invalidated -- over the comment
    or the tick's own copy -- so the comment is read afresh behind that write
    (`rewrite_finish_rechecks.rechecks_behind`): a newer transaction recorded,
    or another attempt put in place, right behind it holds the route, laid
    over the tick's state, rather than being routed past.
    """
    stopped = _readiness.stands_ready(finish, current)
    if _settlement.read_current_evidence(finish.state) == current or rechecks_behind(finish, current.receipt):
        return stopped
    return FinishOutcome.HELD
