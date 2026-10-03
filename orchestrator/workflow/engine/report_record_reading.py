# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one recorded object reads back as, or why it reads back as nothing.

The read half of both outstanding records -- the report a run delivered and the
transaction it is bound into -- apart from the writes that stage either. Every
member is read before any is judged, so the refusal is about the RECORD rather
than about whichever field happened to be looked at first -- and a record short
of any member is refused whole, because the members are proved together: a
transaction bound to a pull request nobody checked, on a branch nobody resolved,
over a commit nobody named is not a weaker transaction, it is one this build
cannot act on.

The two share every group but the subject, and the reader that hands a delivered
report back is the same three readings with that one left out: a report waiting
for a pull request names none, and the requirements revision it does name is the
one member of a subject the run itself settles.

The two pair groups are the one place where absent and unreadable have to stay
apart. A transaction that consumed no feedback and closes no reviewer round is
ordinary -- an initial publication is exactly that -- while a group that will
not read is damage. Read as the same answer, a hand-edited group would settle a
transaction having advanced no watermark and closed no round, and the next
re-entry would rerun a developer over feedback that was already answered.

Each record is read once, into either the record or the `RecordRefusal` saying
why there is none, and the optional readers are that one reading with the
reason dropped -- so a writer asking why a record it built was refused hears
the same verdict the reader acting on it would. The answer is the report's own
refusal only where every other member read: a content refusal says the text is
what to correct, and a record whose identity, routing, bookkeeping, or location
will not read is invalid whatever its report says.
"""
from __future__ import annotations

from orchestrator.workflow.engine import (
    report_consumed_values as _consumed,
    report_record_fields as _fields,
    report_record_values as _record_values,
    report_records as _records,
)
from orchestrator.workflow.late_split import (
    formats as _formats,
    payloads as _payloads,
    spends as _spends,
)
from orchestrator.workflow.state import WorkflowLabel

_RECEIPT = "receipt"

_REVISION = "revision"

_REQUIREMENTS = "requirements"

_MODE = "mode"

_ROUTE = "route"

_REPORT = "report"

_CONTENT_DIGEST = "content"

_WATERMARKS = "watermarks"

_SPENDS = "spends"

_LOCATION = "location"

_INVALID = _record_values.RecordRefusal.INVALID_RECORD


def pending_or_refusal(
    recorded: dict,
) -> _records.PendingReport | _record_values.RecordRefusal:
    """Return the transaction one recorded object is, or why it is none.

    The three groups are read apart and refused together, so a record missing
    its identity, its routing, or the half its own mode owns is one answer
    rather than three near-misses.
    """
    identity = _identity_of(recorded)
    routing = _routing_of(recorded)
    if identity is None or routing is None:
        return _INVALID
    carried = _carried_by_mode(recorded, routing[_MODE])
    if isinstance(carried, _record_values.RecordRefusal):
        return carried
    # A location is exact in both halves and still names a place anywhere in
    # the repository: PR #13's description is a perfectly readable location
    # holding somebody else's text. Unbound, a transaction recorded for PR #12
    # would reread it, find trusted content at the revision claimed, and record
    # it as the report PR #12 now carries. A publication carries no location;
    # what says where it went is the comment the post returns.
    location = carried.get(_LOCATION)
    if location is not None and location.pr_number != identity["subject"].pr_number:
        return _INVALID
    return _records.PendingReport(**identity, **routing, **carried)


def pending_from(recorded: dict) -> _records.PendingReport | None:
    """Return the transaction one recorded object is, or None for damage."""
    read = pending_or_refusal(recorded)
    return None if isinstance(read, _record_values.RecordRefusal) else read


def delivered_or_refusal(
    recorded: dict,
) -> _records.DeliveredReport | _record_values.RecordRefusal:
    """Return the delivered report one recorded object is, or why it is none.

    The same all-or-nothing reading the transaction gets, over the members a
    completed run settles: what the transaction will be called, which report
    revision it is, the requirements it answers, how and on which route it
    completes, and the mode's own half. A record short of any of them is one
    no publication could be bound from -- and read as an absence it would be a
    finished run's report dropped without a word on the tick that publishes
    its code.
    """
    receipt = _record_values.as_receipt(recorded.get(_RECEIPT))
    revision = _record_values.as_recorded_number(recorded.get(_REVISION))
    requirements = _payloads.as_hex(
        recorded.get(_REQUIREMENTS), _formats.DIGEST_LENGTHS,
    )
    routing = _routing_of(recorded)
    if not receipt or not revision or not requirements or routing is None:
        return _INVALID
    carried = _carried_by_mode(recorded, routing[_MODE])
    if isinstance(carried, _record_values.RecordRefusal):
        return carried
    return _records.DeliveredReport(
        receipt=receipt,
        report_revision=revision,
        requirements_revision=requirements,
        **routing,
        **carried,
    )


def delivered_from(recorded: dict) -> _records.DeliveredReport | None:
    """Return the delivered report one recorded object is, or None for damage."""
    read = delivered_or_refusal(recorded)
    return None if isinstance(read, _record_values.RecordRefusal) else read


def _identity_of(recorded: dict) -> dict | None:
    """Return what the transaction IS, or None unless the record says whole.

    The receipt is held to the spelling the published report header carries,
    because a retry finds its own comment by exactly that scope: a receipt
    readable here and uncarriable there names a comment no search could match,
    and the retry would post a second report believing the first never landed.
    """
    receipt = _record_values.as_receipt(recorded.get(_RECEIPT))
    subject = _fields.subject_from(recorded)
    revision = _record_values.as_recorded_number(recorded.get(_REVISION))
    if not receipt or subject is None or not revision:
        return None
    return {
        "receipt": receipt, "subject": subject, "report_revision": revision,
    }


def _routing_of(recorded: dict) -> dict | None:
    """Return how the transaction completes, or None unless the record says.

    The mode and the route are vocabulary members, so a spelling this build
    does not know reads back as nothing rather than as a road it might take.
    The two pair groups are bounded by the tables that own them, which is what
    keeps a recovered record from writing into any field the workflow has.
    """
    mode = _payloads.as_member(_records.ReportMode, recorded.get(_MODE))
    route = _payloads.as_member(WorkflowLabel, recorded.get(_ROUTE))
    watermarks = _consumed.recorded_pairs(
        recorded.get(_WATERMARKS), _consumed.consumable,
    )
    spends = _consumed.recorded_pairs(recorded.get(_SPENDS), _spends.spendable)
    if mode is None or route is None or watermarks is None or spends is None:
        return None
    return {
        _MODE: mode, _ROUTE: route,
        _WATERMARKS: watermarks, _SPENDS: spends,
    }


def _carried_by_mode(
    recorded: dict, mode: _records.ReportMode,
) -> dict | _record_values.RecordRefusal:
    """Return what one mode's transaction carries, or why it carries none.

    The two modes carry opposite halves, and each half is required by exactly
    one of them: a publication with no text is a transaction that could publish
    nothing, and a verification with no location or no revision is one that
    could prove nothing. Read the other way round -- a text on a verification,
    a location on a publication -- the extra field is simply not consulted,
    since what would act on it is the mode.

    A publication's refusal is its report's own, since the text is the one
    member a developer wrote and the one whose refusal it can correct.
    """
    if mode is _records.ReportMode.PUBLISH:
        report = recorded.get(_REPORT)
        refused = _record_values.report_text_refusal(report)
        return {_REPORT: report} if refused is None else refused
    location = _fields.location_from(recorded)
    digest = _payloads.as_hex(
        recorded.get(_CONTENT_DIGEST), _formats.DIGEST_LENGTHS,
    )
    if location is None or not digest:
        return _INVALID
    return {_LOCATION: location, "content_revision": digest}
