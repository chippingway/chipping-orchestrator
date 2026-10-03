# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which measurement of the pinned comment refused a report record, and by how much.

A report record is accepted only where every comment it leads to is one GitHub
takes: the comment its own write leaves, the transaction a delivered report is
later bound into, and the settlement that ends it -- each beside the writes
other roads land on that same comment in between. A refusal at any of those is
about the comment's ROOM, which no reading of the record can tell: the report
is a valid one, and what is short is the space the rest of the issue leaves it.
So the capacity refusal is an answer of its own, named apart from the
`RecordRefusal` a record's reading gives, and given only where one of those
serialized measurements actually failed -- a record that will not read, or
whose settlement cannot even be built, is refused as invalid rather than as one
too big to keep.

It says WHICH measurement failed, because each is a different write: the
record's own, the binding a delivered report is reserved against, or the
settlement. It says which later writes the comment measured was carrying -- the
code-publication receipt the push leaves, the stale-approval hand-back a review
stage leaves, or both -- since those are room spent by roads other than the
record's. And it carries the size that comment rendered to beside the ceiling
it passed, in the characters GitHub counts, so whoever reads the refusal can see
how far over it was.

The worlds those later writes make are built here as well, because they are
what an overflow names. Both are written through the owners that write them for
real rather than spelled again, so a member added to either moves every
reservation taken against it. Like the reading's refusal, all of this is held in
memory only: the pinned comment records a report or does not, never why.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, replace
from enum import StrEnum

from orchestrator.github import pinned_state as _pinned_state
from orchestrator.workflow.engine import (
    report_record_values as _record_values,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.late_split import formats as _formats

# The widest commit either member of the code-publication receipt is recorded
# at. The head a push replaces is the member a record cannot know at all; the
# commit beside it is one a record knows for ITSELF and not for whatever else
# may be pushed while it waits, so both are sized here at what the field can
# hold rather than at what the record expects.
_WIDEST_COMMIT = "f" * max(_formats.COMMIT_LENGTHS)

# The pull request the receipt names, at the ceiling every recorded number is
# already held to.
_WIDEST_IDENTITY = _record_values.MAX_RECORDED_NUMBER


class MeasuredWrite(StrEnum):
    """Which write's comment a record was measured against.

    `RECORD` is the comment the record's own write leaves, a delivered
    report's or a transaction's. `BINDING` is the transaction a delivered
    report becomes once its code reaches a pull request, reserved when the
    delivery is accepted because the binding happens after the push.
    `SETTLEMENT` is the write that ends a transaction once its report is out.
    """

    RECORD = "record"
    BINDING = "binding"
    SETTLEMENT = "settlement"


@dataclass(frozen=True)
class LaterWrites:
    """Which writes landing after a record the measured comment carried.

    `receipt` is the code-publication receipt the gate writes when it pushes;
    `hand_back` is the stale-approval hand-back `in_review` writes when a
    requirements edit sends an approved pull request back. Neither is the
    record's own write, so a refusal carrying one is room other roads spend.
    """

    receipt: bool = False
    hand_back: bool = False

    def over(
        self, state: _pinned_state.PinnedState,
    ) -> _pinned_state.PinnedState:
        """The same comment, carrying these writes (`with_later_writes`)."""
        return with_later_writes(
            state, receipt=self.receipt, hand_back=self.hand_back,
        )


@dataclass(frozen=True)
class CommentOverflow:
    """One measured comment past what GitHub accepts, and which one it was.

    `size` is the body the comment renders to and `limit` the most a pinned
    comment may be, both counted the way `pinned_state_body` renders them.
    """

    write: MeasuredWrite
    later: LaterWrites
    size: int
    limit: int

    @classmethod
    def of(
        cls, staged: dict, write: MeasuredWrite, later: LaterWrites,
    ) -> CommentOverflow:
        """The overflow one staged payload is, once the fit test refused it.

        Built only after `report_record_state.fits_the_comment` has said no,
        so the refusal and the size it reports are one rendering's: the
        ceiling is decided there, and this names what was measured against it.
        """
        return cls(
            write=write,
            later=later,
            size=len(_pinned_state.pinned_state_body(staged)),
            limit=_pinned_state.MAX_PINNED_BODY,
        )


# Every answer a refused record gives: its own reading's, or the room it lacks.
RecordingRefusal = _record_values.RecordRefusal | CommentOverflow


def through_the_binding(
    refusal: RecordingRefusal | None, handed: LaterWrites,
) -> RecordingRefusal | None:
    """The reserved transaction's refusal, as the delivery reserving it hears it.

    A delivered report is accepted only where the transaction it becomes would
    be, and that transaction is measured by its own writer -- whose RECORD is,
    from the delivery's side, the BINDING. Its settlement stays a settlement,
    its receipt stays what that writer measured, and the hand-back is the one
    the delivery's own road reserved under it, which the transaction's writer
    never asks about. Anything but an overflow is passed on as it came.
    """
    if not isinstance(refusal, CommentOverflow):
        return refusal
    write = refusal.write
    if write is MeasuredWrite.RECORD:
        write = MeasuredWrite.BINDING
    return replace(
        refusal,
        write=write,
        later=replace(refusal.later, hand_back=handed.hand_back),
    )


def with_later_writes(
    state: _pinned_state.PinnedState,
    *,
    receipt: bool = False,
    hand_back: bool = False,
) -> _pinned_state.PinnedState:
    """The same comment, carrying a write that lands on it after a record.

    Public because every record written before a commit is pushed is measured
    against these worlds as well as against the comment in hand: the
    transaction, and the delivered report recorded ahead of the gate that
    becomes one. Two writes stand between such a record and its settlement,
    and both land on this same comment.

    The code-publication RECEIPT is the gate's, made when it pushes: the
    commit it put on the remote, the head that push replaced, and the pull
    request it went onto. Accepted without room for it, the gate's own write
    is the one refused.

    The stale-approval HAND-BACK is the review stages', made when a
    requirements edit sends an approved pull request back: a fresh review
    round, the marker saying the label move is owed, and the record that the
    publication this report is about already has its budget. Accepted without
    room for those, the report's own binding is refused instead -- after the
    code has gone out, with nothing left to ask the run that wrote it. It is
    reserved at its widest, the hand-back that owes a publication, since the
    narrower one writes a strict subset.

    Both are written through the owners that write them for real rather than
    spelled again here, so a member added to either moves every reservation
    taken against it. The receipt REPLACES what is there, which is why the
    world without it is measured too: a comment can already carry one written
    wider than any spelling this build produces.
    """
    reserved = _pinned_state.PinnedState(state_data=dict(state.data))
    if receipt:
        importlib.import_module(
            _stage_targets._LATE_PUBLICATION_STATE_OWNER,
        )._record_publication(
            reserved, _WIDEST_COMMIT, _WIDEST_COMMIT, _WIDEST_IDENTITY,
        )
    if hand_back:
        importlib.import_module(
            _stage_targets._IN_REVIEW_HANDOFF_OWNER,
        ).stages_the_handoff(reserved, owed_publication=True)
    return reserved
