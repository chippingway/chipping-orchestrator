# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a landed rewrite finish's own write nobody confirmed left of its attempt, before movement behind it is recorded.

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
  finish read it, those members naming the landed head, so the invalidation
  behind the record or the checkpoint is decided on the attempt as it stands.
  The same bookkeeping another finish of the landing put down announcing a
  settlement it made while this finish's abandonment was asked is taken in
  before that settlement is invalidated
  (`rewrite_finish_captured._abandoned`), for the same reason.
- `stands_back` puts the attempt back exactly as the finish read it where the
  comment carries it blanked as the finish's own retirement leaves it, and the
  same evidence still current, so the movement is invalidated or recorded
  against it and every later finish of the landing comes back to retire the
  evidence whole. Where that write does not land -- a comment another road
  filled behind the retirement has no room for the attempt -- the movement is
  recorded against the evidence itself instead, in a write that only shrinks
  the comment: its handoff dropped, which no reader hands evidence on without
  (`verification_current`), and which a later finish of the landing, finding
  no attempt to finish, retires the evidence whole over once room is made
  (`retires_the_marked`).

`advanced_by_the_announcement` tells an attempt a finish of this very landing
advanced -- its mark and the record of its event put down for the landed head
-- from one another road put in its place, for the announcement's
bookkeeping above and for a settlement adopted behind a finish's own answer
(`rewrite_finish_settled.stands_as_read`), whose movement that bookkeeping is
no part of (`rewrite_finish_settled.retires_the_adopted`).

A comment that would not read is asked once more, since the movement already
read has no other way to be recorded. Another attempt, other members moved,
or a successor settled under another receipt is left as its road wrote it.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Mapping
from typing import Any

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    pinned_commit_models as _commit_models,
    rewrite_finish_readiness as _readiness,
    rewrite_finish_writes as _writes,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

log = logging.getLogger("orchestrator.workflow")

# The attempt's members the announcement writes: the record of its event, and the mark.
_ANNOUNCING = frozenset((_base_sync_state._PENDING_ANNOUNCED_EVENT, _base_sync_state._PENDING_ANNOUNCED_SHA))


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
    durable = _read_afresh(finish)
    if durable is None:
        return
    read = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    moved = advanced_by_the_announcement(finish, read, durable.data)
    if moved is None:
        return
    for member in moved:
        finish.state.set(member, durable.get(member))
    _commit.takes_in(finish.state, durable.data, moved)


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
    durable = _read_afresh(finish)
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
    _marks(finish, marked, current)
    return False


def retires_the_marked(finish: LandedFinish) -> None:
    """Invalidate evidence settled for `finish`'s head that carries the movement mark, where no attempt stands.

    For a finish of the landing that finds its attempt retired -- every
    member blanked as a retirement leaves it -- and so reads nothing else: the
    comment carrying evidence current for the landed head with its handoff
    dropped is the movement a finish behind a retirement nobody confirmed
    recorded where it could not put the attempt back (`stands_back`), and that
    evidence is invalidated into history whole now, its revision and binding
    kept, where room allows -- or left marked for the next finish. Evidence
    whose handoff stands, a transaction pending, and an attempt another road
    pinned are left as they are.
    """
    current = _settlement.read_current_evidence(finish.state)
    if current is None or current.binding.target.target_head != finish.head:
        return
    left = _commit_models.PinnedCommit.capture(_writes.retirement(finish), prerequisites=_attempts._ATTEMPT_KEYS)
    marked = _settlement.read_evidence_handoff(finish.state) is None
    if marked and not left.moved(finish.state.data):
        _readiness.invalidates(finish, current)


def advanced_by_the_announcement(
    finish: LandedFinish, read: _commit_models.PinnedCommit, carried: Mapping[str, Any],
) -> tuple[str, ...] | None:
    """The attempt members `carried` spells otherwise than `read` captured, where its own announcement alone moved them.

    Every one has to be a member the announcement writes -- the mark, or the
    record of its event -- naming `finish`'s landed head: that is this very
    attempt advanced by a finish of its landing. None where any other member
    moved, or one names another head: another attempt, or another road's.
    """
    moved = read.moved(carried)
    named = {carried.get(member) for member in moved}
    if not _ANNOUNCING.issuperset(moved) or not named <= {finish.head}:
        return None
    return moved


def _marks(finish: LandedFinish, durable: PinnedState, current: _records.CurrentEvidence) -> None:
    """Record movement read under `current` by dropping its handoff, over `durable` as `stands_back` read it.

    Guarded by that reading -- the attempt blanked as the retirement left it
    and every bound record, `current` among them, as read -- so another
    attempt or a successor settled since refuses it. The write only shrinks
    the comment, so a comment with no room for the attempt still takes it.
    """
    guard = _durable.guarded(durable, (_records.EVIDENCE_HANDOFF,), _attempts._ATTEMPT_KEYS)
    durable.set(_records.EVIDENCE_HANDOFF, None)
    refused = _durable.lands(finish.gh, finish.issue, finish.state, guard, durable)
    log.warning(
        "issue=#%d could not put back the attempt its retirement took over verification evidence revision %d "
        "read moving; recording that movement by dropping its handoff: %s",
        finish.issue.number, current.revision, "landed" if refused is None else refused.refusal,
    )


def _read_afresh(finish: LandedFinish) -> PinnedState | None:
    """The pinned comment read afresh as the one `finish`'s state came from, asked once more where it would not read."""
    durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    if durable is None:
        durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    return durable
