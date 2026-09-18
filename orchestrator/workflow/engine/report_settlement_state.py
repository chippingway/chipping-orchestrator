# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a settled transaction leaves behind: one current report, one handoff.

Both are written in the same durable write that drops the pending record, and
that is the whole of what makes a replay safe. A settlement split across two
writes has a window in which the report is on the pull request and the record
still says it is owed -- and the tick after a crash there would publish a second
report, or spend the reviewer round a second time.

The two records answer different questions and neither substitutes for the
other. The CURRENT report says what the pull request carries now: it names the
exact location and the content revision, so a later reader can tell the report
it published from one a human has edited since, and so a reviewer is handed the
report that is actually there. The HANDOFF says that one transaction is
finished, keyed by the receipt that transaction was recorded under, so a replay
of the same receipt recognizes its own completed work instead of repeating it.

Neither carries the report text. What the text is for is publication, and once
that has happened GitHub holds it -- keeping a second copy on the pinned comment
would double the record's cost for a value nothing reads back and let the two
disagree the moment somebody edits the comment.

Both writers refuse rather than store what their own readers would not hand
back, and both records are CLAIMED by the mere presence of their key. Those two
are the same rule seen from either end: nothing here ever clears a settled
record -- a settlement replaces one -- so every shape these readers refuse got
onto the comment either from a caller that should have been told or from an
edit nobody made through this owner, and neither is an absence.
"""
from __future__ import annotations

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_record_fields as _fields,
    report_record_values as _record_values,
    report_records as _records,
)
from orchestrator.workflow.late_split import formats as _formats, payloads as _payloads

_REVISION = "revision"

_CONTENT_DIGEST = "content"

# Which road settled the report. Additive: a record without it was settled
# before the member existed, and one carrying a value that is no mode is damage.
_MODE = "mode"

_RECEIPT = "receipt"

_HANDOFF_PR = "pr"

_HANDOFF_SHA = "sha"


def carries_settled_record(state: _pinned_state.PinnedState) -> bool:
    """Whether this issue CLAIMS either settled record, readable or not.

    Presence rather than meaning, for the reason the pending record is asked
    that way: the readers below answer None for a record nobody can act on and
    for an issue that has none, and those are opposite answers to a caller
    about to WRITE over them. A damaged current report read as an absence is
    one a settlement quietly replaces after the report has been posted, and a
    damaged handoff read as an absence is a completed transaction nobody can
    recognize -- which is then published a second time.

    `null` is a CLAIM here, which is where this parts company with the pending
    record. That one is cleared on every settlement, so the key holding `null`
    is its ordinary resting state and testing presence alone would park every
    issue that had just finished a transaction. Nothing clears either record
    below: a settlement REPLACES them, and no other write touches them. So a
    settled key holding `null` is a truncated write or a hand edit -- and read
    as an absence it would be exactly the damage this question exists to
    catch, silently replaced by the next settlement or published over a second
    time.
    """
    return any(
        state.carries(key)
        for key in (_records.CURRENT_REPORT, _records.REPORT_HANDOFF)
    )


def read_current_report(
    state: _pinned_state.PinnedState,
) -> _records.CurrentReport | None:
    """Return the report this pull request carries, or None for none readable.

    None is both an issue that has published no report under this record and
    one whose record cannot be acted on. Neither licenses anything: a caller
    that needs the current report reads it afresh from GitHub at the location
    this names, and with no location there is nothing to read.
    """
    recorded = state.get(_records.CURRENT_REPORT)
    if not isinstance(recorded, dict):
        return None
    return _current_from(recorded)


def record_current_report(
    state: _pinned_state.PinnedState, current: _records.CurrentReport,
) -> bool:
    """Record the report the pull request now carries, or refuse to.

    Replaced rather than appended, because what this answers is which report is
    CURRENT -- the earlier ones stay on the pull request as history, where a
    reader who wants them can see them in order. The caller owns the write.

    False when this owner's own READER would not hand the record back
    identically, and nothing is written on a refusal. A caller can build a
    report about one pull request and a location on another, or a revision
    wider than any GitHub issues; stored, it reads back as damage on the very
    next tick, and the issue then carries a settled record nobody can act on in
    place of the one the report it just published deserved. Asked here, the
    caller hears it while the answer is still worth something.
    """
    recorded = {
        **_fields.subject_fields(current.subject),
        _REVISION: current.report_revision,
        _CONTENT_DIGEST: current.content_revision,
        **_fields.location_fields(current.location),
    }
    if current.mode is not None:
        recorded[_MODE] = str(current.mode)
    if _current_from(recorded) != current:
        return False
    state.set(_records.CURRENT_REPORT, recorded)
    return True


def read_handoff(
    state: _pinned_state.PinnedState,
) -> _records.ReportHandoff | None:
    """Return the completed handoff this issue records, or None for none.

    Read fail-closed like everything else here, and what a caller does with
    None is repeat the work: a handoff nobody can read is not evidence that a
    transaction finished, and re-running a settlement whose report is already
    on the thread finds it there rather than posting a second one.
    """
    recorded = state.get(_records.REPORT_HANDOFF)
    if not isinstance(recorded, dict):
        return None
    return _handoff_from(recorded)


def record_handoff(
    state: _pinned_state.PinnedState, handoff: _records.ReportHandoff,
) -> bool:
    """Record that one transaction finished, or refuse to.

    One handoff at a time, because what it is asked is whether the transaction
    in hand is already done. A later transaction on the same commit runs under
    a receipt of its own and replaces this, which is right: the question is
    never "did some handoff happen" but "did THIS one".

    Held to its own reader for the reason the current report is, and with one
    consequence of its own: a handoff written in a shape that reader refuses is
    a completed transaction nothing can recognize, so the replay that was meant
    to find its own finished work repeats it instead.
    """
    recorded = {
        _RECEIPT: handoff.receipt,
        _HANDOFF_PR: handoff.pr_number,
        _REVISION: handoff.report_revision,
        _HANDOFF_SHA: handoff.source_sha,
    }
    if _handoff_from(recorded) != handoff:
        return False
    state.set(_records.REPORT_HANDOFF, recorded)
    return True


def _current_from(recorded: dict) -> _records.CurrentReport | None:
    """Return the current report one recorded object is, or None for damage.

    The location is bound to the subject's pull request, exactly as a pending
    verification's is. A location is exact in both halves and still names a
    place anywhere in the repository, so a record whose subject says one pull
    request and whose location sits on another says the report this pull
    request carries is somewhere else -- which is what a reviewer would then be
    handed, and what a later transaction would compare its own revision
    against.
    """
    subject = _fields.subject_from(recorded)
    location = _fields.location_from(recorded)
    revision = _record_values.as_recorded_number(recorded.get(_REVISION))
    digest = _payloads.as_hex(
        recorded.get(_CONTENT_DIGEST), _formats.DIGEST_LENGTHS,
    )
    if subject is None or location is None or not revision or not digest:
        return None
    if location.pr_number != subject.pr_number:
        return None
    mode = _payloads.as_member(_records.ReportMode, recorded.get(_MODE))
    if mode is None and recorded.get(_MODE) is not None:
        return None
    return _records.CurrentReport(
        subject=subject,
        report_revision=revision,
        content_revision=digest,
        location=location,
        mode=mode,
    )


def _handoff_from(recorded: dict) -> _records.ReportHandoff | None:
    """Return the handoff one recorded object is, or None for damage.

    The receipt is held to the same spelling the pending record's is, because
    the two are compared: a receipt that reads back here in a shape the other
    reader would refuse could never match the transaction it claims to have
    settled, and would leave that transaction replaying forever.
    """
    receipt = _record_values.as_receipt(recorded.get(_RECEIPT))
    pr_number = _record_values.as_recorded_number(recorded.get(_HANDOFF_PR))
    revision = _record_values.as_recorded_number(recorded.get(_REVISION))
    source_sha = _payloads.as_hex(
        recorded.get(_HANDOFF_SHA), _formats.COMMIT_LENGTHS,
    )
    if not receipt or not pr_number or not revision or not source_sha:
        return None
    return _records.ReportHandoff(
        receipt=receipt,
        pr_number=pr_number,
        report_revision=revision,
        source_sha=source_sha,
    )
