# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The pending transaction's round trip through the pinned comment.

The record goes down BEFORE the report or the code it reports on is published,
which is the whole of what makes the publication recoverable: a process that
dies anywhere after this write comes back to a transaction naming what it was
doing, and one that dies before it comes back to an issue that simply has not
started.

`carries` and `read` answer different questions and both are needed. A reader
deciding what a transaction MEANS reads it fail-closed, so a record nothing can
act on comes back as no record -- which is right there and exactly wrong for the
guard asking whether this issue CLAIMS one: an issue that recorded nothing and
one whose record a hand edit truncated are the same absence to the first and
opposite answers to the second. The reconciliation asks both, so a damaged
record holds the tick rather than reading as an issue with nothing outstanding.

The write is refused rather than truncated when the record would not fit the
comment. A transaction is worth exactly what a later tick can read back, and a
half-written one is the shape this owner exists to refuse -- so a report too
large to record is one this workflow will not accept the transaction for at all,
and the caller hears that where it can still do something about it.
"""
from __future__ import annotations

from typing import Any

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_record_fields as _fields,
    report_record_reading as _reading,
    report_records as _records,
)

_RECEIPT = "receipt"

_REVISION = "revision"

_MODE = "mode"

_ROUTE = "route"

_REPORT = "report"

_CONTENT_DIGEST = "content"

_WATERMARKS = "watermarks"

_SPENDS = "spends"


def carries_pending_report(state: _pinned_state.PinnedState) -> bool:
    """Whether this issue CLAIMS a transaction, whatever the record holds.

    Presence rather than meaning. The reader below answers None for a record
    it cannot act on and for an issue that has none, and those are the two
    answers a guard may never confuse: one is an issue with nothing to do and
    the other is an issue whose outstanding publication nobody can describe.

    `null` is an absence rather than a claim, and it has to be, because that is
    exactly what a SETTLED transaction leaves: the drop writes the key rather
    than removing it, so a key tested for its presence alone would read every
    issue that has ever published a report as one whose record is damaged --
    and park it, on the very next tick, for a transaction it had just finished.
    A payload that is there and is not an object is the real claim this tells
    apart: an array, a number, a truncated write, a hand edit.
    """
    if not state.carries(_records.PENDING_REPORT):
        return False
    return state.get(_records.PENDING_REPORT) is not None


def read_pending_report(
    state: _pinned_state.PinnedState,
) -> _records.PendingReport | None:
    """Return the transaction this issue has outstanding, or None for none.

    None covers both an issue that recorded nothing and a record this build
    cannot act on -- an older binary's spelling, a hand edit, a member that
    will not type. `carries_pending_report` beside this is what tells them
    apart.
    """
    recorded = state.get(_records.PENDING_REPORT)
    if not isinstance(recorded, dict):
        return None
    return _reading.pending_from(recorded)


def record_pending_report(
    state: _pinned_state.PinnedState, pending: _records.PendingReport,
) -> bool:
    """Stage one transaction onto the pinned state, or refuse to.

    False when the comment could not carry the record, measured against what
    the write would actually produce rather than against the report's own
    length: the record shares the comment with everything else this issue has
    recorded, and the caller is about to publish on the strength of a record
    that has to be readable afterwards. Nothing is written on a refusal, so the
    caller's state is exactly as it was found.

    The caller still owns `gh.write_pinned_state`, as every stage-facing writer
    here does, so the record rides whatever else that caller staged rather than
    landing in a write of its own ahead of it.
    """
    recorded = _encoded(pending)
    staged = {**state.data, _records.PENDING_REPORT: recorded}
    if len(_pinned_state.pinned_state_body(staged)) > _pinned_state.MAX_PINNED_BODY:
        return False
    state.set(_records.PENDING_REPORT, recorded)
    return True


def clear_pending_report(state: _pinned_state.PinnedState) -> None:
    """Drop the transaction, settled or superseded.

    Written as an absence rather than removed, which is what every other
    cleared group here does: the key stays on the comment holding `null`, and
    both readers above answer for that exactly as they answer for an issue
    that never had one.
    """
    state.set(_records.PENDING_REPORT, None)


def _encoded(pending: _records.PendingReport) -> dict[str, Any]:
    """Return the pinned object one transaction is recorded as.

    The mode's own half is written only under the mode that owns it, so a
    record says one thing rather than carrying a text and a location that
    could disagree about which report it is about.
    """
    carried: dict[str, Any] = {_REPORT: pending.report}
    if pending.mode is _records.ReportMode.VERIFY:
        carried = {
            _CONTENT_DIGEST: pending.content_revision,
            **_fields.location_fields(pending.location),
        }
    return {
        _RECEIPT: pending.receipt,
        **_fields.subject_fields(pending.subject),
        _REVISION: pending.report_revision,
        _MODE: str(pending.mode),
        _ROUTE: str(pending.route),
        _WATERMARKS: [list(pair) for pair in pending.watermarks],
        _SPENDS: [list(pair) for pair in pending.spends],
        **carried,
    }
