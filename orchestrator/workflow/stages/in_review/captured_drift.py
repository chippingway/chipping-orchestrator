# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured requirements-drift resume on `in_review` the recovery admitted, with no developer run.

A body edit on an approved pull request resumes the developer on its own road
(`drift`), launched on the drift road (`implementing/drift_road`), and a
return a live hold, a lost write, or a restart kept from its disposition is
handed here. It is finished by that very disposition (`drift._dispose_drift_result`)
once what its tick settled around the run is staged from the capture
(`implementing/captured_drift.settled_resume`), beside the move to
`validating` the edit owes -- the marker its tick stages with the refreshed
requirements before the run, so no write may make the baseline durable
without it. The report then goes through the existing drift outcome, the
delivery, the size gate, and the exact-revision publication; a pushed fix,
an `ACK:`, and a report with no commit hand the issue back to `validating`
with `review_round` reset, the round accounting this stage keeps, and a park
leaves that move owed for `validating`'s reply road.

The disposition needs the pull request it reads, and the carry of the shared
IssueComment cursor ahead of the report re-reads both surfaces, each a request
of its own behind the admission's readings. So this owner fetches the pull
request and runs the disposition inside `captured_rereads.rereads`: every
reading a handoff's effect stands on is taken again immediately before the
report is handed on, behind all of those requests, and a control applied, a
label moved, a close, an edit, a checkout moved, or a push meanwhile holds the
capture with nothing written, for the next dispatch to decide afresh. A pull
request that would not read holds it too.

What the run's prompt delivered is settled as the capture froze it -- the
issue thread's half of the reading, as this road settles it -- and the carry
of the shared IssueComment cursor behind it crosses only this orchestrator's
own posts and the delivered stretch: the capture keeps no record of which
pull-request comments that prompt quoted, so those stay above the cursor for
the next scan, delivered twice rather than marked read by nothing.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.workflow.engine import completion_recovery_models as _recovery_models
from orchestrator.workflow.stages.implementing import captured_drift as _captured_drift, captured_rereads as _rereads
from orchestrator.workflow.stages.in_review import drift as _drift, models as _models, state as _state

log = logging.getLogger("orchestrator.workflow")

_PR_NUMBER = "pr_number"


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Finish the admitted capture through the stage's drift disposition; True, since this tick is its."""
    context = _context(admitted)
    if context is None:
        return True
    rebuilt = _captured_drift.settled_resume(admitted)
    context.state.set(_state._HANDOFF_PENDING, True)
    run = admitted.capture.run
    with _rereads.rereads(admitted):
        _drift._dispose_drift_result(context, _models._DriftResume(
            worktree=Path(run.worktree),
            dev_result=rebuilt,
            paused=False,
            before_sha=run.before_sha,
            delivery=_captured_drift.frozen_reading(admitted),
        ))
    return True


def _context(admitted: _recovery_models.AdmittedCompletion) -> _models._InReviewContext | None:
    """The in_review tick's handles over the admitted reading, its pull request fetched; None where none read."""
    number = int(admitted.state.get(_PR_NUMBER))
    try:
        pull_request = admitted.gh.get_pr(number)
    except Exception:  # noqa: BLE001 - a pull request nobody could fetch holds the capture, never invalidates it
        log.warning(
            "issue=#%d could not fetch the pull request its captured drift resume is finished on; holding the tick",
            admitted.issue.number,
        )
        return None
    return _models._InReviewContext(admitted.gh, admitted.spec, admitted.issue, admitted.state, pull_request, number)
