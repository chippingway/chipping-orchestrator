# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Movement a dormant finish read under settled evidence, recorded where its own attempt cannot carry it.

A finish held to the dormant settled-evidence policy invalidates evidence a
proof read moving over the attempt as it read it
(`rewrite_finish_readiness.invalidates`), and with no room for the history
entry blanks that attempt's base tip. Where the comment no longer carries
that attempt -- another finish's route retired it while this finish's
requests were answered, or another road put a new one in its place -- the
evidence still current under the receipt read moving is retired over the
comment as it stands (`holds_the_attempt`, `retires_as_it_stands`), every
attempt and successor kept as its road wrote it. Where history has no room, or the attempt cannot
be put back (`rewrite_finish_unconfirmed.stands_back`), the movement is
recorded by the mark (`marks`): the evidence's handoff replaced by one naming
only the receipt that moved. No reader takes it for a handoff
(`verification_settled_fields.handoff_from`), so none hands that evidence
on, and only a later finish of the landing finding that very receipt current
under it retires the evidence whole (`carries_the_mark`) -- a handoff that is
missing or will not read is no mark.
"""
from __future__ import annotations

import copy
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


def carries_the_mark(state: PinnedState, current: _records.CurrentEvidence) -> bool:
    """Whether `state` carries the mark of movement read under `current` in place of its handoff."""
    return state.get(_records.EVIDENCE_HANDOFF) == {_MOVED: current.receipt}


def marks(finish: LandedFinish, durable: PinnedState, current: _records.CurrentEvidence, why: str) -> None:
    """Record movement read under `current` by the mark in place of its handoff, over `durable` as read, where `why`.

    Guarded by that reading -- the attempt and every bound record, `current`
    among them, as read -- so another attempt or a successor settled since
    refuses it. The mark is shorter than any handoff, so a comment with no
    room for the attempt or the history entry still takes it.
    """
    guard = _durable.guarded(durable, (_records.EVIDENCE_HANDOFF,), _attempts._ATTEMPT_KEYS)
    durable.set(_records.EVIDENCE_HANDOFF, {_MOVED: current.receipt})
    refused = _durable.lands(finish.gh, finish.issue, finish.state, guard, durable)
    log.warning(
        "issue=#%d recording movement read under verification evidence revision %d by marking its handoff, "
        "since %s: %s",
        finish.issue.number, current.revision, why, "landed" if refused is None else refused.refusal,
    )


def holds_the_attempt(finish: LandedFinish, durable: PinnedState, receipt: str, *, as_it_stands: bool = True) -> bool:
    """Whether `durable`, read afresh, carries the attempt `finish` read, so evidence is decided on it.

    An announcement another finish of the landing put down on that attempt
    meanwhile is taken in first (`rewrite_finish_announced.takes_in_the_announcement`).
    Over any other attempt, a finish held to the settled-evidence policy
    retires the evidence current under `receipt` over the comment as it
    stands, or marks it (`retires_as_it_stands`) -- unless `as_it_stands` is
    False -- and the answer is False all the same.
    """
    takes_in_the_announcement(finish, durable)
    attempt = _commit_models.PinnedCommit.capture(finish.state, prerequisites=_attempts._ATTEMPT_KEYS)
    if not attempt.moved(durable.data):
        return True
    if finish.proves_settled and as_it_stands:
        retires_as_it_stands(finish, receipt, attempt)
    return False


def retires_as_it_stands(finish: LandedFinish, receipt: str, attempt: _commit_models.PinnedCommit) -> bool:
    """Invalidate the evidence the comment carries current under `receipt` over another attempt; whether it landed.

    Only where the comment no longer carries `attempt`, the one the finish
    captured, nor that attempt advanced by its own announcement. Staged on the
    comment read afresh and guarded by it, so the attempt standing is kept and
    a successor under another receipt, or a write since, refuses it; where
    history has no room, the movement is marked instead (`marks`).
    """
    durable = read_afresh(finish)
    current = None if durable is None else _settlement.read_current_evidence(durable)
    if current is None or current.receipt != receipt:
        return False
    if advanced_by_the_announcement(finish, attempt, durable.data) is not None:
        return False
    marked = copy.deepcopy(durable)
    guard = _durable.guarded(durable, _INVALIDATES, _attempts._ATTEMPT_KEYS)
    if _settlement.retire_current_evidence(durable):
        refused = _durable.lands(finish.gh, finish.issue, finish.state, guard, durable)
        if refused is None:
            return True
    marks(finish, marked, current, "its invalidation did not land over the attempt that stands")
    return False


def read_afresh(finish: LandedFinish) -> PinnedState | None:
    """The pinned comment read afresh as the one `finish`'s state came from, asked once more where it would not read."""
    durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    if durable is None:
        durable = _durable.durable_comment(finish.gh, finish.issue, finish.state)[0]
    return durable
