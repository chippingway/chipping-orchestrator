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
report are two reports the next tick would try to publish. That is also why
the report a caller offers is held against the one the comment CARRIES: the
write drops whatever is there, so a binding taken on an argument the record
does not match would replace a finished run's report with a value the comment
never held -- or with nothing, on an issue that delivered none. A binding the
transaction's own writer refuses leaves the caller's state untouched -- the
delivery stands, so nothing of the run's is lost by the refusal -- and it says
WHICH refusal it was, because the two are cleared by different things: a
comment too full is freed by the routes that write to it, while a record no
comment could hold the transaction for is a human's to look at.

What the transaction will cost is reserved when the DELIVERY is accepted, not
left to the binding to discover. The binding happens after the push, so a
report accepted here and refused there is one the code went out without -- and
the record cannot know the subject it will be bound to, so the reservation is
taken at the width every member of one is recorded at. A verification is the
one exception and needs no guess: its own location names the pull request the
transaction has to be about, and any other is a refusal the width could not
change.

The record is additive and is claimed exactly as the transaction beside it is: a
key holding `null` is the resting state a binding leaves, and a payload that is
there and is not an object is the claim a hand edit or a truncated write makes.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_record_fields as _fields,
    report_record_reading as _reading,
    report_record_state as _record_state,
    report_record_values as _record_values,
    report_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats

_RECEIPT = "receipt"

_REVISION = "revision"

_REQUIREMENTS = "requirements"

# Why a binding refused, in the words the caller's notice quotes. Two
# sentences rather than one because what clears them differs: room comes back
# on its own as the routes behind a deferred report write to the comment, and
# nothing about the comment would ever make the second binding possible.
CROWDED_COMMENT = (
    "the pinned comment cannot carry the publication transaction this report "
    "would become"
)

UNBINDABLE_RECORD = (
    "this report cannot be bound to the publication its code reached"
)

# The subject a delivered report will be bound to, at the width every member of
# one is recorded at: a reservation narrower than the field admits would accept
# a report whose transaction the binding then refuses, with the code already
# pushed. Sized from the readers' own bounds rather than from a margin, so a
# field either of them widens moves this with it.
# What most of those widths are filled with: one hex digit, since every field
# it stands in for is read as hex or as a slug half, and both are ASCII.
_FILLER = "f"

# The BRANCH is the one that is not, because its bound and the comment's are
# counted in different units. Its reader bounds it in CODEPOINTS and admits
# every one a JSON escape can spell, while the comment is measured in the
# characters that escape renders -- and a codepoint outside the BMP is written
# as a surrogate pair, twelve characters for one. Filled with a hex digit the
# reservation would be a twelfth of what the field admits, so a branch this
# workflow did not generate itself would be accepted here and refused at the
# binding, with the code already pushed and nothing left to ask the run that
# wrote the report. Filled with such a codepoint the width comes out of the
# same rendering that measures it, at whatever that rendering costs.
_BRANCH_FILLER = "\U0001f600"

_WIDEST_SUBJECT = _records.ReportSubject(
    repo_slug="/".join((_FILLER * _record_values.MAX_SLUG_HALF,) * 2),
    pr_number=_record_values.MAX_RECORDED_NUMBER,
    branch=_BRANCH_FILLER * _record_values.MAX_BRANCH,
    source_sha=_FILLER * max(_formats.COMMIT_LENGTHS),
    requirements_revision=_FILLER * max(_formats.DIGEST_LENGTHS),
)


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
    identically, when the comment could not carry it, or when the comment could
    not carry the TRANSACTION it will be bound into. Nothing is written on a
    refusal, so the caller's state is exactly as it was found and the caller is
    told while the work is still unpublished -- which is the only moment a
    report this build cannot deliver can still be asked for again.

    Both measurements are needed and the second is the one that costs
    something to skip. The binding happens after the push, and it writes more
    than this record does: the transaction carries the subject the publication
    settles, and its own acceptance reserves the code-publication receipt and
    the whole settling write beside it. Measured here only against this
    record's own write, a report would be accepted, the code pushed, and the
    binding refused -- which holds the work for a human with the code already
    out, at the one moment nothing can be asked of the run that wrote the
    report. Refused here, nothing is published at all.

    The subject that transaction will name is unknowable here, so the
    reservation is taken at the width every member of one is recorded at,
    which is never narrower than the subject that actually arrives. A
    VERIFICATION is held to its own location's pull request instead: that is
    the number the transaction has to be about, and a binding onto any other
    is a refusal no width could prevent.

    It is reserved over the comment the BINDING leaves rather than over this
    one, because the binding exchanges the two records: it drops the delivery
    in the write that records the transaction, so a delivery already standing
    here is room the transaction gets to spend, and a comment that never
    carried one still ends up holding the `null` that drop writes. Measured
    over the comment as it stands, a report replacing an undeliverable one is
    counted twice and refused with room to spare, and a first delivery is
    accepted without the tombstone its own binding then has to fit -- which is
    the refusal after the push this measurement exists to prevent.

    This record's OWN write is measured in two worlds for a reason of the same
    kind. What stands between it and the binding is the push, and the gate that
    pushes writes the code-publication receipt onto this same comment -- so the
    comment this write leaves has to still have room for that one. It is not
    the world the reservation above measures: that one has the delivery
    exchanged for the transaction, while this one is the delivery added to
    everything the issue already carries, a transaction an earlier publication
    left outstanding included. Measured against the bare comment alone, a
    record is accepted and the gate's own write is the one refused.

    The stale-approval HAND-BACK is reserved the same way, and for the same
    reason the push is: a record made on a review stage's drift road is
    accepted before that hand-back runs, and the hand-back writes a fresh
    review round, the marker saying the label move is owed, and the record
    that this publication's budget is already reset. Every one of them lands
    on this same comment between the record and its binding. Reserved at the
    widest hand-back there is, so the road that writes fewer of them cannot be
    the one refused -- and the same world stands under the transaction below,
    which is bound on the far side of it.

    The caller still owns `gh.write_pinned_state`, as every stage-facing writer
    here does, so the record rides whatever else that caller staged.
    """
    recorded = _encoded(delivered)
    if recorded is None or _reading.delivered_from(recorded) != delivered:
        return False
    handed_back = _record_state.with_later_writes(state, hand_back=True)
    for carried in (
        state,
        _record_state.with_later_writes(state, receipt=True),
        handed_back,
        _record_state.with_later_writes(handed_back, receipt=True),
    ):
        if not _record_state.fits_the_comment(
            {**carried.data, _records.DELIVERED_REPORT: recorded},
        ):
            return False
    reserved = _WIDEST_SUBJECT
    if delivered.location is not None:
        reserved = replace(
            _WIDEST_SUBJECT, pr_number=delivered.location.pr_number,
        )
    exchanged = _pinned_state.PinnedState(state_data=dict(handed_back.data))
    clear_delivered_report(exchanged)
    if not _record_state.record_pending_report(
        exchanged, _pending_for(delivered, reserved),
    ):
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
) -> str:
    """Stage the transaction this report becomes, or say why it cannot be.

    "" is bound. The subject is everything the publication settles and the run
    could not: the repository, the pull request the code landed on, the branch
    it went out under, and the commit it is standing on. Bound to them, the
    report a run wrote becomes a transaction a later tick can prove again from
    the record alone.

    ONE staged write, because the two records claim the same report: a drop
    without the transaction beside it loses a finished run's work, and a
    transaction beside the delivery it came from is a second report the next
    tick would publish. Built on a copy, a refusal leaves the caller's state
    exactly as it was found -- the delivery still standing, so the report is
    not lost by the refusal.

    Which refusal it was is answered rather than left to the caller to guess,
    because the two are cleared by different things. The same transaction is
    offered to an EMPTY comment to tell them apart: accepted there, the record
    is sound and it is this comment that is full -- which the routes behind a
    report still owed give back as they write to it, so a later tick binds what
    this one could not. Refused there too, no comment would ever hold this
    transaction: a verification asserting a report on another pull request, or
    a subject the transaction's own reader will not take. Nothing about
    waiting changes either, so what a caller owes then is a human.

    What is bound is the report this issue DELIVERED, so the record on the
    comment is what the caller's argument is held against and a difference of
    any kind refuses. The argument is a value the caller has been carrying --
    across a push, a pull request, and everything that can fail between them
    -- while the comment is where the report actually lives, and the two can
    part company. Bound without the comparison, an argument the comment has no
    record for would mint a transaction out of a value nobody wrote down, and
    a STALE one would drop the newer record standing there and replace it with
    an older report: the delivery is cleared by this write, so whatever it
    dropped is gone. Neither is about room, so both answer UNBINDABLE.

    The requirements revision is the one member of the subject this owner
    already holds, and a subject restating it differently is refused before
    anything is staged. It is the issue content the RUN was handed, frozen
    when the report was recorded precisely so a publication landing after an
    edit cannot claim the report answers one it never saw -- and a transaction
    bound to any other revision makes exactly that claim, then proves it
    against the wrong content on the tick it would settle.
    """
    if read_delivered_report(state) != delivered:
        return UNBINDABLE_RECORD
    if subject.requirements_revision != delivered.requirements_revision:
        return UNBINDABLE_RECORD
    bound = _pinned_state.PinnedState(state_data=dict(state.data))
    clear_delivered_report(bound)
    pending = _pending_for(delivered, subject)
    if _record_state.record_pending_report(bound, pending):
        state.data = bound.data
        return ""
    if _record_state.record_pending_report(_pinned_state.PinnedState(), pending):
        return CROWDED_COMMENT
    return UNBINDABLE_RECORD


def _pending_for(
    delivered: _records.DeliveredReport, subject: _records.ReportSubject,
) -> _records.PendingReport:
    """The transaction one delivered report becomes, bound to one subject.

    Spelled once because two callers build it: the acceptance that reserves
    what it will cost, and the binding that records it. Built apart, a member
    added to either record would be measured under one shape and written under
    another.
    """
    return _records.PendingReport(
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
    )


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
