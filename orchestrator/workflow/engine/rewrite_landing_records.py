# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the evidence records say a finish of a landed base rewrite already did for the head it published.

A finish records evidence for a head only once it has seen the push of that
head land: a pending transaction, current evidence it settled, a history
entry it retired, or a failed run's notice (`rewrite_finish_failures`). It
resolves that evidence before it announces the head, so a tick lost in
between leaves those records with no announcement mark beside them, and they
are the one durable word that the push landed at all.

`saw_land` is that word: whether any record names the head. The recovery's
coordinator (`rewrite_recovery`) reads a replay the remote no longer stands on,
beside such a record, as a publication somebody rolled back out of band rather
than one never made, and parks it rather than pushing it again over the
rollback -- the guard the announcement mark gives a head already announced.
The evidence history keeps only its latest entries, so records another road
writes can push a retired run out of it; the receipt below outlives that, and
answers for the replay the attempt's record names.

Whose a pending transaction is, is the attempt's own word: the finish puts
the transaction's receipt on the attempt in the very write that records it
(`records`, `pending_auto_base_rebase_evidence_receipt`), so a transaction
under that receipt is the finish's (`captured`), and one under any other --
or beside an attempt whose finish recorded none -- was recorded by another
road, whatever the head it names, the replay the attempt's record names, or
the evidence records say. An attempt from before that receipt existed
recorded its evidence only behind its announcement mark, so with no receipt
on it, a transaction about the head the mark names is that finish's. The
recovery's helpers (`rewrite_landing_moved`) abandon only that transaction,
and the receipt goes with the rest of the attempt when it ends. A receipt
naming no pending transaction is a capture this landing already answered --
settled or retired, whether or not the history still keeps it
(`capture_answered`) -- so a later finish decides and runs nothing afresh,
and holds over any record another road left pending beside it.

`settled` is the evidence such a finish settled for the head and left
current: the evidence the readiness proof (`rewrite_finish_readiness`) proves
ready again and invalidates where the landing is read moving under it, as a
captured transaction is abandoned, so restoring the landing revives no
decision taken over it. The recovery's helpers read it wherever a snapshot
reads the landing moved (`rewrite_landing_moved`), and so do its answers to
a landed reset and to a park that keeps the attempt
(`rewrite_landing_retirement`).

`resolved` is the narrower question of whether evidence for the head was
already settled or retired -- current, or in the history -- which the
settlement step (`rewrite_finish_settlement`) asks before it lets any other
pending record beside that evidence go unanswered, whether it routes the head
or continues it.
"""
from __future__ import annotations

from orchestrator.git.base_sync import attempt_records as _attempt_records, state as _base_sync_state
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    rewrite_finish_failures as _failures,
    verification_record_state as _record_state,
    verification_settlement_state as _settlement,
)
from orchestrator.workflow.engine.verification_records import CurrentEvidence, PendingEvidence


def saw_land(state: PinnedState, head: str) -> bool:
    """Whether any evidence record on `state` names `head`, which only a finish that saw its push land writes."""
    if not head:
        return False
    pending = _record_state.read_pending_evidence(state)
    named = pending is not None and pending.binding.target.target_head == head
    named = named or _receipted(state, head)
    return named or resolved(state, head) or _failures.recorded(state, head) is not None


def resolved(state: PinnedState, head: str) -> bool:
    """Whether evidence for `head` was already settled or retired on `state`: current, or in the history."""
    settled = (_settlement.read_current_evidence(state), *(_settlement.read_evidence_history(state) or ()))
    heads = (record.binding.target.target_head for record in settled if record is not None)
    return head in heads


def capture_answered(state: PinnedState) -> bool:
    """Whether the transaction a finish of the attempt recorded was settled or retired since, history kept or not.

    Read off the receipt the finish put on the attempt (`records`), which
    outlives the evidence history: one naming no pending transaction -- the
    pending record another, unreadable, or gone -- is a capture this landing
    already answered, however many records another road wrote past it since.
    """
    receipt = state.get(_base_sync_state._PENDING_EVIDENCE_RECEIPT)
    if receipt is None:
        return False
    pending = _record_state.read_pending_evidence(state)
    return pending is None or pending.receipt != receipt


def records(staged: PinnedState, pending: PendingEvidence) -> bool:
    """Stage `pending` with the attempt's receipt of it, measured together; whether the comment took both.

    Staged in the finish's own evidence write (`rewrite_finish_writes.EVIDENCE`),
    so the transaction and the word that it is the finish's land together or
    not at all. A refusal leaves `staged` exactly as it was.
    """
    kept = dict(staged.data)
    staged.set(_base_sync_state._PENDING_EVIDENCE_RECEIPT, pending.receipt)
    if _record_state.record_pending_evidence(staged, pending):
        return True
    staged.data = kept
    return False


def captured(state: PinnedState) -> PendingEvidence | None:
    """The pending transaction a finish of the attempt recorded, which `state` still carries; or None."""
    pending = _record_state.read_pending_evidence(state)
    if pending is None:
        return None
    receipt = state.get(_base_sync_state._PENDING_EVIDENCE_RECEIPT)
    if receipt is None:
        owned = pending.binding.target.target_head == state.get(_base_sync_state._PENDING_ANNOUNCED_SHA)
    else:
        owned = receipt == pending.receipt
    return pending if owned else None


def settled(state: PinnedState) -> CurrentEvidence | None:
    """The current evidence a finish of the attempt settled for the head it landed, which `state` carries; or None.

    The finish's own transaction, settled under the receipt it put on the
    attempt, or current evidence about the head the attempt's record names as
    its replay or its mark names as announced: while the attempt stands the
    anchor keeps every other road off that head's evidence, so nothing but a
    finish of the attempt settles any for it -- a newer transaction it
    answered over its own included.
    """
    current = _settlement.read_current_evidence(state)
    if current is None:
        return None
    if current.receipt == state.get(_base_sync_state._PENDING_EVIDENCE_RECEIPT):
        return current
    head = current.binding.target.target_head
    announced = head == state.get(_base_sync_state._PENDING_ANNOUNCED_SHA)
    return current if announced or _attempt_records._pending_rewrite(state).names(head) else None


def _receipted(state: PinnedState, head: str) -> bool:
    """Whether the attempt carries a finish's receipt and its record names `head` as the replay that finish landed."""
    receipt = state.get(_base_sync_state._PENDING_EVIDENCE_RECEIPT)
    return receipt is not None and _attempt_records._pending_rewrite(state).names(head)
