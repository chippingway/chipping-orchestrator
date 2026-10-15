# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a landed rewrite's pinned comment shows a revision spent past its settled evidence, per evidence policy.

A newer transaction recorded beside settled evidence and then abandoned or
dropped spent a revision past it for good: no reader is ever handed the
evidence it outranks. The readiness proof of that evidence
(`rewrite_finish_readiness`) asks `outranks` of every reading of the comment,
and reads a revision past the evidence as movement under it. The revisions
the comment shows spent are the handoff's and those of every history entry
that reads on its own -- so neither a floor nobody can read nor another entry
that will not read hides a newer one the history still shows -- and the
floor.

The two evidence policies read them alike save beside a pending record. The
one every road selects reads no revision past the evidence there at all: the
pending transaction may own the floor, and is the next finish's to answer.
The dormant settled-evidence policy
(`rewrite_finish_models.LandedFinish.proves_settled`) discounts only the one
revision a pending record may own -- the floor stands whole beside a readable
pending record that spent less, and one below it otherwise -- and counts the
revision minted just under a readable pending record, which another
transaction spent: of any two revisions spent past the evidence, at most one
is the pending record's. So a pending record holds that policy's route
without hiding a revision that independently outranks the evidence.

A finish held to that policy spends such a revision itself (`spends_past`)
where movement it read under the evidence fits nowhere else
(`rewrite_finish_marks.marks`): every reader of either policy then reads the
evidence outranked, its record kept whole.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_record_state as _record_state,
    verification_records as _records,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.verification_history_fields import historical_from


def outranks(state: PinnedState, current: _records.CurrentEvidence, *, settled: bool) -> bool:
    """Whether `state` shows a revision spent past `current`, as the dormant policy reads it where `settled`."""
    history = state.get(_records.EVIDENCE_HISTORY)
    if not isinstance(history, list):
        history = []
    readable = max((
        getattr(_settlement.read_evidence_handoff(state), "revision", 0),
        *(entry.revision for entry in map(historical_from, history) if entry),
    ))
    spent = _record_state._latest_revision(state) or 0
    beside = _record_state.carries_pending_evidence(state)
    if not settled:
        return not beside and max(spent, readable) > current.revision
    pending = _record_state.read_pending_evidence(state)
    if beside and getattr(pending, "revision", spent) >= spent:
        spent -= 1
    spent = max(spent, getattr(pending, "revision", 1) - 1)
    return max(spent, readable) > current.revision


def spends_past(state: PinnedState, current: _records.CurrentEvidence) -> bool:
    """Stage on `state` a revision spent past `current`, so every reader reads it outranked; whether one is.

    The revision floor raised one past `current`'s revision, a revision no
    transaction will carry: a write that keeps every record whole and grows
    the comment only where the floor gains a digit. Where a revision is spent
    past `current` already -- a pending record's among them, which settles
    over it or outranks it for good -- nothing is staged, so no floor is ever
    raised past a transaction that would then settle outranked. False, with
    nothing staged, where nobody can say what was spent.
    """
    spent = _record_state._latest_revision(state)
    if spent is None:
        return False
    if spent <= current.revision:
        state.set(_records.REVISION_FLOOR, current.revision + 1)
    return True
