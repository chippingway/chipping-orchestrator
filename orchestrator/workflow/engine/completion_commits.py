# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one write over a captured completion is bound to, and what it can come to.

Every write over a capture -- the capture itself, its transfer into the report
delivery, its retirement -- and its read-back are asked over the pinned
comment the caller holds, read afresh and admitted again (`pinned_commit.reread`):
unreadable, unparsed, unsupported, deleted, or replaced, it is refused with the
guarded commit's own reason and nothing is sent. The invocation the capture
belongs to has to name that comment, its repository, and its issue -- a
comment a human pinned in place of the one the run was charged on is no record
of that run, whatever it copied -- and the workflow cycle the comment is on: a
restart has ended the cycle a capture of the old one answered. A cycle identity
or a capture no reader can name is damage, refused rather than taken for an
absence, and a capture the field holds damaged is never replaced, cleared, or
acted on here.

Each answer is one of four, as the guarded commit's are. LANDED is a write this
call landed and STANDING a record that already read as asked, so nothing was
sent -- a read-back's answer, and every repeat's. UNCONFIRMED is a write that
went out and was never confirmed: the record may read either way, and only a
read-back says which. REFUSED wrote nothing and says why: the commit's own
refusal, the report's or the comment room's (`report_record_room`), or this
domain's (`CheckpointRefusal`). Only the first two settle anything.

What a write landed, or a read-back found, is laid back onto the caller's
state as the comment's (`pinned_commit.takes_in`), so the caller's own
whole-state write keeps it rather than putting back a record without it -- for
a handoff, the delivery that owns the report as well as the capture, so a
caller that confirms one holds what it confirmed. A
write sent and never confirmed withholds the caller's state from every
whole-state write instead: that write would put back the record as it read
before, over a capture -- or the report delivery a transfer recorded -- that
may have landed. So does every answer, landed, standing, or refused, given
over a comment that no longer reads as the one the caller read, or that would
not be read at all: what the caller does not hold -- another report's
delivery, a field a transfer retired, a damaged claim -- its whole-state write
would put back as it read it, so it writes nothing until a fresh reading.
"""
from __future__ import annotations

import copy
import enum
import json
import logging
from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import MAX_PINNED_BODY, PinnedState
from orchestrator.workflow.engine import (
    completion_records as _records,
    completion_state as _state,
    invocations as _invocations,
    pinned_commit as _pinned_commit,
    pinned_commit_models as _commit_models,
    report_record_room as _room,
)
from orchestrator.workflow.late_split import keys as _late_keys

log = logging.getLogger("orchestrator.workflow")


# What every write over a capture is decided on: the capture itself, and the
# workflow cycle its invocation is bound to.
DECIDED_ON = (_records.DEVELOPER_COMPLETION, _late_keys.CYCLE_ID)


class CheckpointStatus(enum.Enum):
    """What one write over a capture, or its read-back, came to."""

    LANDED = "landed"
    STANDING = "standing"
    UNCONFIRMED = "unconfirmed"
    REFUSED = "refused"


class CheckpointRefusal(enum.Enum):
    """Why a write over a capture was refused before its commit was asked; a refused commit names its own reason."""

    # The invocation names another repository, issue, or pinned comment.
    FOREIGN = "foreign"
    # The invocation ran in a workflow cycle the record is no longer on.
    OTHER_CYCLE = "other_cycle"
    # The capture or the cycle identity reads as nothing this build writes.
    DAMAGED = "damaged"
    # Another invocation's capture is still pending.
    UNRESOLVED = "unresolved"
    # A capture of this invocation's, or of a later one's, already resolved.
    SUPERSEDED = "superseded"
    # The record carries no capture of this invocation.
    ABSENT = "absent"
    # The capture was retired, so it carries no report to hand on.
    RETIRED = "retired"
    # A settled retirement asked of a capture never handed off.
    NOT_HANDED_OFF = "not_handed_off"
    # A handed-off capture whose report has not settled yet, and is the one
    # record of the commit that report is about.
    UNBOUND = "unbound"
    # A record the road's handoff was frozen over has moved since.
    HANDOFF_MOVED = "handoff_moved"
    # The report outcome earns no delivered report.
    UNRECORDABLE = "unrecordable"


@dataclass(frozen=True)
class CheckpointOutcome:
    """One answer: its status, the stage the capture stands at, and for a refusal why and the fields it named.

    `stage` is what the record carries for the invocation once the answer
    settles -- None for a read-back finding no capture of it -- and `refusal`
    this domain's reason, the guarded commit's, or the report's or room's
    (`report_record_room.RecordingRefusal`).
    """

    status: CheckpointStatus
    stage: _records.CaptureStage | None = None
    refusal: CheckpointRefusal | _commit_models.CommitRefusal | _room.RecordingRefusal | None = None
    fields: tuple[str, ...] = ()

    @property
    def settled(self) -> bool:
        """Whether the record durably reads as asked: the only answers dependent work may follow."""
        return self.status in {CheckpointStatus.LANDED, CheckpointStatus.STANDING}


@dataclass(frozen=True)
class CompletionCommit:
    """One invocation's capture, the issue it is on, and the caller state its writes are laid back onto."""

    gh: GitHubClient
    issue: Issue
    state: PinnedState
    invocation: AgentInvocation

    def fresh(self) -> PinnedState | CheckpointOutcome:
        """The caller's comment read afresh and admitted, bound to the invocation; or why it cannot be acted on.

        A comment that no longer reads as the one the caller read -- another
        road's write, a hand edit, a damaged claim, or one that would not read
        at all -- withholds the caller's state, whatever is answered over it.
        """
        guard = _commit_models.PinnedCommit.capture(self.state)
        fresh = _pinned_commit.reread(self.gh, self.issue, guard)
        if _stale(fresh, self.state):
            self.state.withheld = True
        if isinstance(fresh, _commit_models.CommitOutcome):
            return self.refused(fresh.refusal)
        unbound = _unbound(fresh, self.invocation, self.issue.number)
        return fresh if unbound is None else self.refused(unbound)

    def standing(
        self,
        reading: PinnedState,
        stage: _records.CaptureStage | None,
        fields: tuple[str, ...] = (_records.DEVELOPER_COMPLETION,),
    ) -> CheckpointOutcome:
        """A record already reading as asked: what it carries in `fields` laid back, and nothing sent.

        `fields` are the capture's own by default; an answer confirming a
        handoff lays back the delivery that owns the report beside it.
        """
        self.laid_back(reading, fields)
        return CheckpointOutcome(CheckpointStatus.STANDING, stage)

    def took(self, fresh: PinnedState, landed: PinnedState, stage: _records.CaptureStage) -> CheckpointOutcome:
        """A write that landed `landed` over `fresh`: every field it moved laid back onto the caller's state."""
        self.laid_back(landed, _moved(fresh, landed))
        return CheckpointOutcome(CheckpointStatus.LANDED, stage)

    def landed(
        self, outcome: _commit_models.CommitOutcome, stage: _records.CaptureStage, fresh: PinnedState,
    ) -> CheckpointOutcome:
        """What one guarded commit over `fresh` came to, laid back where it landed and withheld where unconfirmed.

        A refusal withholds the caller too wherever the comment moved under
        the commit: any refusal but one for room says it did, and one for room
        is asked of the comment read again, so a comment simply too full still
        leaves the caller writable.
        """
        if outcome.status is _commit_models.CommitStatus.COMMITTED:
            return self.took(fresh, outcome.reading, stage)
        if outcome.status is _commit_models.CommitStatus.UNCONFIRMED:
            return self.unconfirmed()
        if outcome.refusal is _commit_models.CommitRefusal.OVERFLOW:
            return self.refused(_room.CommentOverflow(
                write=_room.MeasuredWrite.RECORD, later=_room.LaterWrites(),
                size=outcome.length or 0, limit=MAX_PINNED_BODY,
            ), reread=True)
        if outcome.refusal is _commit_models.CommitRefusal.INADMISSIBLE:
            return self.refused(outcome.inadmissible, reread=True)
        self.state.withheld = True
        return self.refused(outcome.refusal, outcome.fields)

    def unconfirmed(self) -> CheckpointOutcome:
        """A write sent and never confirmed: the caller's state withheld, and only a read-back says what landed."""
        log.warning(
            "issue=#%d a write over the completion of agent invocation %d/%s was sent and never "
            "confirmed; withholding the tick's state until it is read back",
            self.issue.number, self.invocation.ordinal, self.invocation.nonce,
        )
        self.state.withheld = True
        return CheckpointOutcome(CheckpointStatus.UNCONFIRMED)

    def refused(self, refusal: object, fields: tuple[str, ...] = (), *, reread: bool = False) -> CheckpointOutcome:
        """One refusal, said locally; nothing was written for it.

        `reread` is a refusal reached behind a request of its own -- a commit
        refused for room, a repository read -- which the comment may have
        moved during: it is read again, and a caller whose reading it no
        longer is is withheld.
        """
        if reread:
            guard = _commit_models.PinnedCommit.capture(self.state)
            reading = _pinned_commit.reread(self.gh, self.issue, guard)
            if _stale(reading, self.state):
                self.state.withheld = True
        log.warning(
            "issue=#%d a write over the completion of agent invocation %d/%s was refused as %s; writing nothing",
            self.issue.number, self.invocation.ordinal, self.invocation.nonce, getattr(refusal, "value", refusal),
        )
        return CheckpointOutcome(CheckpointStatus.REFUSED, refusal=refusal, fields=fields)

    def laid_back(self, reading: PinnedState, fields: tuple[str, ...]) -> None:
        """Lay `reading`'s `fields` onto the caller's state, as the comment's rather than its own moves."""
        for field in fields:
            if reading.carries(field):
                self.state.set(field, copy.deepcopy(reading.get(field)))
            else:
                self.state.state_data.pop(field, None)
        _pinned_commit.takes_in(self.state, reading.state_data, fields)


def _stale(reading: PinnedState | _commit_models.CommitOutcome, state: PinnedState) -> bool:
    """Whether `reading` -- the comment read afresh, or why it could not be -- is not the record `state` was read as.

    That record is the reading the state last synced with, or what it holds
    where it has none; a comment that would not be read is no proof it stands.
    """
    if isinstance(reading, _commit_models.CommitOutcome):
        return True
    read_as = state.state_data if state.synced is None else json.loads(state.synced)
    return not reading.reads_as(read_as)


def _unbound(fresh: PinnedState, invocation: AgentInvocation, issue_number: int) -> CheckpointRefusal | None:
    """Why `fresh` is no record `invocation`'s capture may be acted on over, or None.

    Another repository, issue, or comment is foreign; a cycle identity or a
    capture nobody can read is damage; another cycle is no longer the record's.
    """
    own = (issue_number, fresh.repo_slug or "", fresh.comment_id)
    if (invocation.issue, invocation.repo, invocation.comment) != own:
        return CheckpointRefusal.FOREIGN
    cycle = _invocations.cycle_of(fresh)
    damaged = _state.carries(fresh) and _state.read(fresh) is None
    if cycle is None or damaged:
        return CheckpointRefusal.DAMAGED
    return None if cycle == invocation.cycle else CheckpointRefusal.OTHER_CYCLE


def _moved(before: PinnedState, after: PinnedState) -> tuple[str, ...]:
    """Every field `after` spells otherwise than `before`, one either lacks included, sorted."""
    fields = before.state_data.keys() | after.state_data.keys()
    return tuple(sorted(
        field for field in fields
        if _commit_models.spelled(before.state_data, field) != _commit_models.spelled(after.state_data, field)
    ))
