# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Start one late adjudication after admission and content reconciliation.

Only a fresh run spends the shared retry budget. The attempt owner persists
its identity with that charge held back; pause and launch refusals remain
free. The completion owner folds usage, proves the candidate unchanged,
and guards the recorded answer before settlement. A split transaction that
has begun over a recorded outcome no longer answering parks instead: no fresh
run is bought over children and a snapshot already on the remote.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.late_split.models import (
    LateFailure,
)
from orchestrator.workflow.late_split.phases import IN_FLIGHT_PHASES
from orchestrator.workflow.stages.decomposition import (
    late_attempt as _late_attempt,
    late_completion as _late_completion,
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_retry_cap as _late_retry_cap,
    late_run_reading as _late_run_reading,
    late_session as _late_session,
)
from orchestrator.workflow.stages.decomposition.late_evidence import _MISSING_WORKTREE_PARK
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.late_result_models import _LateAdjudicationRun, _LateDisposition

log = logging.getLogger("orchestrator.workflow")


_HOLD_DISPLACED_PARK = (
    "the pull request this issue's candidate stands on carries a description "
    "this orchestrator did not write, so the adjudication hold cannot be put "
    "back without overwriting it -- and no late decomposer is started while "
    "that pull request is open with nothing on it saying the committed "
    "candidate is still being adjudicated. Settle the pull request, or put "
    "its description back, and the next tick continues against the same "
    "frozen commit."
)


_UNANSWERED_SPLIT_PARK = (
    "the committed candidate for this issue was adjudicated as a split and "
    "its transaction had begun, but the outcome on the record is not one this "
    "orchestrator can act on, so no child was created and no late decomposer "
    "was spawned. A fresh verdict would be taken beside whatever that split "
    "already put on the remote -- its snapshot, and any child it created -- "
    "and could adopt those children as slices of a different split, so they "
    "are left exactly as they are. Settle the split by hand."
)


def _run_and_decide(context: _LateContext) -> _LateAdjudicationRun:
    """Spend a retry slot on one adjudication of the frozen candidate.

    The slot is the shared budget's and the refusal it can answer with is a
    park this mode owns: it is taken with the generation this tick reached, so
    the record, the reason it stopped moving, and the sentence the thread is
    owed go out on one write. Reached only with no such park standing, since
    the gate above holds that case before any of this runs.

    A hold a human displaced stops this the way a failed one does. Their words
    are left where they wrote them, but the pull request is now open with
    nothing on it saying an adjudication is running -- so no agent is started
    under it. This refusal is here rather than beside the hold because an
    answer already recorded is still allowed to settle: settling releases a
    hold that is already gone, and only a NEW run would leave a human free to
    merge under one.

    A close a poll observed stops it too, and that one is asked twice, the
    second time right against the spawn. Everything between the tick's own
    gates and here is a request -- a worktree probe, a thread read, a hold to
    reconcile, and the write that records what this attempt IS -- and the
    poll runs beside all of it, so the reading it took may not have
    existed when this tick started nor when the first of those two asked. The
    latch costs nothing, and what it is asked against is the one step that
    puts an agent on somebody's repository. It is asked with the retry
    accounting handed back, because the cancellation it takes is a write and
    a run nobody started may not be one the issue paid for.

    A split transaction already in flight stops it before any of that. Its
    recorded outcome is what the transaction resumes from, and reaching here
    means that outcome no longer answers (`_unanswered_in_flight`): a fresh
    run would decide again beside whatever the transaction has put on the
    remote, so nothing is paid for and nothing is created.

    Ahead of all of it, a `single` or `question` park standing over a record
    that no longer answers as that verdict comes down
    (`late_parks._retire_outlived_park`): whatever the run this reaches decides
    is what the issue stops for next.
    """
    _late_parks._retire_outlived_park(context)
    if _stopped_before_spawn(context):
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    worktree = _worktree_paths._worktree_path(
        context.spec, context.issue.number,
    )
    if not worktree.exists():
        _late_parks._park(
            context, _MISSING_WORKTREE_PARK,
            reason=_late_park_state.PARK_WORKTREE_MISSING,
        )
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    unspent = _late_attempt._accounting(context.state)
    if not _late_retry_cap._charge_fresh_spawn(context):
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    stopped = _late_attempt._latched_stop(context, unspent)
    if stopped is not None:
        return _late_outcome._finished(context, stopped)
    return _spawned(context, unspent, worktree)


def _stopped_before_spawn(context: _LateContext) -> bool:
    """Park where no run may be started under what this tick found, and say so.

    The in-flight transaction first, because what it stands on is the remote
    rather than one pull request's description.
    """
    if _unanswered_in_flight(context):
        log.error(
            "issue=#%d has a split transaction in flight over a recorded "
            "outcome that does not answer; parking rather than adjudicating "
            "again", context.issue.number,
        )
        _late_outcome._emit_failure(context, LateFailure.CHILD_CREATE_FAILED)
        _late_parks._park(
            context, _UNANSWERED_SPLIT_PARK,
            reason=_late_park_state.PARK_CHILDREN_FAILED,
        )
        return True
    if not context.displaced_hold:
        return False
    _late_outcome._emit_failure(context, LateFailure.PLAN_PR_HOLD_FAILED)
    _late_parks._park(
        context, _HOLD_DISPLACED_PARK,
        reason=_late_park_state.PARK_HOLD_FAILED,
    )
    return True


def _unanswered_in_flight(context: _LateContext) -> bool:
    """Whether a begun split transaction stands over an outcome that no longer answers.

    Begun is the phase: a record at a boundary the transaction owns may have
    cut a snapshot and created children before writing either down. The
    outcome is whatever the record holds under the result's keys -- a verdict
    in no spelling this build reads, a lost field, a manifest the reply's own
    rules refuse -- and it counts wherever any of them is there and the
    record does not answer, since a value that does not parse is still one
    somebody wrote. Only a result deliberately dropped
    (`late_session._drop_late_result`) leaves none of those keys, and the run
    it was dropped for is the one that replaces it.
    """
    if context.generation.phase not in IN_FLIGHT_PHASES:
        return False
    if not any(key in context.state.state_data for key in _late_session._RESULT_KEYS):
        return False
    return not _late_run_reading._read_late_run(context.state).answers(context.generation)


def _spawned(
    context: _LateContext, unspent: dict, worktree: Path,
) -> _LateAdjudicationRun:
    """Record what this attempt is, then start it -- latch permitting.

    `_begin` is itself a pinned write, so the poll can observe the close
    inside the very write that says this run is about to start. The latch is
    asked again immediately against the spawn: what the record then claims is
    an attempt nobody made, which the next tick reconciles for free, while an
    agent that ran is what nothing takes back.
    """
    started = _late_run_reading._spawn_record_for(
        context.state, context.generation, resuming=context.answering,
    )
    _late_attempt._begin(context, started, unspent)
    stopped = _late_attempt._latched_stop(context, unspent)
    if stopped is not None:
        return _late_outcome._finished(context, stopped)
    return _late_completion._settle(
        context,
        _late_session._spawn_late_adjudicator(context, started, worktree),
        worktree,
    )
