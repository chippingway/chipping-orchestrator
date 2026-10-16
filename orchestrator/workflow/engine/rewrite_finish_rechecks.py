# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The comment the dormant evidence phase reads afresh behind an invalidation it landed, and the attempt it reads there.

An invalidation a finish held to the dormant settled-evidence policy
(`rewrite_finish_models.LandedFinish.proves_settled`) lands leaves the tick's
state carrying what its write sent -- over the comment read afresh, or over
the tick's own copy -- so a newer transaction of the head, or an attempt in
place of the one the finish read, that another road writes right behind that
write, before the invalidation returns, is one only a fresh reading finds.
That policy's evidence phase (`rewrite_finish_settlement.resolves`) asks
`rechecks_behind` behind every invalidation it lands: of settled evidence its
readiness proof read moving (`rewrite_finish_settled.stands_ready_if_settled`)
or took under a configuration no longer in place (`invalidates_rechecked`),
of a settlement it adopted (`rewrite_finish_settled.retires_the_adopted`),
and of one another finish made while its abandonment was asked
(`rewrite_finish_unconfirmed.retires_the_settled`) -- and behind an
abandonment that landed, whose strict edit another finish's settlement may
land right behind (`rewrite_finish_unconfirmed.reconciles_the_abandonment`).

- `stands_as_read` says whether a comment carries the attempt a finish
  captured: unmoved, advanced by its own announcement alone, or -- where
  asked -- with its base tip read blank, which records movement rather than
  another attempt.
- `rechecks_behind` reads the comment afresh, lays its evidence records over
  the tick's state, and holds over a pending record, or over another attempt,
  which it lays over the tick's state too -- and over the evidence it
  invalidated put back current, which it retires again first.
- `invalidates_rechecked` is the readiness proof's invalidation
  (`rewrite_finish_readiness.invalidates`) with that reading behind it.
- `stands_afresh` reads the comment afresh behind the proof ahead of a
  relabel (`rewrite_finish_stops.relabels`), whose requests another road may
  put an attempt of its own in place behind, and says whether it still
  carries the attempt captured ahead of that proof -- settled evidence that
  reading records moving invalidated first, however soon it is put back, a
  successor it carries in that evidence's place asked on its own binding.
- `lays` lays fields of a comment read afresh over the tick's state, each
  taken in as read.

No production road builds such a finish, so no production road asks any of
these.
"""
from __future__ import annotations

import logging
from collections.abc import Collection

from orchestrator.git.base_sync import (
    attempt_records as _attempt_records,
    attempts as _attempts,
    state as _base_sync_state,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    pinned_commit_models as _commit_models,
    rewrite_finish_readiness as _readiness,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_announced import (
    advanced_by_the_announcement,
    takes_in_the_announcement,
)
from orchestrator.workflow.engine.rewrite_finish_marks import read_afresh, retires_as_it_stands
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

log = logging.getLogger("orchestrator.workflow")

# Every member of the attempt but the base tip its replay was recorded as made
# onto, which a proof blanks to record movement read under the evidence where
# nothing else has room (`rewrite_finish_readiness._invalidates_on_the_tick`):
# a comment carrying these as the attempt captured them, its tip blank, still
# carries that attempt (`stands_as_read`).
_UNMARKED = frozenset(
    member for member in _attempts._ATTEMPT_KEYS if member != _base_sync_state._PENDING_REWRITE_BASE
)

# Why a fresh reading carrying another attempt holds the route (`rechecks_behind`).
_REPLACED = "another attempt stands in place of the one this finish read"


def stands_as_read(
    finish: LandedFinish, attempt: _commit_models.PinnedCommit, state: PinnedState, *, blank_aside: bool = False,
) -> bool:
    """Whether `state` carries the attempt `attempt` captured, so movement read under it is this finish's to retire.

    Unmoved; or -- for a finish held to the settled-evidence policy -- advanced
    by its own announcement alone, the mark and the record of its event put
    down for the landed head by a finish of this very landing
    (`rewrite_finish_announced.advanced_by_the_announcement`), which leaves
    the settlement that finish made this finish's to invalidate over what its
    answer read rather than an attempt another road put in its place.
    `blank_aside` sets the base tip aside where `state` reads it blank: the
    blank a proof records movement under the evidence with is no other
    attempt, where a readable tip other than the one captured is.
    """
    if blank_aside and not _attempt_records._recorded_onto(state):
        attempt = attempt.held_to(_UNMARKED)
    if not attempt.moved(state.data):
        return True
    return finish.proves_settled and advanced_by_the_announcement(finish, attempt, state.data) is not None


def rechecks_behind(finish: LandedFinish, receipt: str, durable: PinnedState | None = None) -> bool:
    """Whether the comment read afresh behind an invalidation that landed leaves the route free, laid over the state.

    `receipt` names the evidence that write invalidated, and `durable` is the
    comment a caller already read afresh behind it, where it has one. That
    invalidation leaves the tick's state carrying what its write sent, so
    another road's write right behind it, before the invalidation returns, is
    one only a fresh reading finds. Every evidence record that reading carries
    is laid over the tick's state as read (`lays`), so a pending record among
    them -- readable or not -- stands there as its road wrote it, owed for the
    next finish to answer. Evidence carried current under `receipt` again --
    put back, its bound records with it or not -- revives none of the
    movement read under it: it is retired again over the comment as it stands
    (`_revived`), where evidence settled under another receipt is kept as its
    road wrote it -- save a successor that very reading disproves on its own
    binding, which is invalidated whole, however soon its records are put
    back. Its attempt is read against the one the tick's state
    carries as the invalidation left it (`stands_as_read`, the base tip aside
    where it reads blank): one advanced by this landing's own announcement
    alone has that bookkeeping taken in
    (`rewrite_finish_announced.takes_in_the_announcement`), and any other is
    laid over the tick's state whole, so the caller holds over it rather than
    routing past it, or answering a successor under the movement read under
    the evidence it follows. False, logged, where a pending record, that
    evidence, or another attempt stands, or where the comment would not read,
    since nobody can then say none does.
    """
    left = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    durable = read_afresh(finish) if durable is None else durable
    beside = "the pinned comment would not read again"
    if durable is not None:
        held = _settlement.read_current_evidence(finish.state)
        lays(finish.state, durable, _durable._EVIDENCE_RECORDS)
        beside = _revived(finish, receipt, durable, held) or _readiness.beside_current(durable, None)
        if stands_as_read(finish, left, durable, blank_aside=True):
            takes_in_the_announcement(finish, durable)
        else:
            lays(finish.state, durable, _attempts._ATTEMPT_KEYS)
            beside = beside or _REPLACED
    if not beside:
        return True
    log.warning(
        "issue=#%d holding the route of %.8s behind the invalidation of its verification evidence: %s",
        finish.issue.number, finish.head, beside,
    )
    return False


def invalidates_rechecked(finish: LandedFinish, current: _records.CurrentEvidence) -> bool:
    """Whether `current`'s invalidation landed and the comment read afresh behind it leaves the route free.

    The readiness proof's invalidation (`rewrite_finish_readiness.invalidates`),
    which logs nothing of its own, and -- only where it landed -- the fresh
    reading behind it (`rechecks_behind`).
    """
    return _readiness.invalidates(finish, current) and rechecks_behind(finish, current.receipt)


def stands_afresh(finish: LandedFinish, attempt: _commit_models.PinnedCommit, observed) -> bool:
    """Whether the comment read afresh still carries the attempt `attempt` captured, its base tip aside where blank.

    Always, with nothing read, for a finish not held to the dormant
    settled-evidence policy. False, logged, where another attempt stands there or the comment would
    not read, so nothing is made over an attempt not the finish's own. Where
    it stands, the bookkeeping a finish of this landing put on it meanwhile --
    the record of its relabel among it -- is taken in
    (`rewrite_finish_announced.takes_in_the_announcement`), so a relabel
    another finish made is read made rather than made twice. `observed`, the
    reading the route's writes collect refusals on
    (`rewrite_finish_stops.observing`), is asked what that very comment
    records moving under the evidence (`_goes_on_over`) -- a successor another
    road settled in its place asked on its own binding -- so a report another
    road moved and puts back before the writes behind it is still movement.
    That is asked whatever attempt the reading carries: beside another
    attempt the evidence it reads moving is retired, or marked, over the
    comment as it stands (`rewrite_finish_readiness.invalidates`), that
    attempt kept, before the route holds, so putting both back revives
    nothing.
    """
    if not finish.proves_settled:
        return True
    durable = read_afresh(finish)
    goes_on = durable is not None and _goes_on_over(finish, durable, observed)
    if goes_on and stands_as_read(finish, attempt, durable, blank_aside=True):
        takes_in_the_announcement(finish, durable)
        return True
    log.warning(
        "issue=#%d holding the route of %.8s: the pinned comment would not read again, or another attempt "
        "stands in place of the one this finish holds",
        finish.issue.number, finish.head,
    )
    return False


def _goes_on_over(finish: LandedFinish, durable: PinnedState, observed) -> bool:
    """Whether the route may go on over `durable`, settled evidence it reads moving invalidated first.

    `durable` is asked of `observed`'s classifier as it was read
    (`verification_proof.ProofReading.reads`): settled evidence for the head
    it records moving -- a review or report record moved off its binding, a
    mark, a revision spent past it, a blank of the base tip -- is invalidated
    whole now, however soon what moved is put back, and the comment read
    afresh behind that write (`invalidates_rechecked`). That classifier was
    captured for the evidence the tick holds, so a successor another road
    settled for the head, which `durable` carries current in its place, is
    asked of its own binding in that very reading instead
    (`rewrite_finish_readiness._records_heard`), the movement kept on
    `observed` beside the rest; where it moved, the evidence records `durable`
    carries are laid over the tick's state (`lays`) and the successor is the
    evidence invalidated, so putting its records back revives nothing. False,
    for the route to hold, where that did not land or another road's record or
    attempt stands behind it.
    """
    before = len(observed.observed)
    observed.reads(durable)
    carried = _settlement.read_current_evidence(durable)
    held = _settlement.read_current_evidence(finish.state)
    successor = carried is not None and carried != held
    successor = successor and carried.binding.target.target_head == finish.head
    if successor:
        heard = _readiness._records_heard(carried, durable, settled=True)
        observed.observed.extend(refused for refused in heard if refused and not refused.holds)
    if all(refused.holds for refused in observed.observed[before:]):
        return True
    if successor:
        lays(finish.state, durable, _durable._EVIDENCE_RECORDS)
        held = carried
    if held is None or held.binding.target.target_head != finish.head:
        return True
    return invalidates_rechecked(finish, held)


def lays(state: PinnedState, durable: PinnedState, fields: Collection[str] = _durable._EVIDENCE_RECORDS) -> None:
    """Lay each of `fields` over `state` as `durable`, a comment read afresh, spells it, every one taken in as read.

    The evidence records by default. A field `durable` lacks is dropped from `state`. Each is remembered as
    read (`pinned_commit.takes_in`), so a guarded write decided behind this
    counts none of them as the tick's own move.
    """
    for field in fields:
        state.data.pop(field, None)
        if field in durable.data:
            state.set(field, durable.get(field))
    _commit.takes_in(state, durable.data, fields)


def _revived(
    finish: LandedFinish, receipt: str, durable: PinnedState, held: _records.CurrentEvidence | None,
) -> str:
    """Why evidence current in the tick's state, as `durable`, a fresh reading, laid it, holds the route; or "".

    Evidence current under `receipt` was just invalidated over movement read
    under it, so its coming back current -- another road putting the comment
    back as it read before -- makes it nothing anybody may rely on again: it
    is retired over the comment as it stands, whatever attempt that carries
    (`rewrite_finish_marks.retires_as_it_stands`), or its movement marked
    where that has no room, and the route is held either way, so the next
    finish reads what stands. A successor another road settled for the head
    under another receipt -- evidence the tick's state did not hold current
    before that reading (`held`), so not evidence standing beside a
    transaction this finish abandoned -- is asked of its own binding in that very reading
    (`rewrite_finish_readiness._records_heard`): where `durable` disproves it,
    it is invalidated whole, its provenance kept, or its movement marked
    (`rewrite_finish_readiness.invalidates`), however soon its records are put
    back, and the route held too. "" where no evidence is current there, or a
    successor nothing in that reading moved under.
    """
    current = _settlement.read_current_evidence(finish.state)
    if current is None or current.binding.target.target_head != finish.head:
        return ""
    why = "the verification evidence it invalidated was put back current"
    if current.receipt != receipt:
        heard = () if current == held else _readiness._records_heard(current, durable, settled=True)
        if all(not refused or refused.holds for refused in heard):
            return ""
        why = "a successor settled in its place was read moving on its own binding"
    retired = retires_as_it_stands(finish, receipt) if current.receipt == receipt else _readiness.invalidates(
        finish, current,
    )
    return f"{why}, and is retired" if retired else f"{why}, and could not be retired"
