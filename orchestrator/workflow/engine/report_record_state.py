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
opposite answers to the second. A caller settling a transaction asks both, so a
damaged record holds the tick rather than reading as an issue with nothing
outstanding.

What that comment has to carry is measured over the whole window the record is
outstanding for, not over the comment as it stands. A transaction can be
recorded before the commit it reports on is pushed, and the publication gate
behind the reconciliation writes a receipt onto this same comment when it
pushes -- so the receipt is reserved here as well as the settlement, and a
record is accepted only where both of the writes that follow it still fit.

The write is refused rather than truncated when the record would not fit the
comment. A transaction is worth exactly what a later tick can read back, and a
half-written one is the shape this owner exists to refuse -- so a report too
large to record is one this workflow will not accept the transaction for at all,
and the caller hears that where it can still do something about it.

That measurement is offered to the publication as well as taken at acceptance,
because a record that defers lets the routes behind the guard run and every one
of them writes to this same comment. What was reserved can be spent by work
entitled to spend it, so the room is proved again on the tick that would use it
-- before the report is posted, while a refusal still costs nothing.
"""
from __future__ import annotations

import importlib
from typing import Any

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.github.pull_request_reports import ReportLocation
from orchestrator.workflow.engine import (
    comments as _comments,
    report_consumed_values as _consumed,
    report_record_fields as _fields,
    report_record_reading as _reading,
    report_record_values as _record_values,
    report_records as _records,
    report_settlement_state as _settlement,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.late_split import formats as _formats

_RECEIPT = "receipt"

_REVISION = "revision"

_MODE = "mode"

_ROUTE = "route"

_REPORT = "report"

_CONTENT_DIGEST = "content"

_WATERMARKS = "watermarks"

_SPENDS = "spends"

# The two values a settlement will hold that this transaction cannot yet name:
# the digest the published text will hash to, and the comment id GitHub will
# answer the post with -- which is recorded twice, once as the report's exact
# location and once in the comment-id ledger. Measured at their widest -- a
# whole digest, and the ceiling every recorded number is already held to -- so
# the settlement sized here is never smaller than the one that actually happens.
_WIDEST_DIGEST = "f" * max(_formats.DIGEST_LENGTHS)

_WIDEST_IDENTITY = _record_values.MAX_RECORDED_NUMBER

# The widest commit either member of the code-publication receipt is recorded
# at. The head a push replaces is the member a record cannot know at all; the
# commit beside it is one a record knows for ITSELF and not for whatever else
# may be pushed while it waits, so both are sized here at what the field can
# hold rather than at what this transaction expects.
_WIDEST_COMMIT = "f" * max(_formats.COMMIT_LENGTHS)


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

    The write that will SETTLE this transaction is measured here too, because
    it happens after the report is on the thread. A record accepted at the
    ceiling and settled past it would leave a published comment, a record still
    claiming it is owed, and a retry that fails identically for the rest of the
    issue's life. It is measured rather than allowed for, so a field either
    settled record grows moves this refusal with it instead of quietly eating a
    margin nobody rechecks.

    False too when this owner's own READER would not hand the record back
    identically. Size is only one of the ways a transaction can be
    unpublishable: a report past `MAX_REPORT_TEXT`, one quoting a receipt
    marker, a branch with whitespace in it, a verification whose location sits
    on another pull request or that carries none at all. Written anyway, every
    one of those reads back as damage on the very next tick -- and the issue
    parks for a record this process itself produced. Refused here, the caller
    hears it while the run that wrote the report is still there to be told.

    Both measurements are taken over a comment that already carries the
    CODE-PUBLICATION RECEIPT this transaction is waiting for, because a record
    may be written before the commit it reports on is pushed. The evidence
    behind it then stands down to the publication gate, and that gate WRITES:
    the commit it put on the remote, the head that push replaced, and the pull
    request it went onto. That write lands between this record and the
    settlement, on this same comment -- so a record accepted without room for
    it leaves the gate's own write refused, or the settlement refused after the
    report is already on the thread, and either way a transaction retrying
    identically for the rest of the issue's life.

    It is reserved whether or not the commit is published already, since a
    record cannot know which and a later push onto the same commit rewrites the
    head it replaced in any case. Written through the gate's own owner, at the
    widest every member of that receipt can be recorded at: a record cannot
    know the head a push will replace, and holding the other two to this
    transaction's own values would model a receipt NARROWER than one the gate
    could write for a commit somebody pushed past it.

    BOTH worlds are measured, this comment as it stands and the same comment
    carrying that widest receipt, because neither is wider than the other in
    every field. The reservation REPLACES what is there -- so against a receipt
    already recorded under a wider spelling than any writer here produces, the
    reserved world is the smaller of the two, and measuring it alone would
    accept a record whose own write is past the ceiling the moment it lands.
    Measuring both is what makes the answer "this record fits whatever happens
    next", rather than "it fits one of the things that might".

    The caller still owns `gh.write_pinned_state`, as every stage-facing writer
    here does, so the record rides whatever else that caller staged rather than
    landing in a write of its own ahead of it.
    """
    recorded = _encoded(pending)
    if recorded is None or _reading.pending_from(recorded) != pending:
        return False
    reserved = _pinned_state.PinnedState(state_data=dict(state.data))
    importlib.import_module(
        _stage_targets._LATE_PUBLICATION_STATE_OWNER,
    )._record_publication(
        reserved, _WIDEST_COMMIT, _WIDEST_COMMIT, _WIDEST_IDENTITY,
    )
    for carried in (state, reserved):
        staged = {**carried.data, _records.PENDING_REPORT: recorded}
        settled = settled_payload(carried, pending)
        if settled is None or not fits_the_comment(staged) or not fits_the_comment(settled):
            return False
    state.set(_records.PENDING_REPORT, recorded)
    return True


def fits_the_comment(staged: dict) -> bool:
    """Whether the comment one staged payload writes is one GitHub accepts.

    Public because the publication asks it of `settled_payload` below on the
    tick it would settle, not only here on the tick the record was accepted.
    """
    written = len(_pinned_state.pinned_state_body(staged))
    return written <= _pinned_state.MAX_PINNED_BODY


def settled_payload(
    state: _pinned_state.PinnedState, pending: _records.PendingReport,
) -> dict | None:
    """Return the payload settling this transaction would leave behind, or None.

    Public because it is asked twice about the same transaction: here, when the
    record is accepted, and again by the publication on the tick that would
    settle it. A transaction that cannot complete stands down on purpose, so
    the routes behind the guard run -- and a park taken, a notice recorded, a
    ledger entry added, a watermark advanced all write to this same comment.
    What was reserved can be spent by work entitled to spend it, so the room
    the first answer proved is not the room the settlement has.

    The WHOLE settlement, not only its two records: a completion also advances
    the watermarks the run consumed and closes the round and bookmarks its
    route spent, and every one of those lands on this same comment. Counted
    short, a transaction is accepted at the ceiling and settles past it -- the
    one failure this measurement exists to prevent.

    Built through the owners that perform that write rather than spelled again
    here, because what is being measured is that write and not a second
    description of it: a field added there has to move this measurement, and
    one this owner copied could not.

    Widest at the two values a settlement does not know yet -- the digest the
    published text will hash to and the comment id the post will answer with --
    so the size measured is an upper bound on the one that actually lands.

    The comment-id LEDGER grows on the same road and is reserved here for the
    same reason, which is the one piece of the settling write that does not
    happen in the settlement itself: publishing the report records the comment
    it landed as, so that a later drift hash and every feedback scan pass over
    this orchestrator's own text instead of reading it back as a human's. That
    entry lands between this measurement and the settlement, so a transaction
    accepted at the ceiling without it settles past the ceiling -- and the
    write that fails then fails after the report is already on the thread, and
    goes on failing identically for the rest of the issue's life.

    Reserved only under PUBLISH, which is the only mode that posts, and through
    the ledger's own owner rather than as a second guess at what an entry
    costs, so the reservation moves with that owner's cap and eviction. What
    the owner is handed is the width this domain records an id at; which id it
    reserves at that width is the ledger's own to choose, because its writer is
    idempotent and one it already holds would reserve nothing while the real
    publication went on to add an entry of its own.

    None where either settled write refuses the record this transaction would
    hand it, which is a transaction with no settlement to measure at all. The
    values here are the pending record's own, already proved by the reader
    above, so nothing a caller can pass reaches that answer today -- it is
    there because a measurement that quietly skipped a write it could not make
    would report a settlement smaller than the one that has to happen.
    """
    settled = _pinned_state.PinnedState(state_data=dict(state.data))
    if pending.mode is _records.ReportMode.PUBLISH:
        _comments._reserve_comment_slot(settled, _WIDEST_IDENTITY)
    _consumed.advance_consumed(settled, pending.watermarks)
    _consumed.close_bookkeeping(settled, pending.spends)
    recorded = _settlement.record_current_report(settled, _records.CurrentReport(
        subject=pending.subject,
        report_revision=pending.report_revision,
        content_revision=_WIDEST_DIGEST,
        location=ReportLocation(
            pr_number=pending.subject.pr_number, comment_id=_WIDEST_IDENTITY,
        ),
    ))
    handed = _settlement.record_handoff(settled, _records.ReportHandoff(
        receipt=pending.receipt,
        pr_number=pending.subject.pr_number,
        report_revision=pending.report_revision,
        source_sha=pending.subject.source_sha,
    ))
    if not recorded or not handed:
        return None
    clear_pending_report(settled)
    return settled.data


def clear_pending_report(state: _pinned_state.PinnedState) -> None:
    """Drop the transaction, settled or superseded.

    Written as an absence rather than removed, which is what every other
    cleared group here does: the key stays on the comment holding `null`, and
    both readers above answer for that exactly as they answer for an issue
    that never had one.
    """
    state.set(_records.PENDING_REPORT, None)


def _encoded(pending: _records.PendingReport) -> dict[str, Any] | None:
    """Return the pinned object one transaction is recorded as, or None.

    The mode's own half is written only under the mode that owns it, so a
    record says one thing rather than carrying a text and a location that
    could disagree about which report it is about.

    None for a verification carrying no location. The field is optional on the
    transaction because a publication has none, so a verification without one
    is a value a caller can construct and this owner cannot record -- answered
    as the refusal `record_pending_report` promises rather than raised out of
    the middle of it, which would leave that promise unkept.
    """
    carried: dict[str, Any] = {_REPORT: pending.report}
    if pending.mode is _records.ReportMode.VERIFY:
        if pending.location is None:
            return None
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
