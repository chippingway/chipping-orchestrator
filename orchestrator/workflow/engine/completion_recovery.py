# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Decide, ahead of every stage handler, what a pending captured completion is owed.

A captured completion (`developer_completion`) is a developer run's report
kept past a return that could not deliver it, and the stage the issue is on
is the one road that would lose or repeat that work: an implementing tick
reads the commit as an unreported checkout, a drift check resumes the
developer over it, a launch runs the developer again, and a review resume
drops a handoff the run already answered. So the dispatcher asks here first,
behind the guards that end, park, or reconcile the issue and ahead of the
handler (`dispatch_guards._record_stops_the_tick`, and on the adjudication's
own road), and the in-tick handoff into `implementing` a `ready` decision or
a single verdict makes asks the same question before that handler runs.
Beside a standing auto-rebase anchor it is asked first of all, ahead of the
anchor's hold (`dispatch_guards._anchor_holds_the_tick`): the refresh holds
the branch for the capture there too, and on its own road the capture is
retired before the anchor's recovery may reset or push the commit it reported
on. Under a dependency hold it waits there as anywhere, and the anchor's hold
answers the anchor itself, by a clear or a park that moves no checkout.

What is owed is one reading's answer (`completion_admission`), with what its
effect stands on read again behind the issue's last fetch before it
(`completion_effect`). An APPLICABLE
capture is handed, admitted and immutable, to the owner of the road it was
taken on (`ROUTE_OWNERS`), which finishes it through the existing report
recording, code publication, binding, and settlement -- this owner publishes
nothing, infers no review, verification, approval, or documentation pass, and
the owner says whether the tick carries on. The first implementation and an
implementing resume are the implementing stage's
(`stages/implementing/captured_completion`), and the fix a reviewer's change
request handed its developer -- the direct round, or the resume finishing its
parked round -- and the resume answering a pull request's human feedback the
fixing stage's (`stages/fixing/captured_fixes`), asked ahead of the review
resume that would read that developer as a launch that may have run and drop
the request it answered, and of the rescan that would hand the feedback batch
to a second developer. A requirements-drift resume -- on `implementing`,
`validating`, `in_review`, or `resolving_conflict`, a reply that remains its
continuation included -- is the stage's it reported under
(`stages/<stage>/captured_drift`), asked ahead of the drift check that would
resume the developer again over the same edit; a road no owner takes yet
holds the tick, so no handler re-runs paid work. An INVALID capture is retired by a
guarded invalidation (`completion_checkpoint.retire`), which keeps which
invocation it was, owns nothing but the capture, and is decided on the
reading the proof was taken over. The tick ends behind it either way. A
retirement that landed leaves the dispatch's issue and comment older than
the readings that proved the capture stale -- the comment still carrying it
pending, the issue perhaps closed or edited since -- so the stage runs on the
next tick, over both as they then read, as it would with no capture; one that
did not land -- refused because the comment moved since that reading, a
human's repair of the proof included -- is decided afresh there. UNCERTAIN
and DAMAGED captures hold the tick with nothing written. A WAITING one stands down with
nothing written, so a dependency walk, the `ready` decision, or a human's
unlabeled issue is left to its own stage.

An operator's `paused` or `backlog` keeps all of it off: the dispatcher skips
a held issue before any guard, and on the one road it lets a held issue
through -- a close somebody observed -- this stands down with nothing read
or written. Nothing here, recovering paid work included, charges a run,
clears a standing park, or grants an invocation; the run limit's hold is
asked ahead of this, and a capture never stands in for a launch.
"""
from __future__ import annotations

import importlib
import logging
from collections.abc import Mapping
from types import MappingProxyType

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.labels import hard_skip_control_label
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    completion_checkpoint as _checkpoint,
    completion_effect as _effect,
    completion_records as _records,
    completion_recovery_models as _models,
    completion_routes as _routes,
    completion_state as _state,
    stage_targets as _stage_targets,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")

# The owner each road's admitted handoff is given to, as the defining module
# and the function taking the one `AdmittedCompletion` and answering whether
# the tick stops -- resolved when called, as every stage owner the engine
# reaches is (`stage_targets`). The first implementation and an implementing
# resume are the implementing stage's, and a reviewer's change request and a
# pull request's feedback round the fixing stage's, which every half of those
# rounds runs under, and a requirements-drift resume the stage it reported
# under (`DRIFT_OWNERS`); a road no owner takes yet holds an applicable
# capture rather than finishing it.
_FINISHES = "recovers"

_IMPLEMENTING_OWNER = (_stage_targets._IMPLEMENTING_CAPTURE_OWNER, _FINISHES)

_FIXING_OWNER = (_stage_targets._FIXING_CAPTURE_OWNER, _FINISHES)

ROUTE_OWNERS: Mapping[_routes.CompletionRoute, tuple[str, str]] = MappingProxyType({
    _routes.CompletionRoute.IMPLEMENTATION: _IMPLEMENTING_OWNER,
    _routes.CompletionRoute.RESUME: _IMPLEMENTING_OWNER,
    _routes.CompletionRoute.REQUESTED_CHANGES: _FIXING_OWNER,
    _routes.CompletionRoute.PR_FEEDBACK: _FIXING_OWNER,
    _routes.CompletionRoute.REQUIREMENTS_DRIFT: (__name__, "finishes_a_drift"),
})

# A requirements-drift resume is finished by the stage it reported under,
# each through its own drift disposition, so its owner is told by the label
# the capture was taken on (`finishes_a_drift`) rather than by the road alone.
DRIFT_OWNERS: Mapping[WorkflowLabel, tuple[str, str]] = MappingProxyType({
    WorkflowLabel.IMPLEMENTING: (_stage_targets._IMPLEMENTING_DRIFT_CAPTURE_OWNER, _FINISHES),
    WorkflowLabel.VALIDATING: (_stage_targets._VALIDATING_DRIFT_CAPTURE_OWNER, _FINISHES),
    WorkflowLabel.IN_REVIEW: (_stage_targets._IN_REVIEW_DRIFT_CAPTURE_OWNER, _FINISHES),
    WorkflowLabel.RESOLVING_CONFLICT: (_stage_targets._CONFLICT_DRIFT_CAPTURE_OWNER, _FINISHES),
})


def capture_holds_the_tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    label: WorkflowLabel | None,
    state: PinnedState,
) -> bool:
    """Whether the pending capture `state` carries stops this tick, answered if so.

    False wherever the issue carries no capture, or a resolved one, and under
    an operator's hard-skip; a capture nothing can read is decided as one
    (`completion_admission`), and so held.
    """
    unheld = _state.carries(state) and hard_skip_control_label(issue) is None
    if not unheld or isinstance(_state.read(state), _records.ResolvedCapture):
        return False
    decision = _effect.decided(gh, spec, issue, label, state)
    if decision.standing is _models.Standing.WAITING:
        log.info(
            "issue=#%d carries a captured completion and %s; leaving it captured for the %r stage",
            issue.number, decision.reason, label,
        )
        return False
    if decision.standing is _models.Standing.INVALID:
        _invalidates(gh, issue, state, decision.reason)
        return True
    if decision.admitted is not None:
        return _hands_on(decision.admitted)
    log.warning(
        "issue=#%d carries a captured completion it cannot decide on (%s: %s); holding the %r "
        "handler with nothing written so it neither loses nor repeats that work",
        issue.number, decision.standing, decision.reason, label,
    )
    return True


def _invalidates(gh: GitHubClient, issue: Issue, state: PinnedState, reason: _models.Reason | None) -> None:
    """Retire a capture its readings proved stale, and log how that went.

    The tick stops behind it whether it landed or not: one that did not, or
    was never confirmed, may leave the capture standing, and one that did
    leaves the dispatch's own issue and comment behind the readings that
    proved it, so nothing runs on them.
    """
    capture = _state.read(state)
    retired = _checkpoint.retire(
        gh, issue, state, capture.invocation, _records.RetirementReason.INVALIDATED,
    )
    if retired.settled:
        log.info(
            "issue=#%d retired the captured completion of agent invocation %d/%s (%s); nothing of it is "
            "published, and the stage runs on the next tick over the issue as it then reads",
            issue.number, capture.invocation.ordinal, capture.invocation.nonce, reason,
        )
        return
    log.warning(
        "issue=#%d could not retire the captured completion of agent invocation %d/%s (%s: %s); "
        "holding the tick for a later reading",
        issue.number, capture.invocation.ordinal, capture.invocation.nonce, reason,
        retired.refusal or retired.status,
    )


def _hands_on(admitted: _models.AdmittedCompletion) -> bool:
    """Hand an applicable capture to its road's owner, or hold the tick where no owner takes it."""
    route = admitted.capture.handoff.route
    target = ROUTE_OWNERS.get(route)
    if target is None:
        log.warning(
            "issue=#%d carries an applicable captured completion on the %s road, which no owner "
            "takes in this build; holding the %r handler so it does not run the work again",
            admitted.issue.number, route, admitted.label,
        )
        return True
    return _finished_by(target, admitted)


def finishes_a_drift(admitted: _models.AdmittedCompletion) -> bool:
    """Hand an applicable requirements-drift capture to the stage it reported under; whether the tick stops.

    Every label that road's contract records a report under has an owner
    (`DRIFT_OWNERS`), and a capture its contract refuses never reads back
    as one, so the label always names one.
    """
    return _finished_by(DRIFT_OWNERS[admitted.capture.handoff.origin], admitted)


def _finished_by(target: tuple[str, str], admitted: _models.AdmittedCompletion) -> bool:
    """Resolve the owner `target` names when called and hand it `admitted`; whether the tick stops."""
    owner_module, owner_name = target
    owner = getattr(importlib.import_module(owner_module), owner_name)
    return bool(owner(admitted))
