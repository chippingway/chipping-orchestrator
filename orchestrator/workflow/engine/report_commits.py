# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The guarded commits a developer report's delivery, binding, settlement, and retirement land through.

A report is recorded, bound, settled and retired on the strength of what the
tick read: its revision is minted past every report record the comment
carried, a superseded record's bookkeeping is carried from it, the room every
later write needs is reserved against everything else on the comment, and a
settlement or a drop is decided on the transaction, the handoff and the park it
finds. Written whole from the tick's state, that write would put back every
field another road moved since the tick read it -- an evidence record, a
verdict, a watermark -- and nothing on the comment would say so. So each write
of this domain lands through the guarded commit (`pinned_commit`) over a fresh
reading instead: the recording and the parks a refusal takes
(`report_delivery`), the binding (`report_binding`), the settlement
(`report_settling`), the reconciliation's drops and the retirement of its own
park (`report_transaction`), and the fixing recovery's release of a report no
checkout can publish (`stages/fixing/report_recovery.py`).

The reading it is guarded by is the one the tick last synced with the comment
(`PinnedState.synced`), not the state the tick holds now. A tick stages changes
of its own between two writes -- a run's usage and session, the park a reply
answered, a waiver a finished run retires -- and every one of them has always
ridden the next write. They still do: a field the tick changed since that
reading is one it owns, and it lands as the tick spells it. Beside them each
write declares the fields it owns itself and the records it was decided on
(`ReportWrite`): another writer that moved one of those records since refuses
the write, and so does one that moved a field the write changes. Every other
field is the fresh reading's. A field two roads both move by adding up or by
moving forward -- a usage total, the cost tags, a comment-id watermark, the
ledger of this orchestrator's own comments -- keeps both moves instead of
conflicting, by the validating stage's own rule for it and the ledger's own
writer; where another road left such a field as nothing that rule joins, the
move is refused as a conflict like any other field's. A binding is decided on
the publication's own pinned fields as well (`ReportWrite.on_the_publication`).

A write something depends on is held to the comment it lands on. The check
that decided it -- a record's own reading, and the room every later write
reserves -- rides the guard, so it is asked of the very candidate the commit
sends, over the reading the strict edit then lands on or nowhere: a comment
another road filled since the tick read it refuses the write here, before the
code it describes goes out or the report is posted, rather than after. A write
with an effect of its own to make first is PREPARED before it (`prepares`): a
park before its notice, with what posting that notice writes reserved, and a
settlement before its report is posted.

What lands is laid over the tick's state, so every write behind it starts from
the comment as it now stands. Anything else leaves the tick's state as it was
and withholds it (`PinnedState.withheld`): after a refusal the stage behind the
write still holds a state decided on a comment that has since moved, and after
a write sent and never confirmed nobody can say what the comment carries -- the
record may have landed, and another road may have written past it since -- so
a whole-state write of that state would put back whatever it does not know
about, and the writer writes nothing for it. Nothing may be done on the
strength of an unconfirmed write either: the caller stops the road behind it,
and a later tick settles it from what the comment then carries. A refusal for
room alone is the exception, where the comment read again is still the one the
tick synced with: that comment is simply too full, and the roads behind a
report still owed are what give its room back. A later commit that lands lifts
the mark.

A road that made requests of its own over the comment -- a report posted or
re-read -- and leaves without a write of this domain's landing asks the same
question of the comment (`withholds`): one another road wrote meanwhile
withholds the tick's state, so the stage behind never puts its whole state back
over that write, and one still reading as the tick synced with leaves the
road's own answer as it was.

The guard is not the report's alone: a validating reviewer round's launch,
return, verdict, drop, and park writes land through these same commits, each
declaring its own fields and the records it was decided on
(`stages/validating/review_writes.py`), and so do a change request's handoff,
the drop, retirement, and park of a handed one, the recovery's writes over a
verdict an earlier tick left waiting (`stages/validating/review_handoffs.py`,
`review_launch_park.py`, `review_resume.py`), and every write of an approval's
tail, its squash's own included (`stages/validating/squash_writes.py`). A
landed base rewrite's finish is declared over them too
(`rewrite_finish_writes`), which the ordinary publication of a clean rebase
lands through.
"""
from __future__ import annotations

import copy
import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from functools import partial
from typing import Any

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    pinned_commit as _commit,
    pinned_commit_models as _models,
    prompt_delivery as _prompt_delivery,
    report_record_values as _record_values,
    report_records as _records,
    stage_targets as _stage_targets,
)

# The report records every write here is decided on: a revision is minted past
# all three, a superseded one's bookkeeping is carried from it, and a binding
# drops one of them in the write that records another.
REPORT_RECORDS = frozenset((
    _records.DELIVERED_REPORT, _records.PENDING_REPORT, _records.CURRENT_REPORT,
))


# The refusals a comment's room earns, which say nothing about whether it moved.
_ROOM = frozenset((_models.CommitRefusal.OVERFLOW, _models.CommitRefusal.INADMISSIBLE))


@dataclass(frozen=True)
class ReportWrite:
    """What one write of this domain declares about itself.

    `owned` is every field it changes, besides those the tick changed;
    `decided_on` is the records its decision was taken over, which have to read
    exactly as the tick read them; `admits` is the check the fresh comment has
    to pass first, where the write has one.
    """

    owned: frozenset[str]
    decided_on: frozenset[str] = REPORT_RECORDS
    admits: _models.Admits | None = None

    def admitting(self, admits: _models.Admits) -> ReportWrite:
        """The same write, held to `admits` over the fresh comment."""
        return replace(self, admits=admits)

    def owning(self, *fields: str) -> ReportWrite:
        """The same write, owning `fields` as well."""
        return replace(self, owned=self.owned.union(fields))

    def deciding_on(self, *fields: str) -> ReportWrite:
        """The same write, decided as well on `fields`, which have to read exactly as the tick read them."""
        return replace(self, decided_on=self.decided_on.union(fields))

    def behind(self, handed: _records.HandedRun) -> ReportWrite:
        """The same write, owning what the road `handed` names retires with it, and decided on what it is decided on."""
        return self.owning(*dict(handed.retires)).deciding_on(*handed.decided_on)

    def on_the_publication(self) -> ReportWrite:
        """The same write, decided as well on the pinned fields a publication is resolved from.

        The pull request and branch the issue records, and the code-publication
        receipt -- the implementing stage's own fields, resolved when asked.
        A binding or a settlement made against the publication the tick read
        them as is never landed on a comment another road has since pointed at
        another one.
        """
        owner = importlib.import_module(_stage_targets._IMPLEMENTING_STATE_OWNER)
        publication = {
            owner._PR_NUMBER, owner._BRANCH,
            owner._PUBLISHED_SHA, owner._PUBLISHED_PR, owner._PUBLISHED_LEASE,
        }
        return replace(self, decided_on=self.decided_on | publication)


@dataclass(frozen=True)
class ReportCommit:
    """One issue, the state its tick holds, and the commits that land this domain's writes over its comment."""

    gh: GitHubClient
    issue: Issue
    state: PinnedState

    def staging(self) -> PinnedState:
        """A copy of the tick's state for one write to be staged on, the tick's own left as it is."""
        return PinnedState(
            comment_id=self.state.comment_id,
            state_data=copy.deepcopy(self.state.data),
            parsed=self.state.parsed,
        )

    def prepares(
        self, staged: PinnedState, write: ReportWrite, *, notice: bool = False, ledger_entry: bool = False,
    ) -> _models.CommitOutcome:
        """`staged` laid over the fresh comment and measured, written nowhere.

        For a write with an effect to make before its record -- a park's
        notice, a settlement's report -- that is never made for a record that
        could not follow it. `write.admits` is asked of the candidate measured,
        as it is of the one a commit sends.

        `notice` is a park's, whose notice is the one effect it makes before
        its record: posting it enters the comment in the ledger of this
        orchestrator's comments and may move the issue-thread watermark, so
        both are reserved at the widest a comment id is recorded at. The
        ledger's entry is reserved over the ledger the candidate carries -- the
        fresh comment's, with the tick's own entries merged in -- since an id
        reserved before that merge may be one another road has already recorded
        there, which the merge keeps once and the measurement then misses. A
        record that would not fit with them is one whose notice is never
        posted. A refusal withholds the tick's state, as one `lands` meets does.

        `ledger_entry` is a write behind a comment that enters the ledger and
        moves no watermark -- a notice on the pull request rather than the
        issue thread -- so only that entry is reserved, over the merged ledger
        alike.
        """
        reserved = PinnedState(
            comment_id=staged.comment_id,
            state_data=copy.deepcopy(staged.data),
            parsed=staged.parsed,
        )
        if notice:
            reserved.set(_prompt_delivery.PINNED_LAST_ACTION_COMMENT_ID, _record_values.MAX_RECORDED_NUMBER)
        guard, kept = self._guarded(reserved, write, notice=notice or ledger_entry)
        prepared = _commit.prepare(self.gh, self.issue, guard, reserved.data, kept)
        self.withholds(prepared)
        return prepared

    def lands(self, staged: PinnedState, write: ReportWrite) -> Any:
        """Land `staged` over the fresh comment: the commit's outcome, or the refusal `write.admits` gave.

        The check rides the guard, so it is asked of the candidate the commit
        sends, over the reading its edit lands on or nowhere. Only what landed
        is laid over the tick's state; anything else withholds it.
        """
        guard, kept = self._guarded(staged, write)
        landed = _commit.commit(self.gh, self.issue, guard, staged.data, kept)
        if landed.status is _models.CommitStatus.COMMITTED:
            self.state.data = copy.deepcopy(landed.reading.data)
            _commit.takes_in(self.state, landed.reading.data)
            self.state.withheld = False
        self.withholds(landed)
        if landed.refusal is _models.CommitRefusal.INADMISSIBLE:
            return landed.inadmissible
        return landed

    def withholds(self, outcome: _models.CommitOutcome | None = None) -> bool:
        """Keep the tick's state out of every whole-state write wherever the comment may have moved; whether it is.

        `outcome` is a write of this domain's that did not land over what it
        read. A refusal says the comment is not what the tick's state was
        decided on: written whole from that state, a later write would put
        back over it everything another road wrote since -- the very records
        the refusal kept -- and land the change refused. An edit sent and
        never confirmed is no better: whatever the comment reads as now,
        landed or not, another road may already have written past it, and only
        a later reading can say -- so nothing this tick holds is written over
        it either.

        A refusal for ROOM is the one that says nothing about whether the
        comment moved, so it is asked: read again, a comment that is still the
        one the tick synced with is a comment simply too full, and the tick's
        state may still be written over it -- the roads behind a report still
        owed are what give that room back. One that moved, or will not read,
        is withheld like any other.

        Asked with no outcome by a road whose own requests ran over the
        comment and that leaves without a write of this domain's landing -- a
        report posted or re-read, and its settlement never reached: a post or
        a re-read is long enough for another road to write the comment, and
        the stage behind would put its whole state back over what that road
        wrote. Asked as a refusal for room is. A state already withheld stays
        so; only a commit that lands lifts it.
        """
        if outcome is not None and outcome.status not in {
            _models.CommitStatus.REFUSED, _models.CommitStatus.UNCONFIRMED,
        }:
            return self.state.withheld
        if not self.state.withheld and (outcome is None or outcome.refusal in _ROOM):
            synced = (
                self.state.data if self.state.synced is None
                else json.loads(self.state.synced)
            )
            reading = PinnedState(
                comment_id=self.state.comment_id, state_data=synced, parsed=self.state.parsed,
            )
            fresh = _commit.reread(self.gh, self.issue, _models.PinnedCommit.capture(reading))
            if isinstance(fresh, PinnedState) and fresh.reads_as(synced):
                return False
        self.state.withheld = True
        return True

    def _guarded(
        self, staged: PinnedState, write: ReportWrite, *, notice: bool = False,
    ) -> tuple[_models.PinnedCommit, Mapping[str, _models.Transform]]:
        """The guard `staged` is committed under, and the fields whose two moves it keeps.

        A state nothing was read into stands for its own reading, so on it
        the tick has staged nothing of its own. `notice` is the preparation of
        a write behind a notice, which reserves the ledger entry posting it adds.
        """
        synced = (
            self.state.data if self.state.synced is None
            else json.loads(self.state.synced)
        )
        kept = self._kept(self._moved(synced, staged.data), notice=notice)
        ticked = self._moved(synced, self.state.data)
        guard = _models.PinnedCommit.capture(
            PinnedState(
                comment_id=self.state.comment_id,
                state_data=synced,
                parsed=self.state.parsed,
            ),
            prerequisites=write.decided_on,
            owned={*write.owned, *ticked, *kept},
            admits=write.admits,
        )
        return guard, kept

    def _kept(self, moved: set[str], *, notice: bool = False) -> dict[str, _models.Transform]:
        """The transformation keeping both moves of each field in `moved` that has one.

        A notice's preparation derives the ledger whether or not the tick moved
        it, since the entry it reserves is laid over the fresh ledger.
        """
        both = importlib.import_module(_stage_targets._VALIDATING_STATE_OWNER)._BOTH_MOVES
        kept: dict[str, _models.Transform] = {
            field: partial(_both_moves, field) for field in moved if field in both
        }
        if notice or _comments._ORCH_COMMENT_IDS in moved:
            kept[_comments._ORCH_COMMENT_IDS] = partial(_merged_ledger, reserving=notice)
        return kept

    def _moved(
        self, before: Mapping[str, Any], after: Mapping[str, Any],
    ) -> set[str]:
        """Every field `after` spells otherwise than `before`, one that either lacks included."""
        fields = before.keys() | after.keys()
        return {
            field for field in fields
            if _models.spelled(before, field) != _models.spelled(after, field)
        }


def _both_moves(field: str, fresh: Any, read: Any, staged: Any) -> Any:
    """One field this write moved, beside where another road moved it, as the validating stage keeps both.

    Where that rule cannot join the two -- a value spelled as no writer of the
    field spells it -- the field is decided as any field one road alone owns
    is (`_unkept`).
    """
    kept = PinnedState(state_data=_present(field, staged))
    joined = importlib.import_module(_stage_targets._VALIDATING_STATE_OWNER)._keeps_both_moves(
        kept, field, _present(field, fresh), _present(field, read),
    )
    if not joined:
        return _unkept(fresh, read, staged)
    return kept.data.get(field, _models.ABSENT)


def _unkept(fresh: Any, read: Any, staged: Any) -> Any:
    """A move no rule joins with another road's: the write's own, unless another road moved the field elsewhere.

    The write's value stands where the fresh reading still spells the field
    as it was captured, or already as the write staged it; anything else is
    another road's move the write would otherwise put its own value back over,
    and is a conflict the commit refuses.
    """
    standing = {_models.spelling(read), _models.spelling(staged)}
    if _models.spelling(fresh) in standing:
        return staged
    return _models.CONFLICT


def _merged_ledger(fresh: Any, read: Any, staged: Any, *, reserving: bool = False) -> Any:
    """The ledger of this orchestrator's comments, with what this write added kept beside the fresh one.

    A set every road adds to, so it is merged rather than either side's taken
    whole, through the ledger's own writer -- each id once, within its bound.
    An entry naming no comment is nobody's post, on either side, and is dropped.
    A fresh reading that is no ledger at all joins nothing, and is decided as
    a field one road alone owns is (`_unkept`).

    `reserving` is a notice's preparation: the entry posting it will add is
    reserved on the merged ledger, at the widest a comment id is recorded at,
    under an id that ledger does not already hold (`_reserve_comment_slot`).
    """
    if fresh is not _models.ABSENT and not isinstance(fresh, list):
        ledger = _unkept(fresh, read, staged)
    else:
        known = set(_whole(read))
        merged = PinnedState(state_data={_comments._ORCH_COMMENT_IDS: _whole(fresh)})
        _comments._track_orchestrator_comment(merged, *(
            entry for entry in _whole(staged) if entry not in known
        ))
        ledger = merged.get(_comments._ORCH_COMMENT_IDS)
    if not reserving or ledger is _models.CONFLICT:
        return ledger
    reserved = PinnedState(state_data=_present(_comments._ORCH_COMMENT_IDS, ledger))
    _comments._reserve_comment_slot(reserved, _record_values.MAX_RECORDED_NUMBER)
    return reserved.get(_comments._ORCH_COMMENT_IDS)


def _present(field: str, field_value: Any) -> dict:
    """A record carrying `field` as `field_value`, or carrying nothing for ABSENT."""
    if field_value is _models.ABSENT:
        return {}
    return {field: field_value}


def _whole(ledger: Any) -> list[int]:
    """The entries of one ledger reading that name a comment, in its order."""
    if not isinstance(ledger, list):
        return []
    is_whole = importlib.import_module(_stage_targets._VALIDATING_STATE_OWNER)._is_whole
    return [entry for entry in ledger if is_whole(entry)]
