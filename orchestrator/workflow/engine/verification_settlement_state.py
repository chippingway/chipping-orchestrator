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

History is BOUNDED and kept in REVISION order, lowest out first. It is an
index of what this issue's pull request carried, not the evidence itself:
every artifact stays on the pull request, append-only, whatever the index
keeps. Unbounded, it would grow the pinned comment with every rewrite until a
write GitHub refuses stranded the issue. In revision order rather than the
order records retired, because the two differ -- a transaction abandoned before
the evidence it would have superseded retires ahead of it -- and an index of
artifacts is read by the revisions they carry. So the reader holds it to
exactly what the writer leaves: at most the entries kept, each revision once,
strictly rising. An eviction costs no revision: every later record is minted
past the revision floor each record raises (`verification_record_state`), so
what the index forgets is never a revision a later record can reuse.

A history the reader refuses is REPLACED by the next write that indexes a
retired record rather than preserved, since an index nobody can read indexes
nothing and the artifacts it pointed at are still on the thread; an unreadable
current record reads as no current evidence, which is what every consumer then
fails closed on.

Dormant, like the records it composes: nothing in production settles, retires,
or reads evidence yet (`verification_records`).
"""
from __future__ import annotations

import operator

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    report_record_state as _report_record_state,
    verification_history_fields as _history_fields,
    verification_record_fields as _record_fields,
    verification_records as _records,
    verification_settled_fields as _settled_fields,
)
from orchestrator.workflow.state import WorkflowLabel

# How many retired records the pinned index keeps.
_HISTORY_KEPT = 5

_BY_REVISION = operator.attrgetter("revision")


def read_current_evidence(state: PinnedState) -> _records.CurrentEvidence | None:
    """The evidence the pull request carries now, or None for none readable.

    None covers an issue with no evidence, evidence invalidated since, and a
    record nobody can read; none of them is evidence anybody may rely on.
    """
    return _settled_fields.current_from(state.get(_records.CURRENT_EVIDENCE))


def read_evidence_history(
    state: PinnedState,
) -> tuple[_records.HistoricalEvidence, ...] | None:
    """Every retired record in revision order; empty for none; None for damage.

    Damage is anything its writer never leaves: a present `null`, something
    other than a list, an entry that will not read, more entries than the
    index keeps, or revisions that do not strictly rise -- a repeat names one
    transaction twice, and an index out of order is one no retirement wrote.
    """
    if not state.carries(_records.EVIDENCE_HISTORY):
        return ()
    recorded = state.get(_records.EVIDENCE_HISTORY)
    if not isinstance(recorded, list) or len(recorded) > _HISTORY_KEPT:
        return None
    entries = tuple(_history_fields.historical_from(entry) for entry in recorded)
    if None in entries:
        return None
    revisions = [entry.revision for entry in entries]
    return entries if revisions == sorted(set(revisions)) else None


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
    """The comment settling `pending` leaves, composed on a copy of `state`, or None.

    The copy keeps `state`'s comment identity, so writing it rewrites the
    comment the transaction was recorded on.

    None unless `pending` is the transaction `state` records, read back whole:
    a transaction minted and never recorded raised no floor and holds no place
    on the comment, and settling it would drop whatever IS recorded while
    installing current evidence nothing recorded as owed. None too where
    either settled record would not read back as written -- a comment id past
    what this domain records -- so the caller installs nothing and the
    transaction stays owed rather than half-settled.
    """
    stored = state.get(_records.PENDING_EVIDENCE)
    if not isinstance(stored, dict) or _record_fields.pending_from(stored) != pending:
        return None
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
    if _settled_fields.current_from(_settled_fields.current_object(current)) != current:
        return None
    if _settled_fields.handoff_from(_settled_fields.handoff_object(handoff)) != handoff:
        return None
    # The copy is handed back to be written, so it keeps the comment it was
    # read from: written without one, it would land as a second state comment
    # beside the one still recording the transaction as owed.
    composed = PinnedState(
        comment_id=state.comment_id, state_data=dict(state.data), parsed=state.parsed,
    )
    superseded = read_current_evidence(composed)
    if superseded is not None:
        _appends_history(composed, _records.HistoricalEvidence.of(
            superseded, _records.Retirement.SUPERSEDED,
        ))
    composed.set(_records.CURRENT_EVIDENCE, _settled_fields.current_object(current))
    composed.set(_records.EVIDENCE_HANDOFF, _settled_fields.handoff_object(handoff))
    composed.set(_records.PENDING_EVIDENCE, None)
    return composed


def retire_current_evidence(state: PinnedState) -> bool:
    """Invalidate the current evidence into history, and say whether it moved.

    For a reader that has PROVED the world moved past it -- a head, a tree, a
    context, requirements, or a report. A record nobody can read is cleared
    without an entry, since there is nothing to index. False, with the state
    untouched, where there is none, or where the comment could not carry the
    result: the entry is larger than the record it replaces, and a retirement
    reported done that GitHub then refused would leave the record standing
    while its caller believed it gone. The recorder leaves room for this write
    (`verification_record_state.settled_payload`). The caller writes.
    """
    if state.get(_records.CURRENT_EVIDENCE) is None:
        return False
    composed = PinnedState(state_data=dict(state.data))
    current = read_current_evidence(composed)
    if current is not None:
        _appends_history(composed, _records.HistoricalEvidence.of(
            current, _records.Retirement.INVALIDATED,
        ))
    composed.set(_records.CURRENT_EVIDENCE, None)
    if not _report_record_state.fits_the_comment(composed.data):
        return False
    state.data = composed.data
    return True


def retire_pending_evidence(
    state: PinnedState, pending: _records.PendingEvidence | None,
) -> bool:
    """Drop the recorded transaction that will never settle, keeping it as abandoned history.

    Kept rather than forgotten because it may already have posted its
    artifact, and because its revision is one no later record may reuse.
    Only the transaction the comment records is retired: `pending` has to be
    the stored record read back whole, or None to drop a stored record nobody
    can read, which leaves no entry. Anything else -- a transaction minted and
    never recorded, whose revision no floor covers, or one a later record has
    replaced, whose retirement would drop the one that IS recorded -- and a
    result the comment could not carry leave the state untouched and answer
    False. The caller writes.
    """
    stored = state.get(_records.PENDING_EVIDENCE)
    if stored is None:
        return False
    standing = _record_fields.pending_from(stored) if isinstance(stored, dict) else None
    if standing != pending:
        return False
    composed = PinnedState(state_data=dict(state.data))
    if pending is not None:
        _appends_history(composed, _records.HistoricalEvidence.of(
            pending, _records.Retirement.ABANDONED,
        ))
    composed.set(_records.PENDING_EVIDENCE, None)
    if not _report_record_state.fits_the_comment(composed.data):
        return False
    state.data = composed.data
    return True


def _appends_history(state: PinnedState, entry: _records.HistoricalEvidence) -> None:
    """Index one more retired record, keeping the highest revisions in revision order."""
    indexed = (*(read_evidence_history(state) or ()), entry)
    kept = sorted(indexed, key=_BY_REVISION)[-_HISTORY_KEPT:]
    state.set(
        _records.EVIDENCE_HISTORY,
        [_history_fields.historical_object(record) for record in kept],
    )
