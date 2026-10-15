# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finish's own write nobody confirmed left of its attempt, before movement read behind it is recorded.

A write whose answer was lost may have landed: the record of the
`base_rebased` event or the checkpoint putting the announcement's
bookkeeping on the attempt, or the retirement behind the relabel blanking it
whole. These answer only a finish held to the dormant settled-evidence policy,
so movement a proof read behind that write is recorded over the attempt as it
stands rather than refused as though another road had replaced it. The
evidence phase asks `retires_the_settled` (`rewrite_finish_captured`); the
rest are primitives a caller holding such a finish asks directly, and the
coordinator (`rewrite_finish`) asks none of them yet:

- `takes_in_the_announcement` takes in that bookkeeping, naming the landed
  head (`rewrite_finish_announced.takes_in_the_announcement`), and hands back
  the comment it read.
- `stands_back` puts the attempt back exactly as read where the comment
  carries it blanked as this finish's retirement leaves it and the same
  evidence current, or -- where it no longer fits -- marks the movement
  (`rewrite_finish_marks.marks`); `retires_the_marked` lets a later finish
  finding no attempt retire marked evidence whole once room is made.
- `retires_the_settled` invalidates a settlement another finish made while
  this finish's abandonment was asked (`rewrite_finish_captured._abandoned`),
  and holds the route where a newer transaction came in beside it.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    rewrite_finish_announced as _announced,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_writes as _writes,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_marks import carries_the_mark, marks, read_afresh
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

log = logging.getLogger("orchestrator.workflow")


def takes_in_the_announcement(finish: LandedFinish) -> PinnedState | None:
    """Lay the announcement's bookkeeping the comment carries for `finish`'s attempt over the tick's state.

    Only where every member of the attempt the comment read afresh carries
    otherwise than the tick read it is one the announcement writes, and names
    the landed head: what the record of the event or the checkpoint left,
    landed with its answer lost, or what another finish of the landing left
    announcing a settlement it made meanwhile. Taken in as read, so a write
    decided on the attempt behind it counts none of it as the tick's own move.
    Anything else leaves the tick's state as it was. The comment that reading
    took comes back, for the caller to say what it read there; None where it
    would not read.
    """
    durable = read_afresh(finish)
    if durable is not None:
        _announced.takes_in_the_announcement(finish, durable)
    return durable


def stands_back(finish: LandedFinish, current: _records.CurrentEvidence) -> bool:
    """Put the attempt `finish` read back where its own retirement took it off the comment; whether that landed.

    Only over a comment that carries every member of the attempt exactly as
    that retirement staged it (`rewrite_finish_writes.retirement`) -- blanked,
    so no other attempt stands in its place -- and still carries `current` as
    its current evidence, so no successor settled under another receipt is
    ever marked moved. Staged on that comment read afresh and committed
    guarded by it, the attempt's members alone written -- each spelled as the
    finish read it, a member it read missing, as a legacy attempt leaves one,
    removed rather than written `null` -- and every other field kept as the
    comment carries it; the tick's state then reads as the comment does.
    Where that write is not seen to land -- no room, a refusal, or an answer
    lost -- the movement is marked (`rewrite_finish_marks.marks`): beside an
    attempt a lost answer did put back, every later readiness proof under
    the dormant policy reads that mark as movement and retires the evidence
    whole over it.
    """
    durable = read_afresh(finish)
    left = _commit_models.PinnedCommit.capture(_writes.retirement(finish), prerequisites=_attempts._ATTEMPT_KEYS)
    if durable is None or left.moved(durable.data):
        return False
    if _settlement.read_current_evidence(durable) != current:
        return False
    guard = _durable.guarded(durable, _attempts._ATTEMPT_KEYS, _attempts._ATTEMPT_KEYS)
    for member in _attempts._ATTEMPT_KEYS:
        durable.data.pop(member, None)
        if finish.state.carries(member):
            durable.set(member, finish.state.get(member))
    if _durable.lands(finish.gh, finish.issue, finish.state, guard, durable) is None:
        return True
    marks(finish, current, "the attempt its retirement took could not be put back")
    return False


def retires_the_marked(finish: LandedFinish) -> None:
    """Invalidate evidence settled for `finish`'s head that carries the movement mark, where no attempt stands.

    For a finish of the landing that finds its attempt retired -- every
    member blanked as a retirement leaves it -- and so reads nothing else: the
    comment carrying evidence current for the landed head with the mark of
    movement read under that very receipt in place of its handoff
    (`rewrite_finish_marks.carries_the_mark`) is movement an earlier finish
    recorded where neither its attempt nor history could carry it, and that
    evidence is invalidated into history whole now, its revision and binding
    kept, where room allows -- or left marked for the next finish. Evidence
    whose handoff stands, is missing, or will not read, a transaction pending,
    and an attempt another road pinned are left as they are.
    """
    current = _settlement.read_current_evidence(finish.state)
    if current is None or current.binding.target.target_head != finish.head:
        return
    left = _commit_models.PinnedCommit.capture(_writes.retirement(finish), prerequisites=_attempts._ATTEMPT_KEYS)
    if carries_the_mark(finish.state, current) and not left.moved(finish.state.data):
        _readiness.invalidates(finish, current)


def retires_the_settled(finish: LandedFinish, pending: _records.PendingEvidence, why: str) -> bool | None:
    """Invalidate a settlement another finish made of `pending` while its abandonment was asked; whether to go on.

    None where the comment carries nothing current under `pending`'s receipt.
    Otherwise its records are taken in (`verification_durable.takes_in_a_settlement`)
    and invalidated over what the abandonment read (`why`)
    (`rewrite_finish_readiness.invalidates`): over this finish's attempt, or
    over the comment as it stands where that finish's route took it, which
    holds the route all the same. False too where the records taken in carry
    a pending record beside that settlement -- a newer transaction another
    road recorded, readable or not -- which stands as that road wrote it for
    the next finish to answer, never one a route or continuation may leave
    owed behind a cleared attempt.
    """
    if _durable.takes_in_a_settlement(finish.gh, finish.issue, finish.state, pending.receipt) is None:
        return None
    settled = _settlement.read_current_evidence(finish.state)
    log.info(
        "issue=#%d invalidating verification evidence revision %d another finish settled for %.8s while its "
        "abandonment was asked: %s",
        finish.issue.number, settled.revision, finish.head, why,
    )
    invalidated = _readiness.invalidates(finish, settled)
    beside = _readiness.beside_current(finish.state, None)
    if beside:
        log.warning("issue=#%d holding the route of %.8s: %s", finish.issue.number, finish.head, beside)
    return invalidated and not beside
