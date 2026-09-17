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


def pending_from(recorded: dict) -> _records.PendingReport | None:
    """Return the transaction one recorded object is, or None for damage.

    The three groups are read apart and refused together, so a record missing
    its identity, its routing, or the half its own mode owns is one answer
    rather than three near-misses.
    """
    identity = _identity_of(recorded)
    routing = _routing_of(recorded)
    if identity is None or routing is None:
        return None
    carried = _carried_by_mode(recorded, routing[_MODE])
    if carried is None or not _bound_to_subject(identity, carried):
        return None
    return _records.PendingReport(**identity, **routing, **carried)


def delivered_from(recorded: dict) -> _records.DeliveredReport | None:
    """Return the delivered report one recorded object is, or None for damage.

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
        return None
    carried = _carried_by_mode(recorded, routing[_MODE])
    if carried is None:
        return None
    return _records.DeliveredReport(
        receipt=receipt,
        report_revision=revision,
        requirements_revision=requirements,
        **routing,
        **carried,
    )


def _bound_to_subject(identity: dict, carried: dict) -> bool:
    """Whether a verified location sits on the pull request this is about.

    A location is exact in both halves and still names a place anywhere in the
    repository: PR #13's description is a perfectly readable location holding
    somebody else's text. Unbound, a transaction recorded for PR #12 would
    reread it, find trusted content at the revision claimed, and record it as
    the report PR #12 now carries -- a handoff for a report that is not on the
    pull request at all.

    A publication carries no location and has nothing to bind; what says where
    it went is the comment the post returns.
    """
    location = carried.get("location")
    if location is None:
        return True
    return location.pr_number == identity["subject"].pr_number


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


def _carried_by_mode(recorded: dict, mode: _records.ReportMode) -> dict | None:
    """Return what one mode's transaction carries, or None when it carries none.

    The two modes carry opposite halves, and each half is required by exactly
    one of them: a publication with no text is a transaction that could publish
    nothing, and a verification with no location or no revision is one that
    could prove nothing. Read the other way round -- a text on a verification,
    a location on a publication -- the extra field is simply not consulted,
    since what would act on it is the mode.
    """
    if mode is _records.ReportMode.PUBLISH:
        report = _record_values.as_report_text(recorded.get(_REPORT))
        return None if report is None else {"report": report}
    location = _fields.location_from(recorded)
    digest = _payloads.as_hex(
        recorded.get(_CONTENT_DIGEST), _formats.DIGEST_LENGTHS,
    )
    if location is None or not digest:
        return None
    return {"location": location, "content_revision": digest}
