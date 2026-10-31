# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured requirements-drift resume on `resolving_conflict` the recovery admitted, with no developer run.

Two of this stage's resumes leave one here (`implementing/drift_road`): the
body edit that lands while the pull request is being rebased, and the reply
that answers a park that edit's resume left owing a report -- both the rest
of one drift resume, and both resumed on its frozen drift prompt (`resume`).
Each is finished by the road both share (`resume_reports._disposes`), as its
own tick would have finished it, once what that tick settled around the run
is staged from the capture (`implementing/captured_drift.settled_resume`):
the report through the existing drift outcome into the delivery, recorded
beside the publication its push owes (`resume_records`), the commit through
the size gate and the leased force-push, and a pushed round counted and
handed to `validating` through the tail every pushed round shares, the report
bound behind it; a report with no commit goes onto the head the pull request
carries and leaves the issue here, as an `ACK:` would.

The lease is the one the run's caller proved, which its road froze as the
head the run began on: the head a body edit's resume started from in sync
with its remote, or the pull request's own head ahead of a reply's run. The
admission held the pull request to that head or the commit reported on, so
the publication is leased against that exact head, and a pull request
somebody moved since refuses the push rather than being adopted. A run that
left the rebase mid-flight parks as the resolution funnel parks it, its
capture withdrawn first. The ordinary conflict resolution freezes no road, so
nothing of it is replayed.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.workflow.engine import completion_recovery_models as _recovery_models
from orchestrator.workflow.stages.conflicts import models as _models, resume_reports as _resume_reports
from orchestrator.workflow.stages.implementing import captured_drift as _captured_drift, captured_rereads as _rereads


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Finish the admitted capture on the road its resume shares; True, since this tick is its."""
    rebuilt = _captured_drift.settled_resume(admitted)
    capture = admitted.capture
    lease = capture.run.before_sha
    with _rereads.rereads(admitted):
        _resume_reports._disposes(
            _models._ConflictContext(admitted.gh, admitted.spec, admitted.issue, admitted.state),
            _models._ConflictResumeRun(worktree=Path(capture.run.worktree), dev_result=rebuilt, paused=False),
            lease,
            capture.handoff.requirements_revision,
            lease,
        )
    return True
