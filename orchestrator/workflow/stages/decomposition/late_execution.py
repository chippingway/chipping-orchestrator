# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Start one late adjudication after admission and content reconciliation.

Only a fresh run spends the shared retry budget. The attempt owner persists
its identity with that charge held back; pause and launch refusals remain
free. The completion owner folds usage, proves the candidate unchanged,
and guards the recorded answer before settlement.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.late_split.models import (
    LateFailure,
)
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
    """
    if context.displaced_hold:
        _late_outcome._emit_failure(context, LateFailure.PLAN_PR_HOLD_FAILED)
        _late_parks._park(
            context, _HOLD_DISPLACED_PARK,
            reason=_late_park_state.PARK_HOLD_FAILED,
        )
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
