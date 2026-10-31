# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured requirements-drift resume on `validating` the recovery admitted, with no developer run.

Two roads leave one here (`implementing/drift_road`): the body edit this
stage resumes the developer on (`drift`), and the reply it reads as the rest
of a drift resume -- over a park that edit left unanswered, or a report the
issue owes (`awaiting_resume`). Both are finished by the body edit's own
finishing helper (`drift._finish_validating_drift`), as their ticks would
have finished them, once what each settled around its run is staged from the
capture (`implementing/captured_drift.settled_resume`): the report handed to
the existing drift outcome and through it to the delivery, the size gate,
and the exact-revision publication, a report with no commit recorded for the
head the pull request carries, and the report bound and settled once the
round is written.

What tells the two apart is the round each publication spends, and the
records each froze: the body edit froze the round this stage stood down for
beside the rest (`drift_road.STOOD_DOWN`) and lands on the next round, and a
reply did not and spends what its park owes -- nothing where an `in_review`
hand-back already reset the budget for that publication, or where the owed
report's own record carries its round (`rounds._spends_for_an_owed_publication`).
Either is read off records the capture's admission held to their frozen
spellings, so the round is the one the run's own tick would have spent, and
it is counted once: by the gate's write on a hold, or by the push's, and
never by a report with no code in it.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.workflow.engine import completion_recovery_models as _recovery_models
from orchestrator.workflow.stages.implementing import (
    captured_drift as _captured_drift,
    captured_rereads as _rereads,
    drift_road as _drift_road,
)
from orchestrator.workflow.stages.validating import drift as _drift, drift_models as _drift_models, rounds as _rounds


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Finish the admitted capture on the drift road it was taken on; True, since this tick is its."""
    rebuilt = _captured_drift.settled_resume(admitted)
    capture, state = admitted.capture, admitted.state
    body_edit = _drift_road.STOOD_DOWN_FOR in dict(capture.handoff.frozen)
    run = _drift_models._ValidatingDriftRun(
        worktree=Path(capture.run.worktree),
        agent_result=rebuilt,
        before_sha=capture.run.before_sha,
        paused=False,
        delivery=_captured_drift.frozen_reading(admitted),
        spends=None if body_edit else _rounds._spends_for_an_owed_publication(state),
    )
    with _rereads.rereads(admitted):
        _drift._finish_validating_drift(admitted.gh, admitted.spec, admitted.issue, state, run)
    return True
