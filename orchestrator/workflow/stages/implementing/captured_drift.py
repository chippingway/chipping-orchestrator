# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finish a captured requirements-drift resume the dispatcher's recovery admitted, with no developer run.

The recovery hands an applicable capture on the drift road
(`completion_recovery.DRIFT_OWNERS`) to the owner of the stage it reported
under: this one for `implementing`, and `validating/captured_drift`,
`in_review/captured_drift`, and `conflicts/captured_drift` for the others.
Every one of them first stages what the resume's own tick settled around its
run (`settled_resume`), from the capture alone and never from a second reading
of the thread: the command that ran pinned and the conversation settled as
that run's would be (`captured_completion`), so a resumed one is charged one
resume and a retired one never restored; the park the resume answered taken
down, as every resume takes its flag down; the watermarks its road froze
advanced forward only -- the frozen reading's own settlement, which records
the requirements the run was handed as the baseline, and the commands a retry
consumed -- so nothing later on the thread reads as delivered; and the agent
action stamped. Each then answers the run on the stage's existing drift
disposition, handed a result rebuilt from the capture -- its outcome, the
session it returned, the invocation it came from, no usage of its own -- and
the frozen reading reduced to the revision the run was handed
(`frozen_reading`), whose settlement moves nothing those watermarks have not
already. The report goes through the existing drift outcome, report delivery,
size gate, and exact-revision, leased publication, its capture handed off in
the commit that records it with everything staged here riding that commit;
each stage keeps its own accounting.

Here that is implementing's: the branch stamped, a commit the run made or the
branch already carried for an owed report published and handed to review
through the stage's own publication, and a report with no commit to carry it
parked as the question it reads as on this road, its capture withdrawn first.
A report this road would publish under no commit -- one the issue already
owes -- goes out under the commits the branch carries, as its own tick's
would. No developer is launched, no run charged, and no review, verification,
approval, or documentation pass inferred.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import (
    completion_recovery_models as _recovery_models,
    prompt_delivery as _prompt_delivery,
    report_consumed_values as _consumed,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    captured_completion as _captured_completion,
    drift_disposition as _drift_disposition,
    state as _state,
)
from orchestrator.workflow.stages.implementing.drift_models import _ImplementingDriftRun

log = logging.getLogger("orchestrator.workflow")

_LAST_AGENT_ACTION = "last_agent_action_at"


def recovers(admitted: _recovery_models.AdmittedCompletion) -> bool:
    """Answer an admitted implementing drift capture on the stage's own disposition; True, since this tick is its."""
    rebuilt = settled_resume(admitted)
    capture, state = admitted.capture, admitted.state
    run = capture.run
    state.set(_state._BRANCH, run.branch)
    drift = _ImplementingDriftRun(
        worktree=Path(run.worktree),
        agent_result=rebuilt,
        before_sha=run.before_sha,
        paused=False,
        committed=run.source_sha != run.before_sha,
        delivery=frozen_reading(admitted),
    )
    _drift_disposition._dispose_implementing_drift(admitted.gh, admitted.spec, admitted.issue, state, drift)
    return True


def settled_resume(admitted: _recovery_models.AdmittedCompletion) -> AgentResult:
    """Stage what the drift resume's own tick settled around its run, from the capture alone; the result rebuilt.

    Staged on the admitted reading, for the disposition behind it: the
    session as the run's own tick would have settled it, the park flag the
    resume takes down, the watermarks its road froze, and the agent action.
    """
    capture, state = admitted.capture, admitted.state
    rebuilt = _captured_completion._rebuilt_result(capture)
    log.info(
        "issue=#%d finishing the captured drift resume of agent invocation %d/%s on %r; no developer "
        "is launched for it",
        admitted.issue.number, capture.invocation.ordinal, capture.invocation.nonce, capture.handoff.origin,
    )
    _captured_completion._settles_the_session(state, capture, rebuilt)
    state.set(_state._AWAITING_HUMAN, False)
    _consumed.advance_consumed(state, capture.handoff.watermarks)
    state.set(_LAST_AGENT_ACTION, _usage._now_iso())
    return rebuilt


def frozen_reading(admitted: _recovery_models.AdmittedCompletion) -> _prompt_delivery.PromptDeliverySnapshot:
    """The frozen reading the run was handed, reduced to its requirements revision, as each disposition reads it.

    It names no comment, so its settlement records that revision as the
    baseline and moves no watermark, and the carry a disposition takes over
    it vouches for no comment the capture did not keep.
    """
    return _prompt_delivery.create_prompt_delivery_snapshot(
        entries=(),
        requirements_revision=admitted.capture.handoff.requirements_revision,
        rendered_text="",
        state=admitted.state,
    )
