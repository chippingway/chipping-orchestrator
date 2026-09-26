# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pending evidence transaction's round trip through the pinned comment.

The record goes down BEFORE its artifact is posted, which is what makes the
publication recoverable: a process that dies after this write comes back to a
transaction naming everything it was doing, and one that dies before it comes
back to an issue that simply has no evidence yet. Whoever produced the run
owns that write; this owner owns what the record may be.

A revision moves past every one this issue has spent, so a later artifact on
one pull request is always a later revision. What has been spent is read off
the revision floor every record raises in its own write, and off every
readable record beside it: a record can be damaged, dropped, or evicted from
the bounded history after its artifact landed, and the floor outlives it.
Where nobody can say what was spent -- a comment that did not parse, the floor
present and unreadable, or the floor missing beside any record -- nothing is
minted or recorded, since a transaction there could put a second artifact at a
revision one already carries. Recording holds a transaction to the floor rather than trusting
whoever minted it, so one minted before another settled is refused.

The receipt is spelled from the revision AND a fresh nonce, and a pending
record whose receipt does not spell its own revision reads as damage. A
transaction sharing a receipt with one whose artifact already landed would
find that comment, read it as its own publication edited beyond recognition,
and stand down for good; bound to a revision past the floor, no receipt can
come back once the history has forgotten the transaction that used it.

Recording a transaction over a readable one abandons the earlier into history
in the same write: it may have posted an artifact already, and its revision is
one no later record may reuse. Recording over one nobody can read drops it;
evidence nobody can read is evidence nobody has, and what replaces it is newer.
Recording the SAME transaction again is a retry, accepted only where it is
identical: its artifact may already be on the thread under that receipt, and a
record carrying anything else would no longer describe that post.

The comment has to have room for the record AND for the write that settles it,
measured over the whole settling write rather than allowed for by a margin, so
a transaction is never accepted into a comment its own settlement would push
past what GitHub accepts. That settlement happens after the artifact is posted,
where a refused write would leave the evidence on the thread and the
transaction claiming it forever. The measurement is public (`settled_payload`)
so a publication can take it again on the tick it would settle, since writes
landing between the two ticks can spend the room a record was accepted with.

Dormant, like the records it writes: nothing in production mints or records a
transaction yet (`verification_records`).
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

# Every record whose presence says this issue has recorded a transaction.
_RECORDS = (
    _records.PENDING_EVIDENCE,
    _records.CURRENT_EVIDENCE,
    _records.EVIDENCE_HISTORY,
    _records.EVIDENCE_HANDOFF,
)


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
) -> _records.PendingEvidence | None:
    """A new transaction for `binding` and `commands`, past every spent revision.

    None where nobody can say which revisions this issue has spent.
    """
    latest = _latest_revision(state)
    if latest is None:
        return None
    revision = latest + 1
    return _records.PendingEvidence(
        receipt=_records.RECEIPT.format(
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

    True, with the state untouched, for an identical retry of the transaction
    already recorded. False, with the state untouched, wherever nobody can say
    which revisions this issue has spent -- a retry included, since what it
    would stand on is then no more provable than a new record -- for anything
    else under the recorded receipt, for a transaction `_acceptable` refuses,
    or when the comment could not carry the record or the write that settles
    it. The caller owns `gh.write_pinned_state`.
    """
    standing = read_pending_evidence(state)
    if standing is not None and standing.receipt == pending.receipt:
        return standing == pending and _latest_revision(state) is not None
    if not _acceptable(state, pending):
        return False
    composed = PinnedState(state_data=dict(state.data))
    # A readable earlier record has to go into history; nothing stored, or one
    # nobody can read, is simply replaced.
    retired = _settlement.retire_pending_evidence(composed, standing) or standing is None
    composed.set(_records.PENDING_EVIDENCE, _fields.pending_object(pending))
    composed.set(_records.REVISION_FLOOR, pending.revision)
    settled = settled_payload(composed, pending)
    written = (composed.data, settled) if retired and settled is not None else ()
    if not written or not all(map(_report_record_state.fits_the_comment, written)):
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
    records, or where the evidence it installs could not later be invalidated
    within the comment: that entry is larger than the record it replaces, so
    a comment the settlement filled would strand the evidence as current.
    """
    widest = _record_values.MAX_RECORDED_NUMBER
    composed = PinnedState(state_data=dict(state.data))
    _comments._reserve_comment_slot(composed, widest)
    settled = _settlement.settled_state(
        composed, pending, widest, _report_record_state._WIDEST_LABEL,
    )
    if settled is None:
        return None
    invalidated = PinnedState(state_data=dict(settled.data))
    return settled.data if _settlement.retire_current_evidence(invalidated) else None


def _acceptable(state: PinnedState, pending: _records.PendingEvidence) -> bool:
    """Whether `pending` may be recorded as a new transaction on `state`.

    Past every revision this issue has spent, since a transaction minted
    before another settled shares that one's and would publish a second
    artifact under it -- and refused where nobody can say what was spent.
    Read back identically by this owner's own reader, which also holds the
    receipt to the revision, since a record that reads back as damage on the
    next tick is no record. And publishing an artifact the format accepts --
    asked where the record is accepted rather than where it is published,
    because by then the world has been proved and the tick spent, and a
    refusal there would hold every later tick over a record this owner let
    through.
    """
    latest = _latest_revision(state)
    if latest is None or pending.revision <= latest:
        return False
    if _fields.pending_from(_fields.pending_object(pending)) != pending:
        return False
    try:
        return bool(_artifacts.render_verification_artifact(pending.artifact))
    except _evidence.ArtifactRefusedError:
        return False


def _latest_revision(state: PinnedState) -> int | None:
    """The highest revision this issue has spent, or None where nobody can say.

    The recorded floor, raised to any readable record's revision. None over a
    comment that did not parse, whose empty stand-in is indistinguishable from
    an issue that never recorded anything; where the floor is present and
    unreadable, `null` included, since no write spells it so; and where it is
    missing beside any record, `null` ones included, since a settled or
    invalidated record spent a revision too: a record nobody can read may have
    spent one above everything readable, and only the floor its own write
    raised says so. An issue carrying none of these keys has spent nothing.
    """
    recorded = state.carries(_records.REVISION_FLOOR)
    claimed = any(state.carries(key) for key in _RECORDS)
    if not state.parsed or (claimed and not recorded):
        return None
    floor = _record_values.as_recorded_number(state.get(_records.REVISION_FLOOR)) if recorded else 0
    if floor is None:
        return None
    kept = (
        read_pending_evidence(state),
        _settlement.read_current_evidence(state),
        _settlement.read_evidence_handoff(state),
        *(_settlement.read_evidence_history(state) or ()),
    )
    return max((floor, *(record.revision for record in kept if record is not None)))
