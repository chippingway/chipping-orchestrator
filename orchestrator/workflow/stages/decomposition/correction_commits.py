# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What one write over a decomposer manifest correction is bound to, and what it can come to.

Every write over the attempt -- its arming, its exhaustion, its retirement --
and its read-back is asked over the pinned comment the caller holds, read
afresh and admitted again (`pinned_commit.reread`): unreadable, unparsed,
unsupported, deleted, or replaced, it is refused with the guarded commit's own
reason and nothing is sent. A write is bound to the source invocation of the
attempt it is about, which has to name that comment, its repository, and its
issue, and the workflow cycle the comment is on; a cycle identity or a claim
no reader can name is damage, refused rather than taken for an absence, and a
claim the field holds damaged is never replaced, cleared, or acted on here.

Each write owns `decomposer_correction` and nothing else, so it moves no
session pin, requirements baseline, park, counter, or run charge, whatever the
caller staged; every other field, unknown ones included, is the fresh
reading's. Each is decided on the field and the cycle, and on what its
caller names beside them, so a reading that moved under it refuses it.

Each answer is one of four, as the guarded commit's are. LANDED is a write
this call landed and STANDING a record that already read as asked -- a
read-back's answer, and every repeat's -- so nothing was sent. UNCONFIRMED went
out and was never confirmed: the record may read either way, and only a
read-back says which. REFUSED wrote nothing and says why. Only the first two
settle anything, and each carries what the comment it settled on says of the
attempt (`correction_standing.read`).

What a write landed, or a read-back found, is laid back onto the caller's
state as the comment's (`pinned_commit.takes_in`), so the caller's own
whole-state write keeps it rather than putting back a record without it -- a
spent attempt armed again. A write sent and never confirmed withholds the
caller's state from every whole-state write instead, since that write would
put back the record as it read before, over an attempt that may have moved.
So does every answer given over a comment that no longer reads as the one the
caller read, or that would not be read at all, and a write that landed over a
comment another road or a human moved after it was read: the commit keeps
that move, and the caller, which does not hold it, would write it away.
"""
from __future__ import annotations

import copy
import dataclasses
import enum
import logging

from github.Issue import Issue

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_commits as _completion_commits,
    invocations as _invocations,
    pinned_commit as _pinned_commit,
    pinned_commit_models as _commit_models,
)
from orchestrator.workflow.late_split import keys as _late_keys
from orchestrator.workflow.stages.decomposition import (
    correction_records as _records,
    correction_standing as _standing,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")

_FIELD = _state._DECOMPOSER_CORRECTION

# What every write over an attempt is decided on: the attempt itself, and the
# workflow cycle its source is bound to.
DECIDED_ON = (_FIELD, _late_keys.CYCLE_ID)

# The commit refusals that say only that the comment had no room.
_NO_ROOM = frozenset((_commit_models.CommitRefusal.OVERFLOW, _commit_models.CommitRefusal.INADMISSIBLE))


class CorrectionStatus(enum.Enum):
    """What one write over an attempt, or its read-back, came to."""

    LANDED = "landed"
    STANDING = "standing"
    UNCONFIRMED = "unconfirmed"
    REFUSED = "refused"


class CorrectionRefusal(enum.Enum):
    """Why a write over an attempt was refused before its commit was asked; a refused commit names its own reason."""

    # The source invocation names another repository, issue, or pinned comment.
    FOREIGN = "foreign"
    # The source ran in a workflow cycle the record is no longer on.
    OTHER_CYCLE = "other_cycle"
    # The attempt or the cycle identity reads as nothing this build writes.
    DAMAGED = "damaged"
    # The attempt the record carries names another record or cycle.
    DISPLACED = "displaced"
    # Another source's attempt is still pending.
    UNRESOLVED = "unresolved"
    # The source is covered by a resolved attempt, or another charge -- or an
    # owed start -- followed it on the record.
    SUPERSEDED = "superseded"
    # The record carries no attempt of this source.
    ABSENT = "absent"
    # The attempt already resolved otherwise than asked.
    RESOLVED = "resolved"
    # The record's requirements baseline or decomposer pins are not the ones
    # the source names.
    UNSAVED = "unsaved"
    # The attempt a write would land would not read back as itself: a member
    # past its bound -- a source, a correction, or a floor no record holds.
    UNRECORDABLE = "unrecordable"
    # The correction named is not one charged after the source on its record.
    UNRELATED = "unrelated"
    # A retirement asked of a reading that proves no move of its context.
    NO_EVIDENCE = "no_evidence"
    # A resolution asked of a reading whose run ledger count, or the usage
    # meter beside it, reads as no count, or as one below a charge the owed
    # start or a usage receipt records: no floor could be shown to cover every
    # charge taken.
    UNCOUNTED = "uncounted"
    # The comment has no room for the write, or for the attempt's widest resolution.
    NO_ROOM = "no_room"


# Why a write wrote nothing: this domain's reason, or the guarded commit's.
_Refusal = CorrectionRefusal | _commit_models.CommitRefusal


@dataclasses.dataclass(frozen=True)
class CorrectionOutcome:
    """One answer: its status, what the comment it was given over says, and for a refusal why and the fields it named.

    `reading` is what that comment says of the attempt it carries -- the one a
    write landed on or a read-back found, or the one a refusal was decided over
    -- and None where no reading was taken. Of a refusal it is that comment's
    own attempt, whichever source it names (`reading.attempt`), never a grant
    to the write that was refused: `status` decides.
    """

    status: CorrectionStatus
    reading: _standing.CorrectionReading | None = None
    refusal: _Refusal | None = None
    fields: tuple[str, ...] = ()

    @property
    def settled(self) -> bool:
        """Whether the record durably reads as `reading` says: the only answers dependent work may follow."""
        return self.status in {CorrectionStatus.LANDED, CorrectionStatus.STANDING}


@dataclasses.dataclass(frozen=True)
class CorrectionCommit:
    """The issue a write is on, the caller state it is laid back onto, and the source it is bound to, if any."""

    gh: GitHubClient
    issue: Issue
    state: PinnedState
    source: AgentInvocation | None = None

    def fresh(self) -> PinnedState | CorrectionOutcome:
        """The caller's comment read afresh and admitted, bound to the source; or why it cannot be acted on.

        A comment that no longer reads as the one the caller read withholds
        the caller's state, whatever is answered over it.
        """
        guard = _commit_models.PinnedCommit.capture(self.state)
        fresh = _pinned_commit.reread(self.gh, self.issue, guard)
        if _completion_commits._stale(fresh, self.state):
            self.state.withheld = True
        if isinstance(fresh, _commit_models.CommitOutcome):
            return self.refused(fresh.refusal)
        unbound = self._unbound(fresh)
        return fresh if unbound is None else self.refused(unbound, fresh)

    def standing(self, reading: PinnedState) -> CorrectionOutcome:
        """A record already reading as asked: the attempt field laid back, and nothing sent."""
        self._laid_back(reading)
        return CorrectionOutcome(CorrectionStatus.STANDING, _standing.read(reading, self.issue.number))

    def lands(
        self,
        fresh: PinnedState,
        attempt: _records.CorrectionAttempt,
        decided_on: tuple[str, ...],
        admits: _commit_models.Admits | None = None,
    ) -> CorrectionOutcome:
        """Commit `attempt` as the record's over `fresh`, owning that field alone, decided on `decided_on` too.

        Only an attempt that reads back as itself is sent: a write that landed
        a record its own reader refuses would leave a damaged claim where an
        attempt stood, whatever answer it gave.
        """
        if not attempt.recordable():
            return self.refused(CorrectionRefusal.UNRECORDABLE, fresh)
        guard = _commit_models.PinnedCommit.capture(
            fresh, prerequisites=(*DECIDED_ON, *decided_on), owned=(_FIELD,), admits=admits,
        )
        staged = {**fresh.state_data, _FIELD: attempt.spelled()}
        landed = _pinned_commit.commit(self.gh, self.issue, guard, staged)
        if landed.status is _commit_models.CommitStatus.COMMITTED:
            # Classified over the fresh reading carrying what landed: the
            # commit's own reading names the comment and nothing of the
            # repository its source is bound to.
            carried = dataclasses.replace(fresh, state_data=landed.reading.state_data)
            self._withholds_behind(fresh, carried)
            self._laid_back(carried)
            return CorrectionOutcome(CorrectionStatus.LANDED, _standing.read(carried, self.issue.number))
        if landed.status is _commit_models.CommitStatus.UNCONFIRMED:
            log.warning(
                "issue=#%d a write of its manifest correction at %s was sent and never confirmed; "
                "withholding the tick's state until it is read back", self.issue.number, attempt.stage.value,
            )
            self.state.withheld = True
            return CorrectionOutcome(CorrectionStatus.UNCONFIRMED)
        if landed.refusal in _NO_ROOM:
            return self.refused(CorrectionRefusal.NO_ROOM, fresh, reread=True)
        self.state.withheld = True
        return self.refused(landed.refusal, fresh, fields=landed.fields)

    def refused(
        self,
        refusal: _Refusal | None,
        over: PinnedState | None = None,
        *,
        fields: tuple[str, ...] = (),
        reread: bool = False,
    ) -> CorrectionOutcome:
        """One refusal, said locally; nothing was written for it.

        `over` is the reading it was decided over, where one was taken, which
        the answer carries what it says of. `reread` is a refusal the commit
        reached over a reading of its own, which the comment may have moved
        before: it is read again, and a caller whose reading it no longer is
        is withheld.
        """
        if reread:
            guard = _commit_models.PinnedCommit.capture(self.state)
            if _completion_commits._stale(_pinned_commit.reread(self.gh, self.issue, guard), self.state):
                self.state.withheld = True
        log.warning(
            "issue=#%d a write of its manifest correction was refused as %s; writing nothing",
            self.issue.number, getattr(refusal, "value", refusal),
        )
        reading = None if over is None else _standing.read(over, self.issue.number)
        return CorrectionOutcome(CorrectionStatus.REFUSED, reading, refusal, fields)

    def _unbound(self, fresh: PinnedState) -> CorrectionRefusal | None:
        """Why `fresh` is no record the source's attempt may be written over, or None; a read-back is bound to none."""
        if self.source is None:
            return None
        own = (self.issue.number, fresh.repo_slug or "", fresh.comment_id)
        if (self.source.issue, self.source.repo, self.source.comment) != own:
            return CorrectionRefusal.FOREIGN
        cycle = _invocations.cycle_of(fresh)
        damaged = _records.carries(fresh) and _records.read(fresh) is None
        if cycle is None or damaged:
            return CorrectionRefusal.DAMAGED
        return None if cycle == self.source.cycle else CorrectionRefusal.OTHER_CYCLE

    def _withholds_behind(self, fresh: PinnedState, landed: PinnedState) -> None:
        """Withhold the caller where the comment `landed` on moved beyond this write since it was read as `fresh`.

        The commit reads the comment again behind `fresh` and keeps whatever
        another road or a human wrote there meanwhile, which the caller -- read
        no later than `fresh` -- does not hold: its whole-state write would put
        that back as it read it.
        """
        if set(_completion_commits._moved(fresh, landed)).difference((_FIELD,)):
            self.state.withheld = True

    def _laid_back(self, reading: PinnedState) -> None:
        """Lay `reading`'s attempt field onto the caller's state, as the comment's rather than its own move."""
        if reading.carries(_FIELD):
            self.state.set(_FIELD, copy.deepcopy(reading.get(_FIELD)))
        else:
            self.state.state_data.pop(_FIELD, None)
        _pinned_commit.takes_in(self.state, reading.state_data, (_FIELD,))
