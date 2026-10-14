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
- `stands_back` puts the attempt back exactly as the finish read it where the
  comment carries it blanked as the finish's own retirement leaves it, and the
  same evidence still current, so the movement is invalidated or recorded
  against it and every later finish of the landing comes back to retire the
  evidence whole.

A comment that would not read is asked once more, since the movement already
read has no other way to be recorded. Another attempt, other members moved,
or a successor settled under another receipt is left as its road wrote it.
"""
from __future__ import annotations

from orchestrator.git.base_sync import attempts as _attempts, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit as _commit,
    pinned_commit_models as _commit_models,
    rewrite_finish_writes as _writes,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

# The attempt's members the announcement writes: the record of its event, and the mark.
_ANNOUNCING = frozenset((_base_sync_state._PENDING_ANNOUNCED_EVENT, _base_sync_state._PENDING_ANNOUNCED_SHA))


def takes_in_the_announcement(finish: LandedFinish) -> None:
    """Lay the announcement's bookkeeping the comment carries for `finish`'s attempt over the tick's state.

    Only where every member of the attempt the comment read afresh carries
    otherwise than the tick read it is one the announcement writes, and names
    the landed head: what the record of the event or the checkpoint left,
    landed with its answer lost. Taken in as read, so a write decided on the
    attempt behind it counts none of it as the tick's own move. Anything else
    leaves the tick's state as it was.
    """
    durable = _read_afresh(finish)
    if durable is None:
        return
    read = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    moved = read.moved(durable.data)
    named = {durable.get(member) for member in moved}
    if not _ANNOUNCING.issuperset(moved) or not named <= {finish.head}:
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
    guard = _durable.guarded(durable, _attempts._ATTEMPT_KEYS, _attempts._ATTEMPT_KEYS)
    for member in _attempts._ATTEMPT_KEYS:
        durable.set(member, finish.state.get(member))
    return _durable.lands(finish.gh, finish.issue, finish.state, guard, durable) is None


def _read_afresh(finish: LandedFinish) -> PinnedState | None:
    """The pinned comment read afresh as the one `finish`'s state came from, asked once more where it would not read."""
    durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    if durable is None:
        durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    return durable
