# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Current evidence, its history, and the handoff: read, settled, and retired.

A settlement is ONE composed write, as a developer report's is: the evidence
that was current goes into history as superseded, the settled transaction
becomes current, the handoff names its receipt, and the pending record is
dropped -- all on a copy of the comment, installed by the caller only once
every member reads back. Split across writes, a crash between two of them
leaves an artifact on the pull request and a transaction still claiming it is
owed, or current evidence that nothing records as ever having been published.

Nothing here RELABELS evidence. A record retired from pending or current keeps
its whole binding -- the commit and tree it was about, the head it answered
for, and the report and review subject it answered to -- and goes into history
saying why it stopped being what it was; the next current record is a
settlement of its own. So a run is never presented as one on a commit it did
not run on, and an invalidation says so rather than leaving stale evidence
standing as current.

History is BOUNDED, oldest out first. It is an index of what this issue's pull
request carried, not the evidence itself: every artifact stays on the pull
request, append-only, whatever the index keeps. Unbounded, it would grow the
pinned comment with every rewrite until a write GitHub refuses stranded the
issue. Oldest out is also what keeps revisions monotonic: every later record
is minted past every earlier one, so what an eviction drops is never the
highest revision this issue has used.

A history the reader refuses is REPLACED by the next write rather than
preserved, since an index nobody can read indexes nothing and the artifacts it
pointed at are still on the thread; an unreadable current record reads as no
current evidence, which is what every consumer then fails closed on.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    verification_history_fields as _history_fields,
    verification_records as _records,
    verification_settled_fields as _settled_fields,
)
from orchestrator.workflow.state import WorkflowLabel

# How many retired records the pinned index keeps.
_HISTORY_KEPT = 5


def read_current_evidence(state: PinnedState) -> _records.CurrentEvidence | None:
    """The evidence the pull request carries now, or None for none readable.

    None covers an issue with no evidence, evidence invalidated since, and a
    record nobody can read; none of them is evidence anybody may rely on.
    """
    return _settled_fields.current_from(state.get(_records.CURRENT_EVIDENCE))


def read_evidence_history(
    state: PinnedState,
) -> tuple[_records.HistoricalEvidence, ...] | None:
    """Every retired record, oldest first; empty for none; None for damage."""
    recorded = state.get(_records.EVIDENCE_HISTORY)
    if recorded is None:
        return ()
    if not isinstance(recorded, list):
        return None
    entries = tuple(_history_fields.historical_from(entry) for entry in recorded)
    return None if None in entries else entries


def read_evidence_handoff(state: PinnedState) -> _records.EvidenceHandoff | None:
    """The receipt of the last finished transaction, or None for none readable.

    A handoff nobody can read proves nothing finished, and what a caller does
    with that is repeat the work -- which the receipt-scoped publication turns
    into finding the artifact already there.
    """
    return _settled_fields.handoff_from(state.get(_records.EVIDENCE_HANDOFF))


def settled_state(
    state: PinnedState,
    pending: _records.PendingEvidence,
    comment_id: int,
    settled_under: WorkflowLabel | None,
) -> PinnedState | None:
    """The comment settling `pending` leaves, composed on a copy, or None.

    None where either settled record would not read back as written -- a
    comment id past what this domain records -- so the caller installs nothing
    and the transaction stays owed rather than half-settled.
    """
    current = _records.CurrentEvidence(
        receipt=pending.receipt,
        revision=pending.revision,
        binding=pending.binding,
        content_revision=pending.content_revision,
        comment_id=comment_id,
        passed=pending.passed,
    )
    handoff = _records.EvidenceHandoff(
        receipt=pending.receipt,
        pr_number=pending.binding.target.publication.pr_number,
        revision=pending.revision,
        target_head=pending.binding.target.target_head,
        settled_under=settled_under,
    )
    current_recorded = _settled_fields.current_object(current)
    handoff_recorded = _settled_fields.handoff_object(handoff)
    if _settled_fields.current_from(current_recorded) != current:
        return None
    if _settled_fields.handoff_from(handoff_recorded) != handoff:
        return None
    composed = PinnedState(state_data=dict(state.data))
    retire_current_evidence(composed, _records.Retirement.SUPERSEDED)
    composed.set(_records.CURRENT_EVIDENCE, current_recorded)
    composed.set(_records.EVIDENCE_HANDOFF, handoff_recorded)
    composed.set(_records.PENDING_EVIDENCE, None)
    return composed


def retire_current_evidence(
    state: PinnedState,
    because: _records.Retirement = _records.Retirement.INVALIDATED,
) -> bool:
    """Move the current evidence into history, and say whether there was any.

    For a reader that has PROVED the world moved past it -- a head, a tree, a
    context, requirements, or a report -- and for the settlement that replaces
    it. A record nobody can read is cleared without an entry, since there is
    nothing to index. The caller writes.
    """
    if state.get(_records.CURRENT_EVIDENCE) is None:
        return False
    current = read_current_evidence(state)
    if current is not None:
        _appends_history(state, _records.HistoricalEvidence.of(current, because))
    state.set(_records.CURRENT_EVIDENCE, None)
    return True


def retire_pending_evidence(
    state: PinnedState, pending: _records.PendingEvidence | None,
) -> None:
    """Drop a transaction that will never settle, keeping it as abandoned history.

    Kept rather than forgotten because it may already have posted its
    artifact, and because its revision is one no later record may reuse. A
    record nobody can read (`pending` None) is dropped without an entry. The
    caller writes.
    """
    if pending is not None:
        _appends_history(state, _records.HistoricalEvidence.of(
            pending, _records.Retirement.ABANDONED,
        ))
    state.set(_records.PENDING_EVIDENCE, None)


def _appends_history(state: PinnedState, entry: _records.HistoricalEvidence) -> None:
    """Append one entry to the bounded history, oldest out first."""
    kept = (*(read_evidence_history(state) or ()), entry)[-_HISTORY_KEPT:]
    state.set(
        _records.EVIDENCE_HISTORY,
        [_history_fields.historical_object(record) for record in kept],
    )
