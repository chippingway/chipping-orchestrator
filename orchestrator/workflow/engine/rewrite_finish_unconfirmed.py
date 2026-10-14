# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a finish's own write nobody confirmed, or another finish, left of its attempt, before movement is recorded.

The invalidation of settled evidence a proof read moving
(`rewrite_finish_readiness.invalidates`) is decided on the attempt as the
finish read it, so one another road put in its place refuses it. A finish's
own write can change that attempt too: the record of its `base_rebased`
event and the checkpoint put the announcement's bookkeeping on it -- the
record of the event and the mark, each naming the landed head -- and the
retirement behind the relabel blanks it whole, the base tip the movement is
recorded by where history has no room among it. A write whose answer was
lost may have landed all the same, and an invalidation decided on the attempt
as the tick read it is then refused as though another road had replaced it,
so movement a proof read behind that write would outlive it unrecorded and a
later finish would route the evidence once what moved was put back.

Only the dormant settled-evidence policy asks these
(`rewrite_finish_settled`), behind the write that went unconfirmed:

- `takes_in_the_announcement` takes in the announcement's bookkeeping where
  the comment read afresh carries this attempt otherwise exactly as the
  finish read it, those members naming the landed head
  (`rewrite_finish_announced.takes_in_the_announcement`), so the proof and
  the abandonment behind the record or the checkpoint are decided on the
  attempt as it stands, as the invalidation itself is.
- `stands_back` puts the attempt back exactly as the finish read it where the
  comment carries it blanked as the finish's own retirement leaves it, and the
  same evidence still current, so the movement is invalidated or recorded
  against it and every later finish of the landing comes back to retire the
  evidence whole. Where that write does not land -- a comment another road
  filled behind the retirement has no room for the attempt -- the movement is
  recorded by the receipt-scoped mark in place of the evidence's handoff
  (`rewrite_finish_marks.marks`), which a later finish of the landing, finding
  no attempt to finish, retires the evidence whole over once room is made
  (`retires_the_marked`).
- `retires_the_settled` invalidates a settlement another finish made while
  this finish's abandonment was asked (`rewrite_finish_captured._abandoned`).

A comment that would not read is asked once more, since the movement already
read has no other way to be recorded. Another attempt, other members moved,
or a successor settled under another receipt is left as its road wrote it.
"""
from __future__ import annotations

import copy
import logging

from orchestrator.git.base_sync import attempts as _attempts
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


def takes_in_the_announcement(finish: LandedFinish) -> None:
    """Lay the announcement's bookkeeping the comment carries for `finish`'s attempt over the tick's state.

    Only where every member of the attempt the comment read afresh carries
    otherwise than the tick read it is one the announcement writes, and names
    the landed head: what the record of the event or the checkpoint left,
    landed with its answer lost, or what another finish of the landing left
    announcing a settlement it made meanwhile. Taken in as read, so a write
    decided on the attempt behind it counts none of it as the tick's own move.
    Anything else leaves the tick's state as it was.
    """
    durable = read_afresh(finish)
    if durable is not None:
        _announced.takes_in_the_announcement(finish, durable)


def stands_back(finish: LandedFinish, current: _records.CurrentEvidence) -> bool:
    """Put the attempt `finish` read back where its own retirement took it off the comment; whether that landed.

    Only over a comment that carries every member of the attempt exactly as
    that retirement staged it (`rewrite_finish_writes.retirement`) -- blanked,
    so no other attempt stands in its place -- and still carries `current` as
    its current evidence, so no successor settled under another receipt is
    ever marked moved. Staged on that comment read afresh and committed
    guarded by it, the attempt's members alone written, every other field
    kept as the comment carries it; the tick's state then reads as the
    comment does.
    """
    durable = read_afresh(finish)
    left = _commit_models.PinnedCommit.capture(_writes.retirement(finish), prerequisites=_attempts._ATTEMPT_KEYS)
    if durable is None or left.moved(durable.data):
        return False
    if _settlement.read_current_evidence(durable) != current:
        return False
    marked = copy.deepcopy(durable)
    guard = _durable.guarded(durable, _attempts._ATTEMPT_KEYS, _attempts._ATTEMPT_KEYS)
    for member in _attempts._ATTEMPT_KEYS:
        durable.set(member, finish.state.get(member))
    if _durable.lands(finish.gh, finish.issue, finish.state, guard, durable) is None:
        return True
    marks(finish, marked, current, "the attempt its retirement took could not be put back")
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
    """Invalidate a settlement another finish made of `pending` while its abandonment was asked; whether it landed.

    None where the comment carries nothing current under `pending`'s receipt.
    Otherwise its records are taken in (`verification_durable.takes_in_a_settlement`)
    and invalidated over what the abandonment read (`why`)
    (`rewrite_finish_readiness.invalidates`): over this finish's attempt, or
    over the comment as it stands where that finish's route took it, which
    holds the route all the same.
    """
    settled = _durable.takes_in_a_settlement(finish.gh, finish.issue, finish.state, pending.receipt)
    if settled is None:
        return None
    log.info(
        "issue=#%d invalidating verification evidence revision %d another finish settled for %.8s while its "
        "abandonment was asked: %s",
        finish.issue.number, settled.revision, finish.head, why,
    )
    return _readiness.invalidates(finish, settled)
