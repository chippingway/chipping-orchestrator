# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The outcome, reason, and retained evidence from acting on a maintenance candidate.

Discovery supplies the candidate, and eligibility supplies retention evidence.
The pass records these closed outcome and reason values after its guarded
teardown steps; analytics reads the same records without repeating any probes.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from orchestrator.git.worktrees import (
    candidates as _candidates,
    models as _models,
)
from orchestrator.git.worktrees.models import Retention


class MaintenanceOutcome(StrEnum):
    """What one maintenance pass over one candidate did.

    Three answers, because a caller counting them has to keep apart the two
    ways a candidate survives a pass. `RETAINED` is the pass deciding not to
    touch it -- every gate in front of the mutation is a decision of that kind,
    and one repeating every pass is a candidate somebody has to settle by hand.
    `FAILED` is the pass trying and being refused: git would not remove the
    checkout, the remote would not accept the delete. Collapsed together, an
    operator could not tell a host that is behaving from one that is not.

    `CLEANED` is every artifact this candidate was found holding now gone from
    the host and the remote, absences included: a pass that found a branch
    already deleted has nothing left to do about it, and reporting that as
    anything but done would keep the candidate reported forever.
    """

    CLEANED = "cleaned"
    RETAINED = "retained"
    FAILED = "failed"


class MaintenanceReason(StrEnum):
    """Why one maintenance pass ended where it did.

    Closed, and each member is fixed to exactly one outcome, so the two fields
    of a result cannot disagree: what an outcome counts, the reason explains.

    `UNPROVEN` is the classification keeping the candidate, and it is one
    member rather than a copy of `RetentionReason` because the result carries
    those retentions themselves -- an operator reads which artifact and which
    question off them, in the vocabulary they were already spelled in.

    The two tip members are the pass's own last reading, taken after everything
    else cleared and immediately before the mutation. `TIP_MOVED` is an
    artifact that has left the commit the classification proved -- an agent
    committed, a human pushed -- which is not a failure but a race the next
    pass re-runs from the start. `TIP_UNREADABLE` is that reading not coming
    back at all.

    `BRANCH_CHECKED_OUT` is the one reason about a tree this candidate does
    not own. Some worktree of the clone is still standing on the branch --
    an operator's own, or one this scan could not attribute -- and the
    plumbing delete would take the ref without a word and leave that tree
    holding a HEAD nothing resolves.

    The three failures name the step that would not run, because that is what
    separates the operator's next move: a checkout git refuses to remove is a
    tree on this host, a remote delete refused is a token or a branch
    protection rule, and a local ref that would not go is a clone somebody
    else is holding.
    """

    RECLAIMED = "reclaimed"
    UNPROVEN = "unproven"
    RECENT_ACTIVITY = "recent_activity"
    ACTIVITY_UNREADABLE = "activity_unreadable"
    ACTIVE_CLAIM = "active_claim"
    CLAIM_UNREADABLE = "claim_unreadable"
    TIP_MOVED = "tip_moved"
    TIP_UNREADABLE = "tip_unreadable"
    BRANCH_CHECKED_OUT = "branch_checked_out"
    WORKTREE_REMOVAL_FAILED = "worktree_removal_failed"
    REMOTE_DELETE_FAILED = "remote_delete_failed"
    LOCAL_DELETE_FAILED = "local_delete_failed"


@dataclass(frozen=True)
class MaintenanceResult:
    """What one pass over one candidate decided, and what it is about.

    One record per candidate rather than one per artifact, because a pass that
    stops stops for the whole candidate: whatever is still standing when it
    ends is left where it is, and the discovery that found it once finds it
    again. Nothing here is a retry list, which is what lets an interrupted pass
    cost nothing to resume.

    `subject` names the artifact the reason is about -- a branch by name, a
    checkout by path -- spelled the way a retention's and a proven tip's are,
    and empty where the reason is about the candidate as a whole. `retentions`
    is the classification's own answer, carried only where it is what kept the
    candidate: a pass that cleared it has nothing to report there, and a
    retention beside a reclaimed candidate would read as a permission nothing
    gave.
    """

    candidate: _candidates.MaintenanceCandidate
    outcome: MaintenanceOutcome
    reason: MaintenanceReason
    subject: str = ""
    retentions: tuple[Retention, ...] = ()

# Which outcome each reason is, fixed here so the two fields of a result
# cannot disagree. A retention is the pass declining to act, a failure is a
# step that ran and was refused, and the one reason that cleans is the one
# that reached the end of the teardown.
_OUTCOMES = MappingProxyType({
    MaintenanceReason.RECLAIMED: MaintenanceOutcome.CLEANED,
    MaintenanceReason.UNPROVEN: MaintenanceOutcome.RETAINED,
    MaintenanceReason.RECENT_ACTIVITY: MaintenanceOutcome.RETAINED,
    MaintenanceReason.ACTIVITY_UNREADABLE: MaintenanceOutcome.RETAINED,
    MaintenanceReason.ACTIVE_CLAIM: MaintenanceOutcome.RETAINED,
    MaintenanceReason.CLAIM_UNREADABLE: MaintenanceOutcome.RETAINED,
    MaintenanceReason.TIP_MOVED: MaintenanceOutcome.RETAINED,
    MaintenanceReason.TIP_UNREADABLE: MaintenanceOutcome.RETAINED,
    MaintenanceReason.BRANCH_CHECKED_OUT: MaintenanceOutcome.RETAINED,
    MaintenanceReason.WORKTREE_REMOVAL_FAILED: MaintenanceOutcome.FAILED,
    MaintenanceReason.REMOTE_DELETE_FAILED: MaintenanceOutcome.FAILED,
    MaintenanceReason.LOCAL_DELETE_FAILED: MaintenanceOutcome.FAILED,
})


def _answered(
    candidate: _candidates.MaintenanceCandidate,
    reason: MaintenanceReason,
    subject: str = "",
    retentions: tuple[_models.Retention, ...] = (),
) -> MaintenanceResult:
    """One candidate's answer, with the outcome its reason fixes."""
    return MaintenanceResult(
        candidate=candidate,
        outcome=_OUTCOMES[reason],
        reason=reason,
        subject=subject,
        retentions=retentions,
    )
