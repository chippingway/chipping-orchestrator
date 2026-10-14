# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where a landed rewrite's finish takes a step under the dormant settled-evidence policy or the one every road selects.

A finish is held to one of two policies over the same order (`rewrite_finish`):
the one every production road hands over, which proves again only a
transaction an earlier finish captured for the landed head, and a dormant one
a caller selects only by building the finish with
`rewrite_finish_models.LandedFinish.proves_settled`. The dormant policy proves
evidence already settled for the head ready again
(`rewrite_finish_readiness.stands_ready`), and invalidates it into history
whole wherever anything it is bound to moved since it settled, at every step
that keeps, routes, or parks the attempt.

Each step here is one the coordinator and the settlement step
(`rewrite_finish_settlement`) take whichever policy holds the finish, and it
answers for both: a finish not held to the dormant policy goes on exactly as
the policy every road selects has it, reading nothing more.

- `stands_ready_if_settled` proves evidence settled current for the head
  ready, where any is, and -- behind the relabel -- holds a head with none to
  the base its replay was made onto.
- `ahead_of_the_park` proves that evidence and a captured transaction ahead of
  the park a debt with no room takes.
- `behind_the_announcement` and `behind_the_write` answer a step of the
  announcement or the route that stopped, or raised, with settled evidence
  proved ready once more, invalidated over a binding record a refusal read
  moved, and a captured transaction proved again whole -- behind a write
  nobody confirmed, over the attempt as that write may have left it
  (`rewrite_finish_unconfirmed`).
- `out_of_step` says why the records beside settled evidence hold the route.
- `retires_the_adopted` invalidates a settlement the settlement step's answer
  left current -- its own, or another road's it adopted -- over movement the
  answer read under its binding, the announcement a finish of this landing
  made of it aside, before anything is resolved afresh -- and, where another
  finish's route took the attempt off the comment meanwhile or another road
  replaced it, over the comment as it stands; and `stands_as_read` says
  whether the attempt that answer left is the one the finish captured:
  unmoved, or advanced by its own announcement.

Nothing here runs the configured commands, posts an artifact, launches a
developer, or announces anything.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import attempt_records as _attempt_records, attempts as _attempts
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
from orchestrator.workflow.engine.report_evidence_models import ReportEvidence
from orchestrator.workflow.engine.rewrite_evidence_proof import standing_refusal
from orchestrator.workflow.engine.rewrite_finish_announced import advanced_by_the_announcement
from orchestrator.workflow.engine.rewrite_finish_models import FinishOutcome, LandedFinish

log = logging.getLogger("orchestrator.workflow")


def stands_ready_if_settled(finish: LandedFinish, *, or_the_base: bool = False) -> FinishOutcome | None:
    """`stands_ready` over evidence settled current for `finish`'s landed head, where any is; None to go on.

    Asked only of a finish held to the dormant settled-evidence policy: any
    other finish goes on from here with nothing read. For a route whose
    evidence step left nothing recorded for the head
    (`rewrite_finish_settlement.settles`): where a newer transaction recorded
    beside settled evidence was abandoned, that evidence is still current,
    and the route may not carry it unproved. And for the retirement behind the
    relabel (`rewrite_finish`), the last write of the route, `or_the_base`
    set: the announcement and the relabel are requests made after the
    evidence was resolved, and a base advanced while they were answered has
    the route held with the attempt standing rather than retired over a head
    the base has left behind -- settled evidence proved ready over the landing
    and the base and invalidated over what moved, and a head with none
    current for it (the fresh reviewer's responsibility handed off, or
    evidence of the replaced head deferred) held to the base tip its replay
    was made onto alone, by the last word over the base
    (`rewrite_finish_captured.stands_before_the_route`), so the recovery
    continues the head to another rebase. Such a head carries no decision the
    landing could move under: a head pushed over it meanwhile is the pull
    request's to show the validating stage, which reads it afresh.
    An attempt that records no such tip -- one blanked to record movement
    under the evidence (`rewrite_finish_readiness`,
    `rewrite_recovery_parks.records_the_reset`), one blanked because the base
    moved while git ran, or a legacy attempt pinned before the tip was among
    its members -- proves nothing about which base the head was replayed
    onto, which every proof reads as refusing the evidence rather than the
    route: its head is held instead to the base this tick counted it against
    (`rewrite_evidence_proof.standing_refusal`), so a base advanced while the
    announcement or the relabel was answered still holds the route. Only a
    base that still reads as that count stands there: one advanced, one the
    local base ref was rewound or repointed under -- which leaves the remote
    unasked -- and one nobody could read each hold the route with the attempt
    standing, for the next tick's fetch to count the head again.
    """
    if not finish.proves_settled:
        return None
    current = _settlement.read_current_evidence(finish.state)
    stopped = None
    if current is not None and current.binding.target.target_head == finish.head:
        stopped = _readiness.stands_ready(finish, current)
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


def ahead_of_the_park(finish: LandedFinish) -> FinishOutcome | None:
    """Prove what an earlier finish made for the head ahead of the park a debt with no room takes; None to park.

    Nothing is read for a finish not held to the settled-evidence policy. For
    one that is, evidence already settled for the head is proved ready
    (`stands_ready_if_settled`): the park keeps it current for the reply that
    brings the route back, so anything read moving under it now is
    invalidated before the park, and putting that back before the reply
    revives nothing; a proof that holds holds the park too. A transaction
    captured for the head is proved again whole -- the settled report re-read
    at its location among it -- and held to the last word, and abandoned where
    anything moved (`rewrite_finish_captured.stands_before_the_route`), or,
    where another finish settled it while that abandonment was asked, its
    settlement invalidated over the movement instead.
    """
    if not finish.proves_settled:
        return None
    stopped = stands_ready_if_settled(finish)
    if stopped is not None or _captured.recorded(finish, logged=False) is None:
        return stopped
    return _captured.stands_before_the_route(finish, whole=True)


def behind_the_announcement(
    finish: LandedFinish, stopped: FinishOutcome | None, observed: list[ReportEvidence],
) -> FinishOutcome | None:
    """`stopped`, where the announcement or the debt's park stopped the route, behind the last word; None to route.

    The last word is taken over a transaction still recorded for the head
    behind any stop (`rewrite_finish_captured.stands_before_the_route`). A
    finish held to the settled-evidence policy -- which asks this behind an
    announcement or a park whose request raised as well, as UNCONFIRMED,
    before the error goes on -- proves settled evidence ready once more
    first, invalidated over a binding record a refusal read moved
    (`rewrite_finish_readiness.invalidates_behind`), and has the transaction
    proved again whole, since the notice was posted after the first proof:
    the first movement a guarded write's refusal read (`observed`) is handed
    to the word as its proof in place of the proof taken again, so a record
    put back before that word revives nothing, and a report edited while the
    notice was posted is read by the proof however soon it is put back after.
    Behind the record of the event or the checkpoint nobody confirmed, the
    bookkeeping either may have landed on the attempt is taken in first
    (`rewrite_finish_unconfirmed.takes_in_the_announcement`), so movement the
    proof reads is invalidated over the attempt as it stands rather than
    refused as though another attempt stood in its place.
    """
    if stopped is None:
        return None
    if not finish.proves_settled:
        return _captured.stands_before_the_route(finish, behind=stopped)
    if stopped is FinishOutcome.UNCONFIRMED:
        _unconfirmed.takes_in_the_announcement(finish)
    _readiness.invalidates_behind(finish, stopped, observed)
    moved = observed[0] if observed else None
    return _captured.stands_before_the_route(finish, proof=moved, behind=stopped, whole=True)


def behind_the_write(
    finish: LandedFinish, stopped: FinishOutcome, observed: list[ReportEvidence],
) -> FinishOutcome | None:
    """`stopped`, where the route's retirement did not land, behind proving settled evidence once more.

    A finish held to the settled-evidence policy invalidates settled evidence
    a refusal read a binding record moving under, or proves it ready once more
    where the refusal read none (`rewrite_finish_readiness.invalidates_behind`),
    so putting that record back first revives nothing; any other finish stops
    with nothing read.

    A retirement nobody confirmed may have landed all the same, taking the
    attempt every write recording movement is decided on -- and the base tip
    the movement is recorded by where history has no room -- with it.
    Settled evidence for the head is proved over the attempt as this finish
    read it, its base tip among it, so a retirement that landed reads no
    movement of its own. Where the proof reads movement -- the requirements
    edited, say, while the retirement was sent -- the evidence is invalidated
    over the attempt as read, which a retirement that did not land leaves in
    place; where that retirement landed instead, the attempt is put back
    first, exactly as this finish read it
    (`rewrite_finish_unconfirmed.stands_back`), and the same
    receipt invalidated over it -- or, with no room for its history entry,
    the movement recorded against it by blanking the base tip. The attempt
    standing again brings every later finish of this landing back to retire
    the evidence whole once room is made, however soon what moved is put
    back, and to retire the attempt behind it with nothing said or relabelled
    twice. A successor settled under another receipt, or another attempt in
    this one's place, is kept as its road wrote it.
    """
    if not finish.proves_settled:
        return stopped
    current = _settlement.read_current_evidence(finish.state)
    unconfirmed = stopped is FinishOutcome.UNCONFIRMED and current is not None
    if not unconfirmed or current.binding.target.target_head != finish.head:
        return _readiness.invalidates_behind(finish, stopped, observed)
    moved = _readiness.settled_word(finish, current)[0]
    if moved is None:
        return stopped
    invalidated = _readiness.invalidates(finish, current)
    if not invalidated and _unconfirmed.stands_back(finish, current):
        invalidated = _readiness.invalidates(finish, current)
    log.warning(
        "issue=#%d verification evidence revision %d settled for %.8s moved behind a retirement nobody confirmed "
        "(%s); invalidated: %s",
        finish.issue.number, current.revision, finish.head, moved.refusal, invalidated,
    )
    return stopped


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
    moves are no such movement (`verification_durable.moves_only_the_evidence`),
    nor the attempt's: the announcement a finish of this landing put on
    `attempt`, the one captured before the answer (`stands_as_read`), or any
    member where another finish's route or another road took `attempt` off
    the comment -- over which, holding the route whatever this says, the
    evidence is invalidated as the comment stands
    (`rewrite_finish_unconfirmed.retires_as_it_stands`). False, logged, where
    that invalidation did not land.
    """
    current = _settlement.read_current_evidence(finish.state)
    if not finish.proves_settled or current is None or current.receipt != pending.receipt:
        return True
    captured = stands_as_read(finish, attempt, finish.state)
    excused = advanced_by_the_announcement(finish, attempt, finish.state.data) if captured else _attempts._ATTEMPT_KEYS
    if all(_durable.moves_only_the_evidence(moved, excused or ()) for moved in movements):
        return True
    if captured:
        invalidated = _readiness.invalidates(finish, current)
    else:
        invalidated = _unconfirmed.retires_as_it_stands(finish, pending.receipt, attempt)
    if invalidated:
        return True
    log.warning(
        "issue=#%d holding the route of %.8s: verification evidence revision %d was read moving while it "
        "settled, and could not be invalidated",
        finish.issue.number, finish.head, pending.revision,
    )
    return False


def stands_as_read(finish: LandedFinish, attempt: _commit_models.PinnedCommit, state: PinnedState) -> bool:
    """Whether `state` carries the attempt `attempt` captured, so movement read under it is this finish's to retire.

    Unmoved; or -- for a finish held to the settled-evidence policy -- advanced
    by its own announcement alone, the mark and the record of its event put
    down for the landed head by a finish of this very landing
    (`rewrite_finish_announced.advanced_by_the_announcement`), which leaves
    the settlement that finish made this finish's to invalidate over what its
    answer read rather than an attempt another road put in its place.
    """
    if not attempt.moved(state.data):
        return True
    return finish.proves_settled and advanced_by_the_announcement(finish, attempt, state.data) is not None
