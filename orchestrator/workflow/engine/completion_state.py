# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an issue's pinned state says about its captured completion, read without writing.

`carries` and `read` answer different questions, and both are needed, as they
are for every report record. A reader deciding what the capture MEANS reads it
fail-closed, so a record nothing can act on comes back as none -- which is
exactly wrong for a caller asking whether the issue CLAIMS one. An issue that
never captured anything is the supported absence, and the field is missing;
anything else in the field -- `null` included, which no writer here spells --
is a claim, and one `read` answers None for is a damaged capture: never acted
on, never replaced by another invocation's, and never cleared as if it were
nothing.

A handed-off capture is the one record of the commit the delivery it became
is about, and the one record that the report came from a capture at all, until
the transaction that delivery becomes settles. So while the delivery or its
transaction stands -- or a claim of either nobody can read stands, which may
be it -- the capture is neither retired nor replaced (`source_owed`), save by a
later capture carrying it while the delivery stands unbound; the binding holds
a publication to the branch and commit the capture reported on, or the one a
pending capture carries (`binding_hold`); and the binding and settlement of
that report are measured with every terminator escaped (`escapes_in_full`), as
its capture and transfer were. A capture nobody can read holds every binding and is measured the same
way: whether the report came from it is exactly what its damage hides, so it
is never read as no constraint at all.
"""
from __future__ import annotations

from enum import StrEnum

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_records as _records,
    completion_spelling as _spelling,
    report_delivery_state as _delivery_state,
    report_record_state as _record_state,
)

# What a write deciding on a delivery's captured source is decided on: the
# capture the delivery may have been handed off from.
DECIDED_ON = frozenset((_records.DEVELOPER_COMPLETION,))

# The two records a handed-off report lives in until it settles, each asked
# as a claim and as a reading.
_OUTSTANDING = (
    (_delivery_state.carries_delivered_report, _delivery_state.read_delivered_report),
    (_record_state.carries_pending_report, _record_state.read_pending_report),
)


class SourceHold(StrEnum):
    """Why a delivery may not be bound to a publication, on the strength of the capture beside it."""

    # The issue claims a capture nobody can read, which may be the one the
    # delivery was handed off from.
    DAMAGED = "damaged"
    # The delivery was handed off from a capture of another branch or commit.
    ELSEWHERE = "elsewhere"


def carries(state: PinnedState) -> bool:
    """Whether the issue CLAIMS a captured completion, whatever the field holds."""
    return state.carries(_records.DEVELOPER_COMPLETION)


def read(state: PinnedState) -> _records.CompletionCapture | _records.ResolvedCapture | None:
    """The captured completion `state` carries: None where it carries none, or carries one nothing can read."""
    if not carries(state):
        return None
    return _spelling.read_record(state.get(_records.DEVELOPER_COMPLETION))


def unresolved(state: PinnedState) -> bool:
    """Whether the issue claims a capture still owed a decision: a pending one, or one nobody can read.

    Every developer launch is held on one (`implementing.execution`): its
    return could not be captured beside it, and it would run again over work
    the capture already holds, or over whatever the damaged one was.
    """
    return carries(state) and not isinstance(read(state), _records.ResolvedCapture)


def source_owed(
    state: PinnedState, captured: _records.CompletionCapture | _records.ResolvedCapture | None,
) -> bool:
    """Whether `captured` is a handoff still owed to the report it became, which has not settled yet.

    True while the delivery or the transaction its receipt names stands on
    `state`, and while `state` claims either record in a shape nobody can
    read, which may be that one. A settlement ends what is owed, and so does
    a later report superseding the one the handoff became.
    """
    if not isinstance(captured, _records.ResolvedCapture) or captured.stage is not _records.CaptureStage.HANDED_OFF:
        return False
    for claims, reads in _OUTSTANDING:
        if claims(state):
            outstanding = reads(state)
            if outstanding is None or outstanding.receipt == captured.receipt:
                return True
    return False


def binding_hold(state: PinnedState, receipt: str, branch: str, commit: str) -> SourceHold | None:
    """Why the delivery `receipt` names may not be bound to `branch` at `commit`, or None.

    None where the issue carries no capture, or one the delivery was not
    handed off from -- every delivery a run recorded for itself -- or one
    that reported on exactly that branch and commit. A pending or retired
    capture still carrying the handoff the delivery came from holds it as
    that handoff did.
    """
    if not carries(state):
        return None
    captured = read(state)
    if captured is None:
        return SourceHold.DAMAGED
    handoff = captured.standing_handoff
    handed_off = isinstance(handoff, _records.ResolvedCapture) and handoff.stage is _records.CaptureStage.HANDED_OFF
    if not handed_off or handoff.receipt != receipt:
        return None
    return None if (handoff.branch, handoff.source_sha) == (branch, commit) else SourceHold.ELSEWHERE


def escapes_in_full(state: PinnedState, receipt: str) -> bool:
    """Whether the report `receipt` names is measured with every terminator escaped wherever it is written.

    True for a report a capture was handed off as -- one a pending or
    retired capture carries included -- and beside a capture nobody can read, which may be
    the one it came from; every report a run recorded for itself keeps the
    writer's own measurement.
    """
    if not carries(state):
        return False
    captured = read(state)
    if captured is None:
        return True
    handoff = captured.standing_handoff
    handed_off = isinstance(handoff, _records.ResolvedCapture) and handoff.stage is _records.CaptureStage.HANDED_OFF
    return handed_off and handoff.receipt == receipt
