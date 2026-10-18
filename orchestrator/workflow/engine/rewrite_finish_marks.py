# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Movement a finish read under settled evidence, recorded however the attempt has moved since.

The invalidation is decided on the attempt as reconciled -- an announcement
of this landing taken in, a refused write read and retried once
(`retires_over_the_attempt`) -- or,
where another finish's route or another road took the attempt, on the
comment as it stands (`retires_as_it_stands`), every attempt and successor
kept. Where history has no room, the attempt cannot be put back, or no write
over the tick's own copy lands, the mark (`marks`) replaces the evidence's
handoff with one naming only the receipt that moved: no reader takes it for a
handoff (`verification_settled_fields.handoff_from`), every later readiness
proof of that very receipt reads it as the movement it is (`carries_the_mark`,
`rewrite_finish_readiness.settled_word`) and retires the evidence whole once
room is made, and a later finish finding no
attempt does the same (`rewrite_finish_unconfirmed.retires_the_marked`).
Where even the mark has no room, the evidence is retired whole at once, its
current record and the evidence records left null or unreadable removed --
or, where not even that fits, a revision is spent past it
(`rewrite_finish_outranking.spends_past`), its record kept current and
whole, which every reader reads outranked and every later readiness proof
retires whole once room is made. Where the
floor has no room to gain the digit that takes, the evidence is retired whole
with the floor taken off to make room (`rewrite_finish_outranking.unfloors`),
its history entry carrying the revision the floor did.

Every readiness proof's invalidation asks these
(`rewrite_finish_readiness.invalidates`), on the finish's roads and the
recovery's alike; the evidence phase retires a settlement it adopted as the
comment stands too (`rewrite_finish_settled.retires_the_adopted`), as the
coordinator does evidence read moving behind a retirement nobody confirmed
where another attempt stands (`rewrite_finish_stops.behind_the_write`).
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_announced import takes_in_the_announcement
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish
from orchestrator.workflow.engine.rewrite_finish_outranking import spends_past, unfloors

log = logging.getLogger("orchestrator.workflow")

# The one member of the mark, naming the receipt whose movement it records.
_MOVED = "moved"

# What an invalidation writes: the current record, and the history it enters.
_INVALIDATES = (_records.CURRENT_EVIDENCE, _records.EVIDENCE_HISTORY)

# What a compact one may remove as well: a pending record left null, and a
# handoff nobody can read (`verification_settlement_state.retire_current_evidence`).
_COMPACTS = (*_INVALIDATES, _records.PENDING_EVIDENCE, _records.EVIDENCE_HANDOFF)

# How `_lands` records the movement, and what each writes: by retiring the
# evidence into history, by the mark in its handoff's place, by retiring it
# whole compactly, where not even that fits by spending a revision past it on
# the floor, and where the floor cannot grow by retiring it whole without it.
_RETIRES = "retires"

_MARKS = "marks"

_RETIRES_WHOLE = "retires whole"

_SPENDS = "spends"

_UNFLOORS = "retires whole without its floor"

_WRITES = MappingProxyType({
    _RETIRES: _INVALIDATES,
    _MARKS: (_records.EVIDENCE_HANDOFF,),
    _RETIRES_WHOLE: _COMPACTS,
    _SPENDS: (_records.REVISION_FLOOR,),
    _UNFLOORS: (*_COMPACTS, _records.REVISION_FLOOR),
})

# What `marks` tries, each over the comment read afresh and once more where
# the comment moved under its edit: the mark, the whole retirement, the
# revision spent, then the whole retirement without the floor.
_RECORDINGS = (_MARKS, _MARKS, _RETIRES_WHOLE, _RETIRES_WHOLE, _SPENDS, _SPENDS, _UNFLOORS, _UNFLOORS)


def carries_the_mark(state: PinnedState | None, current: _records.CurrentEvidence) -> bool:
    """Whether `state` carries the mark of movement read under `current` in place of its handoff; False for no state."""
    if state is None:
        return False
    return state.get(_records.EVIDENCE_HANDOFF) == {_MOVED: current.receipt}


def marks(finish: LandedFinish, current: _records.CurrentEvidence, why: str) -> None:
    """Record movement read under `current` by the mark in place of its handoff, over the comment afresh, where `why`.

    Only where that comment still carries `current` as current, guarded by it
    (`_lands`), so a successor settled since refuses it; a comment that moved
    under the edit, a report put back meanwhile among it, is read and marked
    once more. Where even the mark finds no room -- a handoff missing or
    shorter than it -- `current` is retired whole at once, made to fit by
    removing the records left null or unreadable (`_lands`), save beside a
    pending transaction, whose revision already outranks it; that retirement
    too is read and made once more where the comment moved under its edit,
    keeping whatever another road wrote there. Where not even that fits --
    the comment full and no evidence record left to remove -- a revision is
    spent past `current` on the floor instead
    (`rewrite_finish_outranking.spends_past`), read and spent once more
    likewise. `current` stays current with its whole binding, revision, and
    transcript digest, so no provenance is lost, while every reader reads it
    outranked: nothing put back meanwhile makes it evidence anybody relies on
    again, and every later readiness proof reads that as movement and retires
    it whole into history once room is made. Where the floor would gain a
    digit the comment has no room for, or nobody can say what was spent,
    `current` is retired whole into history after all, read and made once more
    likewise, with the floor taken off to
    make room (`rewrite_finish_outranking.unfloors`) -- only where it shows no
    revision past `current`, whose entry carries the revision it did -- so
    the run's provenance and its movement both stand; nobody can then say
    what was spent, and nothing is minted for the issue until the floor is
    put back.
    """
    landed = "not landed"
    for how in _RECORDINGS:
        if _lands(finish, read_afresh(finish), current, how):
            landed = f"landed as it {how}"
            break
    log.warning(
        "issue=#%d recording movement read under verification evidence revision %d by marking its handoff "
        "or as room allows, since %s: %s",
        finish.issue.number, current.revision, why, landed,
    )


def retires_over_the_attempt(
    finish: LandedFinish, current: _records.CurrentEvidence, *, as_it_stands: bool = True,
) -> bool | None:
    """Whether `current`'s invalidation landed over the attempt `finish` read, on the comment read afresh; or None.

    An announcement another finish of the landing put down on that attempt is
    taken in first (`rewrite_finish_announced.takes_in_the_announcement`), and
    a write refused -- an announcement landing under it among the reasons --
    is read, reconciled, and made once more. False where the comment carries
    another evidence or another attempt, over which the same receipt is
    retired or marked as the comment stands (`retires_as_it_stands`) unless
    `as_it_stands` is False. None where
    neither reading took the invalidation, for the tick's own copy to try.
    """
    first = _over_the_attempt(finish, current, as_it_stands)
    if first is None:
        return _over_the_attempt(finish, current, as_it_stands)
    return first


def retires_as_it_stands(finish: LandedFinish, receipt: str) -> bool:
    """Invalidate the evidence current under `receipt` over whatever attempt the comment carries; whether it landed.

    For a caller that found the attempt it captured gone -- another finish's
    route or another road took it -- and holds the route whatever this
    answers: the comment read afresh may carry another attempt, none, or the
    very one captured put back meanwhile, and the movement already read
    retires the evidence over whichever it is. Staged on that reading and
    guarded by it (`_lands`), so the attempt standing is kept and a successor
    under another receipt refuses it; a comment that moved under the write --
    a report put back meanwhile among it -- is read and retired once more.
    Where neither lands, for want of room among the reasons, the movement is
    marked instead (`marks`).
    """
    durable = read_afresh(finish)
    current = None if durable is None else _settlement.read_current_evidence(durable)
    if current is None or current.receipt != receipt:
        return False
    if _lands(finish, durable, current) or _lands(finish, read_afresh(finish), current):
        return True
    marks(finish, current, "its invalidation did not land over the attempt that stands")
    return False


def read_afresh(finish: LandedFinish) -> PinnedState | None:
    """The pinned comment read afresh as the one `finish`'s state came from, asked once more where it would not read."""
    durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    if durable is None:
        durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    return durable


def _lands(
    finish: LandedFinish, durable: PinnedState | None, current: _records.CurrentEvidence, how: str = _RETIRES,
) -> bool:
    """Whether the movement read under `current` was recorded over `durable` as `how` records it.

    `durable` is a reading of the comment that still has to carry `current`,
    and the write is guarded by it -- every bound record and the attempt.
    `_RETIRES` retires `current` into history and `_MARKS` writes the mark of
    its movement in its handoff's place. `_RETIRES_WHOLE` retires it even
    where the comment has no room for that as it stands, removing its current
    record and the evidence records left null or unreadable rather than
    leaving them null. `_SPENDS` spends a revision past it on the floor,
    keeping its record whole, and lands with nothing sent where one already is.
    `_UNFLOORS` retires it whole as `_RETIRES_WHOLE` does, and where that
    does not fit takes a floor showing nothing past it off first.
    """
    if durable is None or _settlement.read_current_evidence(durable) != current:
        return False
    guard = _durable.guarded(durable, _WRITES[how], _attempts._ATTEMPT_KEYS)
    if how == _MARKS:
        durable.set(_records.EVIDENCE_HANDOFF, {_MOVED: current.receipt})
        staged = True
    elif how == _SPENDS:
        staged = spends_past(durable, current)
    else:
        staged = _settlement.retire_current_evidence(durable, compact=how != _RETIRES)
    if not staged and how == _UNFLOORS and unfloors(durable, current):
        staged = _settlement.retire_current_evidence(durable, compact=True)
    if not staged:
        return False
    return _durable.lands(finish.gh, finish.issue, finish.state, guard, durable) is None


def _over_the_attempt(finish: LandedFinish, current: _records.CurrentEvidence, as_it_stands: bool) -> bool | None:
    """One reading of `retires_over_the_attempt`: landed, refused for good (False), or not taken (None)."""
    durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    if durable is None:
        return None
    takes_in_the_announcement(finish, durable)
    attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    if attempt.moved(durable.data):
        if as_it_stands:
            retires_as_it_stands(finish, current.receipt)
        return False
    if _settlement.read_current_evidence(durable) != current:
        return False
    return _lands(finish, durable, current) or None
