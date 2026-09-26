# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned objects current evidence and a handoff are written as.

Current evidence carries the whole binding, because it is what a later reader
proves against the world before relying on it and what a carry-forward is
decided from. A handoff carries only what says WHICH transaction finished --
the receipt, the pull request, the revision, and the head -- since the artifact
itself stays on the pull request and a second copy on the pinned comment would
only be a second thing to disagree with it. A history entry is written by
`verification_history_fields` over the same binding, and the members
`record_members` reads here for both.

Every reader here refuses what its own writer would not have produced, and
answers None for it. The state owner above decides what a refusal means for
each record, which differs: an unreadable current record is no current
evidence, and an unreadable handoff proves no transaction finished.

Dormant, like the records it spells (`verification_records`).
"""
from __future__ import annotations

from typing import Any

from orchestrator.workflow.engine import (
    report_record_values as _record_values,
    verification_record_fields as _fields,
    verification_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads
from orchestrator.workflow.state import WorkflowLabel

RECEIPT = "receipt"

REVISION = "revision"

CONTENT_DIGEST = "content"

COMMENT = "comment"

PASSED = "passed"

_HEAD = "head"

_PR = "pr"

_SETTLED_UNDER = "under"


def current_object(current: _records.CurrentEvidence) -> dict[str, Any]:
    """The pinned object current evidence is recorded as."""
    return {
        RECEIPT: current.receipt,
        REVISION: current.revision,
        **_fields.binding_fields(current.binding),
        CONTENT_DIGEST: current.content_revision,
        COMMENT: current.comment_id,
        PASSED: current.passed,
    }


def current_from(recorded: object) -> _records.CurrentEvidence | None:
    """The current evidence one recorded object is, or None for damage."""
    if not isinstance(recorded, dict):
        return None
    members = record_members(recorded)
    binding = _fields.binding_from(recorded)
    comment_id = _record_values.as_recorded_number(recorded.get(COMMENT))
    if members is None or binding is None or not comment_id:
        return None
    return _records.CurrentEvidence(**members, binding=binding, comment_id=comment_id)


def handoff_object(handoff: _records.EvidenceHandoff) -> dict[str, Any]:
    """The pinned object one handoff is recorded as.

    The settling label only where one was read: the member is optional and its
    reader holds an absence to "nobody could say".
    """
    recorded: dict[str, Any] = {
        RECEIPT: handoff.receipt,
        _PR: handoff.pr_number,
        REVISION: handoff.revision,
        _HEAD: handoff.target_head,
    }
    if handoff.settled_under is not None:
        recorded[_SETTLED_UNDER] = str(handoff.settled_under)
    return recorded


def handoff_from(recorded: object) -> _records.EvidenceHandoff | None:
    """The handoff one recorded object is, or None for damage."""
    if not isinstance(recorded, dict):
        return None
    receipt = _record_values.as_receipt(recorded.get(RECEIPT))
    pr_number = _record_values.as_recorded_number(recorded.get(_PR))
    revision = _record_values.as_recorded_number(recorded.get(REVISION))
    head = _payloads.as_hex(recorded.get(_HEAD), _formats.COMMIT_LENGTHS)
    under = _payloads.as_member(WorkflowLabel, recorded.get(_SETTLED_UNDER))
    if not (receipt and pr_number and revision and head):
        return None
    if not _records.PendingEvidence.receipt_names(receipt, revision):
        return None
    if under is None and _SETTLED_UNDER in recorded:
        return None
    return _records.EvidenceHandoff(
        receipt=receipt,
        pr_number=pr_number,
        revision=revision,
        target_head=head,
        settled_under=under,
    )


def record_members(recorded: dict) -> dict[str, Any] | None:
    """What every current and history record carries, read as their writers spell it.

    The receipt, the revision, the evidence digest, and the pass flag,
    returned as the keyword arguments those records are built from, or None
    where any of them is not what the writers spell -- a receipt naming
    another revision than the record's included.
    """
    receipt = _record_values.as_receipt(recorded.get(RECEIPT))
    revision = _record_values.as_recorded_number(recorded.get(REVISION))
    digest = _payloads.as_hex(recorded.get(CONTENT_DIGEST), _formats.DIGEST_LENGTHS)
    passed = recorded.get(PASSED)
    if not (receipt and revision and digest) or not isinstance(passed, bool):
        return None
    if not _records.PendingEvidence.receipt_names(receipt, revision):
        return None
    return {
        "receipt": receipt,
        "revision": revision,
        "content_revision": digest,
        "passed": passed,
    }
