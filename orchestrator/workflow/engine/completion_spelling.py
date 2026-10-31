# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a captured completion is spelled as on the pinned comment, and what one spelling reads back as.

One flat object per stage, every member spelled on every record of that stage:
the `stage`, the six members of the invocation it came from, and then the
stage's own. A PENDING capture adds the road and its frozen handoff, the
thread stretch it `delivered` (`[]` where its road settles none), what ran and
where, the conversation it `resumed`, the one it left `pinned`, and the session
it returned (each `null` where none), the outcome (`ready` with its `report`, or
`verified` with its `location_*` and `content`), its accounting, and the
handed-off capture it `supersedes` (`null` where none), spelled as that stage
is. A HANDED_OFF one adds the delivery's `receipt` and `revision` and
the `branch` and `source` the report is about; a RETIRED one, its `reason`
and the handed-off capture it still `supersedes` (`null` where none).

Read strictly and whole. Each member has its own reader (`completion_values`),
bounded by what the field is: a repository slug, a recorded number, a nonce of
the minted shape, a digest, a commit, a branch, one bounded line, a pair group
the report records' own vocabulary takes, a report the report records' own
reading takes. An object carrying a key its stage does not spell, or lacking
one, or any member that will not read, is no record at all -- and so is one
whose road's contract would have refused it -- answered None, which the state
reader (`completion_state`) tells apart from an absent field.
"""
from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from functools import partial
from operator import attrgetter
from types import MappingProxyType
from typing import Any

from orchestrator.agents.models import AgentInvocation
from orchestrator.workflow.engine import (
    completion_frozen as _frozen,
    completion_records as _records,
    completion_routes as _routes,
    completion_values as _bounds,
    invocations as _invocations,
    report_consumed_values as _consumed,
    report_outcome_models as _outcome_models,
    report_record_values as _record_values,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads, spends as _spends
from orchestrator.workflow.state import WorkflowLabel

_STAGE = "stage"
_OUTCOME = "outcome"
_READY = "ready"
_VERIFIED = "verified"
_REPORT = "report"
_BRANCH = "branch"
_SOURCE = "source"
_SESSION = "session"
_ACCOUNTING = "accounting"
_RECEIPT = "receipt"
_REVISION = "revision"
_REASON = "reason"
_ROUTE = "route"
_ORIGIN = "origin"
_FROZEN = "frozen"
_DELIVERED = "delivered"
_RESUMED = "resumed"
_PINNED = "pinned"
_SUPERSEDES = "supersedes"

# The members a PENDING capture's own reader reads apart from the rest, and a
# resolved one's by stage: a RETIRED capture's carried handoff among them.
_PENDING_APART = (_STAGE, _OUTCOME, _SUPERSEDES)

_RESOLVED_APART = MappingProxyType({_records.CaptureStage.RETIRED: (_STAGE, _SUPERSEDES)})
_LOCATION_SLUG = "location_slug"
_LOCATION_PR = "location_pr"
_LOCATION_COMMENT = "location_comment"
_CONTENT_DIGEST = "content"

_NONCE_DIGITS = 2 * _invocations.NONCE_BYTES
_NONCE_SHAPE = re.compile(f"[0-9a-f]{{{_NONCE_DIGITS}}}")

_RECORDED = _bounds.Member(_record_values.as_recorded_number)
_DIGEST = _bounds.Member(partial(_payloads.as_hex, lengths=_formats.DIGEST_LENGTHS))
_COMMIT = _bounds.Member(partial(_payloads.as_hex, lengths=_formats.COMMIT_LENGTHS))
_BRANCH_NAME = _bounds.Member(_record_values.as_branch)
_SESSION_ID = _bounds.Member(partial(_bounds.line, limit=_bounds.MAX_SESSION), optional=True)

# The invocation a record came from, spelled under the names its own fields carry.
_INVOCATION = MappingProxyType({
    "repo": _bounds.Member(_record_values.as_slug),
    "issue": _RECORDED,
    "comment": _RECORDED,
    "cycle": _bounds.Member(_bounds.count),
    "ordinal": _RECORDED,
    "nonce": _bounds.Member(partial(_bounds.shaped, shape=_NONCE_SHAPE)),
})

_PENDING = MappingProxyType({
    _ROUTE: _bounds.Member(partial(_payloads.as_member, _routes.CompletionRoute)),
    _ORIGIN: _bounds.Member(partial(_payloads.as_member, WorkflowLabel)),
    "requirements": _DIGEST,
    "watermarks": _bounds.Member(partial(_consumed.recorded_pairs, allowed=_consumed.consumable)),
    "spends": _bounds.Member(partial(_consumed.recorded_pairs, allowed=_spends.spendable)),
    _FROZEN: _bounds.Member(_bounds.frozen),
    _DELIVERED: _bounds.Member(_frozen.delivered_stretch),
    "command": _bounds.Member(partial(_bounds.line, limit=_bounds.MAX_COMMAND)),
    "prompt": _DIGEST,
    "worktree": _bounds.Member(partial(_bounds.line, limit=_bounds.MAX_WORKTREE)),
    _BRANCH: _BRANCH_NAME,
    "before": _COMMIT,
    _SOURCE: _COMMIT,
    _SESSION: _SESSION_ID,
    _RESUMED: _SESSION_ID,
    _PINNED: _SESSION_ID,
    _ACCOUNTING: _bounds.Member(partial(_payloads.as_member, _records.CaptureAccounting)),
})

# What each outcome adds: a READY report's text, or where a VERIFIED one was read and what it hashed to.
_OUTCOMES = MappingProxyType({
    _READY: MappingProxyType({_REPORT: _bounds.Member(_bounds.report)}),
    _VERIFIED: MappingProxyType({
        _LOCATION_SLUG: _bounds.Member(_record_values.as_slug),
        _LOCATION_PR: _RECORDED,
        _LOCATION_COMMENT: _bounds.Member(_record_values.as_recorded_number, optional=True),
        _CONTENT_DIGEST: _DIGEST,
    }),
})

# Which attribute of its record each wire key is.
_INVOCATION_ATTRIBUTES = MappingProxyType({key: key for key in _INVOCATION})

_HANDOFF_ATTRIBUTES = MappingProxyType({
    _ROUTE: _ROUTE, _ORIGIN: _ORIGIN, "requirements": "requirements_revision",
    "watermarks": "watermarks", "spends": "spends", _FROZEN: _FROZEN, _DELIVERED: _DELIVERED,
})

_RUN_ATTRIBUTES = MappingProxyType({
    "command": "command", "prompt": "prompt_revision", "worktree": "worktree",
    _BRANCH: _BRANCH, "before": "before_sha", _SOURCE: "source_sha", _RESUMED: _RESUMED, _PINNED: _PINNED,
})

_RESOLVED_ATTRIBUTES = MappingProxyType({
    _records.CaptureStage.HANDED_OFF: MappingProxyType({
        _RECEIPT: _RECEIPT, _REVISION: "report_revision", _BRANCH: _BRANCH, _SOURCE: "source_sha",
    }),
    _records.CaptureStage.RETIRED: MappingProxyType({_REASON: _REASON}),
})

_OUTCOME_ATTRIBUTES = MappingProxyType({
    _READY: MappingProxyType({_REPORT: _REPORT}),
    _VERIFIED: MappingProxyType({
        _LOCATION_SLUG: "location.slug",
        _LOCATION_PR: "location.pull_number",
        _LOCATION_COMMENT: "location.comment_id",
        _CONTENT_DIGEST: "revision",
    }),
})

# What a PENDING capture of each outcome spells beside its invocation.
_PENDING_OUTCOMES = MappingProxyType({
    kind: MappingProxyType({**_PENDING, **readers})
    for kind, readers in _OUTCOMES.items()
})

# What each resolved stage adds.
_RESOLVED = MappingProxyType({
    _records.CaptureStage.HANDED_OFF: MappingProxyType({
        _RECEIPT: _bounds.Member(_record_values.as_receipt),
        _REVISION: _RECORDED,
        _BRANCH: _BRANCH_NAME,
        _SOURCE: _COMMIT,
    }),
    _records.CaptureStage.RETIRED: MappingProxyType({
        _REASON: _bounds.Member(partial(_payloads.as_member, _records.RetirementReason)),
    }),
})


def spelled(record: _records.CompletionCapture | _records.ResolvedCapture) -> dict[str, Any]:
    """The pinned object one capture is written as, in the JSON types a reading parses it back into."""
    parts = [(record.invocation, _INVOCATION_ATTRIBUTES)]
    if isinstance(record, _records.ResolvedCapture):
        parts.append((record, _RESOLVED_ATTRIBUTES[record.stage]))
        spelling = {_STAGE: record.stage}
    else:
        kind = _READY if isinstance(record.outcome, _outcome_models._ReadyReport) else _VERIFIED
        parts.extend((
            (record.handoff, _HANDOFF_ATTRIBUTES),
            (record.run, _RUN_ATTRIBUTES),
            (record.outcome, _OUTCOME_ATTRIBUTES[kind]),
        ))
        spelling = {_STAGE: record.stage, _OUTCOME: kind, _SESSION: record.session_id, _ACCOUNTING: record.accounting}
    if record.stage is not _records.CaptureStage.HANDED_OFF:
        spelling[_SUPERSEDES] = None if record.supersedes is None else spelled(record.supersedes)
    for part, attributes in parts:
        spelling.update(_attributes(part, attributes))
    return json.loads(json.dumps(spelling))


def read_record(
    raw: Any, *, handed_off: bool = False,
) -> _records.CompletionCapture | _records.ResolvedCapture | None:
    """The capture one pinned object is, or None where it is no capture this build writes.

    `handed_off` reads only a HANDED_OFF capture, as a pending or retired
    one's `supersedes` holds: any other stage is None too, and so is a
    `supersedes` that is not `null` and no such capture.
    """
    if not isinstance(raw, dict):
        return None
    stage = _payloads.as_member(_records.CaptureStage, raw.get(_STAGE))
    carried = read_record(raw.get(_SUPERSEDES), handed_off=True)
    damaged = carried is None and raw.get(_SUPERSEDES) is not None
    if damaged or (handed_off and stage is not _records.CaptureStage.HANDED_OFF):
        return None
    if stage is _records.CaptureStage.PENDING:
        return _pending(raw, carried)
    apart = _RESOLVED_APART.get(stage, (_STAGE,))
    members = _members(raw, _RESOLVED.get(stage), apart)
    return None if members is None else _built(
        _records.ResolvedCapture, members, _RESOLVED_ATTRIBUTES[stage], stage=stage,
        invocation=_built(AgentInvocation, members, _INVOCATION_ATTRIBUTES), supersedes=carried,
    )


def _pending(raw: dict, handoff: _records.ResolvedCapture | None) -> _records.CompletionCapture | None:
    """The PENDING capture one object is, held to its road's contract, or None; `handoff` is what it supersedes."""
    outcome = raw.get(_OUTCOME)
    added = _PENDING_OUTCOMES.get(outcome) if isinstance(outcome, str) else None
    members = _members(raw, added, _PENDING_APART)
    if members is None:
        return None
    refused = _routes.refused_by_contract(
        members[_ROUTE],
        members[_ORIGIN],
        verified=outcome == _VERIFIED,
        handed=bool(members[_FROZEN]),
    )
    contract = _routes.CONTRACTS[members[_ROUTE]]
    if refused is not None or not contract.holds(members[_DELIVERED]):
        return None
    return _records.CompletionCapture(
        invocation=_built(AgentInvocation, members, _INVOCATION_ATTRIBUTES),
        handoff=_built(_records.CompletionHandoff, members, _HANDOFF_ATTRIBUTES),
        run=_built(_records.CompletionRun, members, _RUN_ATTRIBUTES),
        outcome=_outcome_of(members),
        accounting=members[_ACCOUNTING],
        session_id=members[_SESSION],
        supersedes=handoff,
    )


def _members(
    raw: dict,
    added: Mapping[str, _bounds.Member] | None,
    spelled_apart: Iterable[str],
) -> dict | None:
    """The invocation's members and every one `added` names, each read by its own reader, or None.

    None where the stage spells no such members, and where the object
    carries a key besides those and `spelled_apart` -- the ones the caller
    read for itself -- lacks one, or carries one that will not read.
    """
    if added is None:
        return None
    readers = {**_INVOCATION, **added}
    if set(raw) != {*readers, *spelled_apart}:
        return None
    members = {
        key: member.read(raw[key])
        for key, member in readers.items()
    }
    if any(member is _bounds.DAMAGED for member in members.values()):
        return None
    return members


def _built(record_type: type, members: dict, attributes: Mapping[str, str], **given: Any) -> Any:
    """One record of `record_type`, each attribute the member its wire key read as."""
    named = {
        attribute: members[key]
        for key, attribute in attributes.items()
    }
    return record_type(**named, **given)


def _attributes(part: Any, attributes: Mapping[str, str]) -> dict[str, Any]:
    """What `part` holds under each wire key, read off the attribute it names."""
    return {
        key: attrgetter(attribute)(part)
        for key, attribute in attributes.items()
    }


def _outcome_of(members: dict) -> _routes.CapturedOutcome:
    """The report outcome the members of a PENDING capture spell."""
    report = members.get(_REPORT)
    if report is not None:
        return _outcome_models._ReadyReport(report)
    return _outcome_models._VerifiedReport(
        _outcome_models._ReportLocation(
            slug=members[_LOCATION_SLUG],
            pull_number=members[_LOCATION_PR],
            comment_id=members[_LOCATION_COMMENT],
        ),
        members[_CONTENT_DIGEST],
    )
