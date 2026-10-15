# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Movement a dormant finish read under settled evidence, recorded however the attempt has moved since.

The invalidation is decided on the attempt as reconciled -- an announcement
of this landing taken in, a refused write read and retried once, for a
finish held to the dormant policy alone (`retires_over_the_attempt`) -- or,
where another finish's route or another road took the attempt, on the
comment as it stands (`retires_as_it_stands`), every attempt and successor
kept. Where history has no room, or the attempt
cannot be put back, the mark (`marks`) replaces the evidence's handoff with
one naming only the receipt that moved: no reader takes it for a handoff
(`verification_settled_fields.handoff_from`), and only a later finish finding
that very receipt current retires the evidence whole (`carries_the_mark`).
Where even the mark has no room, the evidence is retired whole at once, its
current record and the evidence records left null or unreadable removed.
"""
from __future__ import annotations

import logging

from orchestrator.git.base_sync import attempts as _attempts
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    pinned_commit_models as _commit_models,
    verification_durable as _durable,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.rewrite_finish_announced import (
    advanced_by_the_announcement,
    takes_in_the_announcement,
)
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

log = logging.getLogger("orchestrator.workflow")

# The one member of the mark, naming the receipt whose movement it records.
_MOVED = "moved"

# What an invalidation writes: the current record, and the history it enters.
_INVALIDATES = (_records.CURRENT_EVIDENCE, _records.EVIDENCE_HISTORY)

# What a compact one may remove as well: a pending record left null, and a
# handoff nobody can read (`verification_settlement_state.retire_current_evidence`).
_COMPACTS = (*_INVALIDATES, _records.PENDING_EVIDENCE, _records.EVIDENCE_HANDOFF)


def carries_the_mark(state: PinnedState, current: _records.CurrentEvidence) -> bool:
    """Whether `state` carries the mark of movement read under `current` in place of its handoff."""
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
    keeping whatever another road wrote there.
    """
    landed = _lands(finish, read_afresh(finish), current, marked=True)
    landed = landed or _lands(finish, read_afresh(finish), current, marked=True)
    landed = landed or _lands(finish, read_afresh(finish), current, compact=True)
    landed = landed or _lands(finish, read_afresh(finish), current, compact=True)
    log.warning(
        "issue=#%d recording movement read under verification evidence revision %d by marking its handoff, "
        "since %s: %s",
        finish.issue.number, current.revision, why, "landed" if landed else "not landed",
    )


def retires_over_the_attempt(
    finish: LandedFinish, current: _records.CurrentEvidence, *, as_it_stands: bool = True,
) -> bool | None:
    """Whether `current`'s invalidation landed over the attempt `finish` read, on the comment read afresh; or None.

    For a finish held to the settled-evidence policy, an announcement another
    finish of the landing put down on that attempt is taken in first
    (`rewrite_finish_announced.takes_in_the_announcement`), and a write
    refused -- an announcement landing under it among the reasons -- is read,
    reconciled, and made once more; any other finish reads and writes once,
    as the invalidation always has. False where the comment carries
    another evidence or another attempt, over which a finish held to the
    settled-evidence policy retires or marks the same receipt as the comment
    stands (`retires_as_it_stands`) unless `as_it_stands` is False. None where
    neither reading took the invalidation, for the tick's own copy to try.
    """
    first = _over_the_attempt(finish, current, as_it_stands)
    if first is None and finish.proves_settled:
        return _over_the_attempt(finish, current, as_it_stands)
    return first


def retires_as_it_stands(finish: LandedFinish, receipt: str, attempt: _commit_models.PinnedCommit) -> bool:
    """Invalidate the evidence the comment carries current under `receipt` over another attempt; whether it landed.

    Only where the comment no longer carries `attempt`, the one the finish
    captured, nor that attempt advanced by its own announcement. Staged on the
    comment read afresh and guarded by it (`_lands`), so the attempt standing
    is kept and a successor under another receipt refuses it; a comment that
    moved under the write -- a report put back meanwhile among it -- is read
    and retired once more. Where neither lands, for want of room among the
    reasons, the movement is marked instead (`marks`).
    """
    durable = read_afresh(finish)
    current = None if durable is None else _settlement.read_current_evidence(durable)
    if current is None or current.receipt != receipt:
        return False
    if advanced_by_the_announcement(finish, attempt, durable.data) is not None:
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
    finish: LandedFinish,
    durable: PinnedState | None,
    current: _records.CurrentEvidence,
    *,
    marked: bool = False,
    compact: bool = False,
) -> bool:
    """Whether `current`'s retirement into history -- or, `marked`, the mark of its movement -- landed over `durable`.

    `durable` is a reading of the comment that still has to carry `current`,
    and the write is guarded by it -- every bound record and the attempt.
    `compact` retires `current` whole even where the comment has no room for
    that as it stands, removing its current record and the evidence records
    left null or unreadable rather than leaving them null.
    """
    if durable is None or _settlement.read_current_evidence(durable) != current:
        return False
    if marked:
        guard = _durable.guarded(durable, (_records.EVIDENCE_HANDOFF,), _attempts._ATTEMPT_KEYS)
        durable.set(_records.EVIDENCE_HANDOFF, {_MOVED: current.receipt})
        return _durable.lands(finish.gh, finish.issue, finish.state, guard, durable) is None
    guard = _durable.guarded(durable, _COMPACTS if compact else _INVALIDATES, _attempts._ATTEMPT_KEYS)
    if not _settlement.retire_current_evidence(durable, compact=compact):
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
        if finish.proves_settled and as_it_stands:
            retires_as_it_stands(finish, current.receipt, attempt)
        return False
    if _settlement.read_current_evidence(durable) != current:
        return False
    return _lands(finish, durable, current) or None
