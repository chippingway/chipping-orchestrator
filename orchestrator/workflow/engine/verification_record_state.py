# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pending evidence transaction's round trip through the pinned comment.

The record goes down BEFORE its artifact is posted, which is what makes the
publication recoverable: a process that dies after this write comes back to a
transaction naming everything it was doing, and one that dies before it comes
back to an issue that simply has no evidence yet. Whoever produced the run
owns that write; this owner owns what the record may be.

A revision moves past every record this issue has kept -- the transaction
outstanding, the current evidence, the handoff, and the history -- so a later
artifact on one pull request is always a later revision. The receipt is spelled
from the revision AND a fresh nonce. A revision alone is not unique once a
record nobody can read has been dropped, and a transaction sharing a receipt
with one whose artifact already landed would find that comment, read it as its
own publication edited beyond recognition, and stand down for good.

Recording a transaction over a readable one abandons the earlier into history
in the same write: it may have posted an artifact already, and its revision is
one no later record may reuse. Recording over one nobody can read drops it;
evidence nobody can read is evidence nobody has, and what replaces it is newer.

The comment has to have room for the record AND for the write that settles it,
measured over the whole settling write rather than allowed for by a margin, so
a transaction is never accepted into a comment its own settlement would push
past what GitHub accepts. That settlement happens after the artifact is posted,
where a refused write would leave the evidence on the thread and the
transaction claiming it forever. The measurement is offered to the publication
as well, which takes it again on the tick it would settle: the routes behind
the reconciliation can spend the room a record was accepted with.
"""
from __future__ import annotations

import uuid

from orchestrator.github import verification_artifacts as _artifacts, verification_evidence as _evidence
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    report_record_state as _report_record_state,
    report_record_values as _record_values,
    verification_record_fields as _fields,
    verification_records as _records,
    verification_settlement_state as _settlement,
)

_RECEIPT = "issue-{issue}-verification-{revision}-{nonce}"


def carries_pending_evidence(state: PinnedState) -> bool:
    """Whether this issue CLAIMS a transaction, whatever the record holds.

    `null` is the resting state a settlement leaves, so only a payload that is
    there is a claim.
    """
    return state.get(_records.PENDING_EVIDENCE) is not None


def read_pending_evidence(state: PinnedState) -> _records.PendingEvidence | None:
    """The transaction this issue has outstanding, or None for none readable."""
    recorded = state.get(_records.PENDING_EVIDENCE)
    if not isinstance(recorded, dict):
        return None
    return _fields.pending_from(recorded)


def mint_pending_evidence(
    state: PinnedState,
    issue_number: int,
    binding: _records.EvidenceBinding,
    commands: tuple[_evidence.VerifiedCommand, ...],
) -> _records.PendingEvidence:
    """A new transaction for `binding` and `commands`, past every earlier revision."""
    revision = 1 + _latest_revision(state)
    return _records.PendingEvidence(
        receipt=_RECEIPT.format(
            issue=issue_number, revision=revision, nonce=uuid.uuid4().hex,
        ),
        revision=revision,
        binding=binding,
        commands=commands,
    )


def record_pending_evidence(
    state: PinnedState, pending: _records.PendingEvidence,
) -> bool:
    """Stage one transaction onto the pinned state, or refuse to.

    False, with the state untouched, when this owner's own reader would not
    hand the record back identically -- a record that reads back as damage on
    the next tick is no record -- when its artifact would be refused, or when
    the comment could not carry the record or the write that settles it. The
    caller owns `gh.write_pinned_state`.
    """
    recorded = _fields.pending_object(pending)
    if _fields.pending_from(recorded) != pending or not _publishable(pending):
        return False
    composed = PinnedState(state_data=dict(state.data))
    standing = read_pending_evidence(composed)
    if standing is None or standing.receipt != pending.receipt:
        _settlement.retire_pending_evidence(composed, standing)
    composed.set(_records.PENDING_EVIDENCE, recorded)
    settled = settled_payload(composed, pending)
    if settled is None or not _report_record_state.fits_the_comment(composed.data):
        return False
    if not _report_record_state.fits_the_comment(settled):
        return False
    state.data = composed.data
    return True


def settled_payload(
    state: PinnedState, pending: _records.PendingEvidence,
) -> dict | None:
    """The payload settling this transaction would leave, at its widest, or None.

    Widest at what a settlement cannot know yet: the comment id the post will
    answer with, and the label the issue will carry when the write lands. The
    comment-id ledger entry the publication records is reserved too, through
    the ledger's own owner. None where the settlement would refuse its own
    records.
    """
    widest = _record_values.MAX_RECORDED_NUMBER
    composed = PinnedState(state_data=dict(state.data))
    _comments._reserve_comment_slot(composed, widest)
    settled = _settlement.settled_state(
        composed, pending, widest, _report_record_state._WIDEST_LABEL,
    )
    return None if settled is None else settled.data


def _publishable(pending: _records.PendingEvidence) -> bool:
    """Whether the artifact this transaction publishes is one the format accepts.

    Asked where the record is accepted rather than where it is published: by
    then the world has been proved and the tick spent, and a refusal there
    would hold every later tick over a record this owner let through.
    """
    try:
        return bool(_artifacts.render_verification_artifact(pending.artifact))
    except _evidence.ArtifactRefusedError:
        return False


def _latest_revision(state: PinnedState) -> int:
    """The highest revision any readable record of this issue carries, or 0."""
    kept = (
        read_pending_evidence(state),
        _settlement.read_current_evidence(state),
        _settlement.read_evidence_handoff(state),
        *(_settlement.read_evidence_history(state) or ()),
    )
    return max((record.revision for record in kept if record is not None), default=0)
