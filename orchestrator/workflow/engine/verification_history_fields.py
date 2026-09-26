# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pinned object one history entry is written as.

An entry says WHICH record it was and why it stopped being it: the receipt and
revision, the whole binding -- written by `verification_record_fields` exactly
as current evidence writes it, so the report revision and digest and the
complete review subject survive the retirement -- the evidence digest, whether
it passed, why it was retired, and the comment the artifact landed as. It
carries no commands, because the artifact stays on the pull request and the
entry is an index of it. The members it shares with current evidence are read
by `verification_settled_fields.record_members`, so the two records cannot come
to spell them differently.
"""
from __future__ import annotations

from typing import Any

from orchestrator.workflow.engine import (
    report_record_values as _record_values,
    verification_record_fields as _fields,
    verification_records as _records,
    verification_settled_fields as _settled_fields,
)
from orchestrator.workflow.late_split import payloads as _payloads

_RETIRED = "retired"


def historical_object(entry: _records.HistoricalEvidence) -> dict[str, Any]:
    """The pinned object one history entry is recorded as."""
    return {
        _settled_fields.RECEIPT: entry.receipt,
        _settled_fields.REVISION: entry.revision,
        **_fields.binding_fields(entry.binding),
        _settled_fields.CONTENT_DIGEST: entry.content_revision,
        _settled_fields.PASSED: entry.passed,
        _RETIRED: str(entry.retired),
        _settled_fields.COMMENT: entry.comment_id,
    }


def historical_from(recorded: object) -> _records.HistoricalEvidence | None:
    """The history entry one recorded object is, or None for damage.

    `comment` is the one member that may be `null`: an abandoned transaction
    confirmed no post. Absent, or present and not an identity, it is damage.
    """
    if not isinstance(recorded, dict):
        return None
    members = _settled_fields.record_members(recorded)
    binding = _fields.binding_from(recorded)
    retired = _payloads.as_member(_records.Retirement, recorded.get(_RETIRED))
    raw_comment = recorded.get(_settled_fields.COMMENT, False)
    if members is None or binding is None or retired is None:
        return None
    comment_id = None if raw_comment is None else _record_values.as_recorded_number(raw_comment)
    if raw_comment is not None and comment_id is None:
        return None
    return _records.HistoricalEvidence(
        **members, binding=binding, retired=retired, comment_id=comment_id,
    )
