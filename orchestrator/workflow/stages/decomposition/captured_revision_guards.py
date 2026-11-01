# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a captured late revision's recovery asks before each write behind its reads, and how it lands them.

The recovery's reconciliation lands the capture's transfer, a park, and its
withdrawal through guarded commits of its own (`late_revision_landing`). What
follows them is the late coordinator's owner read (`late_owner._guarded_owner`):
the claim it writes where the commit did not already carry it, the settlement
of that claim, and the persists behind the notices it releases. Each of those
is a whole-state write of the tick's state, and written whole it would put
back over the comment everything another road or a human recorded since the
recovery last read it -- a split child the issue now owes among them -- while
asking no question of its own, so a control applied as it walks to the
comment would not stop it either.

So the recovery hands the late coordinator a client whose whole-state writes
of this issue's comment land through the guarded commit instead
(`report_commits.ReportCommit`): owning what the tick moved, and decided on
every record the capture's handoff was frozen over as the tick last read
them. Another writer's move of one refuses the write and withholds the state,
so nothing the tick holds is written over it -- an owner read still claimed
stays owed, for a later tick to take over the comment as it then reads -- and
the strict edit the commit lands through asks the recovery's question behind
its own walk (`implementing/captured_rereads`). A state already withheld is
written nowhere, as the whole-state writer writes none, and every other
request passes through.

Beside that client the recovery hands the late coordinator a question of its
own: the owner read asks of the issue it fetches whether a control or a
relabel holds it (`holds`), so nothing the read decides is written or said
over one. Whether the issue was closed for the revision's cycle is the other
question every strict edit asks, last, and its own owner's
(`captured_revision_closes`).
"""
from __future__ import annotations

from orchestrator.github import labels as _labels
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import completion_recovery_models as _recovery_models, report_commits as _commits


class _CommitsItsWrites:
    """`gh` for one recovery of one issue: every call passed through, each whole-state write of its comment guarded."""

    def __init__(self, gh: GitHubClient, issue_number: int, write: _commits.ReportWrite) -> None:
        self._gh = gh
        self._issue_number = issue_number
        self._write = write

    def __getattr__(self, name: str):
        return getattr(self._gh, name)

    def write_pinned_state(self, issue, state: PinnedState) -> PinnedState:
        """Land `state` through a guarded commit; a withheld state, or another issue's comment, as the client would."""
        if issue.number != self._issue_number or state.withheld:
            return self._gh.write_pinned_state(issue, state)
        commit = _commits.ReportCommit(self._gh, issue, state)
        commit.lands(commit.staging(), self._write)
        return state


def committing(admitted: _recovery_models.AdmittedCompletion) -> _CommitsItsWrites:
    """`admitted`'s client, each whole-state write of its issue's comment decided on the capture's frozen records."""
    frozen = frozenset(dict(admitted.capture.handoff.frozen))
    return _CommitsItsWrites(
        admitted.gh, admitted.issue.number, _commits.ReportWrite(frozenset(), decided_on=frozen),
    )


def holds(admitted: _recovery_models.AdmittedCompletion, owner) -> bool:
    """Whether the issue an owner read fetched as `owner` carries a control, or another label than was admitted."""
    if _labels.hard_skip_control_label(owner) is not None:
        return True
    return admitted.gh.workflow_label(owner) != admitted.label
