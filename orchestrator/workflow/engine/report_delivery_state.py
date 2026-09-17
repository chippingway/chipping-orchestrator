# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The delivered report's round trip, and the transaction it is bound into.

A run writes its report and ends with the tick that ran it. The code that report
is about has still to pass the size gate and reach a remote, and only then does
a pull request exist for the report to go onto -- so between the run and the
publication there is a window in which the whole of what was produced lives
nowhere but in memory. A process that dies there loses a finished run's report,
and nothing can get it back: the session is gone, and a second run writes a
second report rather than the one this one wrote.

So the report is recorded FIRST, before the gate and before the push, holding
everything the run settled and nothing the publication decides. What a pull
request would add -- which repository, which number, which branch, which commit
-- is unknowable here and is proved by whoever binds it. What the run settled
and nobody else can supply is the text, the revision it is, the route that
produced it, the receipt a retry would find its own comment by, and the
requirements revision the run was actually handed.

Binding is one write and it REPLACES: the delivered record is dropped in the
same write that records the transaction, because two records claiming one
report are two reports the next tick would try to publish. A binding the
transaction's own writer refuses leaves the caller's state untouched, so the
caller can drop the delivery rather than carrying a report nothing will ever
accept.

The record is additive and is claimed exactly as the transaction beside it is: a
key holding `null` is the resting state a binding leaves, and a payload that is
there and is not an object is the claim a hand edit or a truncated write makes.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_record_fields as _fields,
    report_record_reading as _reading,
    report_record_state as _record_state,
    report_records as _records,
)

_RECEIPT = "receipt"

_REVISION = "revision"

_REQUIREMENTS = "requirements"


def carries_delivered_report(state: _pinned_state.PinnedState) -> bool:
    """Whether this issue CLAIMS a report it has not bound, whatever it holds.

    Presence rather than meaning, for the reason the transaction is asked that
    way: the reader below answers None both for an issue that delivered
    nothing and for a record nobody can act on, and a caller deciding whether
    a report is still owed may not confuse the two. An issue whose record a
    hand edit truncated owes a report nobody can describe, and waved through
    as an absence it would be handed to a reviewer without one.

    `null` is an absence, because that is what binding a delivery leaves: the
    drop writes the key rather than removing it.
    """
    if not state.carries(_records.DELIVERED_REPORT):
        return False
    return state.get(_records.DELIVERED_REPORT) is not None


def read_delivered_report(
    state: _pinned_state.PinnedState,
) -> _records.DeliveredReport | None:
    """Return the report this issue has delivered and not bound, or None.

    None covers both an issue that recorded nothing and a record this build
    cannot act on. `carries_delivered_report` beside this is what tells them
    apart.
    """
    recorded = state.get(_records.DELIVERED_REPORT)
    if not isinstance(recorded, dict):
        return None
    return _reading.delivered_from(recorded)


def record_delivered_report(
    state: _pinned_state.PinnedState, delivered: _records.DeliveredReport,
) -> bool:
    """Stage one completed run's report onto the pinned state, or refuse to.

    False when this owner's own READER would not hand the record back
    identically, or when the comment could not carry it. Nothing is written on
    a refusal, so the caller's state is exactly as it was found and the caller
    hears it while the run that wrote the report is still there to be told --
    which is the only moment anything can still be done about a report too
    large to record or one quoting a receipt marker of this orchestrator's.

    The measurement is over this write alone. What a transaction bound from
    this record will additionally cost -- the code-publication receipt it waits
    for and the settlement that ends it -- is measured where that transaction
    is accepted, over a comment this record has already been dropped from.

    The caller still owns `gh.write_pinned_state`, as every stage-facing writer
    here does, so the record rides whatever else that caller staged.
    """
    recorded = _encoded(delivered)
    if recorded is None or _reading.delivered_from(recorded) != delivered:
        return False
    staged = {**state.data, _records.DELIVERED_REPORT: recorded}
    if not _record_state.fits_the_comment(staged):
        return False
    state.set(_records.DELIVERED_REPORT, recorded)
    return True


def clear_delivered_report(state: _pinned_state.PinnedState) -> None:
    """Drop the delivered report, bound or abandoned.

    Written as an absence rather than removed, which is what every other
    cleared group here does: the key stays on the comment holding `null`, and
    both readers above answer for that exactly as they answer for an issue
    that never delivered one.
    """
    state.set(_records.DELIVERED_REPORT, None)


def binds_delivered_report(
    state: _pinned_state.PinnedState,
    delivered: _records.DeliveredReport,
    subject: _records.ReportSubject,
) -> bool:
    """Stage the transaction this delivered report becomes, or refuse to.

    The subject is everything the publication settles and the run could not:
    the repository, the pull request the code landed on, the branch it went
    out under, and the commit it is standing on. Bound to them, the report a
    run wrote becomes a transaction a later tick can prove again from the
    record alone.

    ONE staged write, because the two records claim the same report: a drop
    without the transaction beside it loses a finished run's work, and a
    transaction beside the delivery it came from is a second report the next
    tick would publish. Built on a copy, a refusal leaves the caller's state
    exactly as it was found -- and a refusal is a transaction nothing can
    accept, so what the caller owes then is the drop rather than a retry.
    """
    bound = _pinned_state.PinnedState(state_data=dict(state.data))
    clear_delivered_report(bound)
    if not _record_state.record_pending_report(
        bound, _records.PendingReport(
            receipt=delivered.receipt,
            subject=subject,
            report_revision=delivered.report_revision,
            mode=delivered.mode,
            route=delivered.route,
            report=delivered.report,
            location=delivered.location,
            content_revision=delivered.content_revision,
            watermarks=delivered.watermarks,
            spends=delivered.spends,
        ),
    ):
        return False
    state.data = bound.data
    return True


def _encoded(delivered: _records.DeliveredReport) -> dict[str, Any] | None:
    """Return the pinned object one delivered report is recorded as, or None.

    Every group but the subject, spelled by the owner the transaction shares
    them with, so a field added to one record is a field on both.

    None for a verification carrying no location, which is the refusal
    `record_delivered_report` promises answered where the record is built.
    """
    carried = _fields.carried_fields(delivered)
    if carried is None:
        return None
    return {
        _RECEIPT: delivered.receipt,
        _REVISION: delivered.report_revision,
        _REQUIREMENTS: delivered.requirements_revision,
        **_fields.routing_fields(delivered),
        **carried,
    }
