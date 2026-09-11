# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Run and interpret one late adjudication after admission and content reconciliation.

Only a fresh run spends the shared retry budget. The attempt owner persists
its identity with that charge held back; pause and launch refusals remain
free. Completed runs fold usage and prove the candidate unchanged before
the completion owner guards and settles the answer.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator import config
from orchestrator.agents import AgentResult
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import guards as _guards, usage as _usage
from orchestrator.workflow.late_split.models import (
    LateFailure,
    LateGeneration,
)
from orchestrator.workflow.stages.decomposition import (
    late_attempt as _late_attempt,
    late_completion as _late_completion,
    late_outcome as _late_outcome,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    late_retry_cap as _late_retry_cap,
    late_session as _late_session,
    late_verdict as _late_verdict,
)
from orchestrator.workflow.stages.decomposition.late_admission import _MISSING_WORKTREE_PARK
from orchestrator.workflow.stages.decomposition.late_models import (
    _LateAdjudicationRun,
    _LateContext,
    _LateDisposition,
)

log = logging.getLogger("orchestrator.workflow")


_LAST_AGENT_ACTION_AT = "last_agent_action_at"


_HOLD_DISPLACED_PARK = (
    "the pull request this issue's candidate stands on carries a description "
    "this orchestrator did not write, so the adjudication hold cannot be put "
    "back without overwriting it -- and no late decomposer is started while "
    "that pull request is open with nothing on it saying the committed "
    "candidate is still being adjudicated. Settle the pull request, or put "
    "its description back, and the next tick continues against the same "
    "frozen commit."
)


_TIMEOUT_PARK = "late decomposer timed out after {seconds}s"


_MOVED_HEAD_PARK = (
    "the late decomposer was read-only, but the candidate worktree is no "
    "longer on the frozen commit {frozen}. Its verdict is not being used. "
    "Put the worktree back on that commit before resuming -- the recorded "
    "SHA is the evidence every later step acts on, and whatever HEAD points "
    "at now is not it."
)


_DIRTY_TREE_PARK = (
    "the late decomposer was read-only, but it left changes in the candidate "
    "worktree (or the tree could not be read). Its verdict is not being "
    "used. Clean the worktree back to the frozen commit {frozen} before "
    "resuming, so the candidate a later step publishes is the one that was "
    "measured."
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
    started = _late_session._spawn_record_for(
        context.state, context.generation, resuming=context.answering,
    )
    _late_attempt._begin(context, started, unspent)
    stopped = _late_attempt._latched_stop(context, unspent)
    if stopped is not None:
        return _late_outcome._finished(context, stopped)
    return _settle(
        context,
        _late_session._spawn_late_adjudicator(context, started, worktree),
        worktree,
    )


def _settle(
    context: _LateContext, agent_result: AgentResult, worktree: Path,
) -> _LateAdjudicationRun:
    """Fold this run's usage and decline the outcomes that are not answers."""
    if _guards._paused_during_agent_run(context.gh, context.issue):
        return _late_outcome._finished(context, _LateDisposition.DEFERRED)
    context.state.set(_LAST_AGENT_ACTION_AT, _usage._now_iso())
    if not agent_result.interrupted:
        _usage._accumulate_issue_usage(context.state, agent_result.usage)
    declined = _declined_run(context, agent_result, worktree)
    if declined is not None:
        return _late_completion._guarded(context, declined)
    _late_session._record_late_session(context.state, agent_result)
    return _late_completion._guarded(
        context, _late_verdict._decide(context, agent_result.last_message),
    )


def _declined_run(
    context: _LateContext, agent_result: AgentResult, worktree: Path,
) -> _LateAdjudicationRun | None:
    """The refusals a finished run earns before its reply is read at all.

    The mutation check sits ahead of the interruption refusal for the reason
    the initial decomposer's dirty check does: a run the shutdown sweep killed
    can have written before it died, and a contaminated candidate is a thing
    an operator has to be told about whether or not the run that caused it
    counted. A launch that never became a process is ahead of both, since a
    candidate changed by something else is not a verdict this run contaminated.
    """
    if _guards._ignore_if_never_invoked(context.issue, agent_result):
        return _late_outcome._finished(context, _LateDisposition.DEFERRED)
    if agent_result.timed_out:
        return _late_outcome._parked_run(
            context,
            agent_result,
            _TIMEOUT_PARK.format(seconds=config.AGENT_TIMEOUT),
            reason=_late_park_state.PARK_TIMEOUT,
        )
    mutated = _candidate_mutation(context.generation, worktree)
    if mutated is not None:
        log.error(
            "issue=#%d the late decomposer left the candidate worktree "
            "changed; refusing its verdict",
            context.issue.number,
        )
        return _late_outcome._parked_run(
            context, agent_result, mutated,
            reason=_late_park_state.PARK_WORKTREE_MUTATED,
        )
    if _guards._ignore_if_interrupted(context.issue, agent_result):
        return _late_outcome._finished(context, _LateDisposition.DEFERRED)
    return None


def _candidate_mutation(
    generation: LateGeneration, worktree: Path,
) -> str | None:
    """The park a worktree the read-only agent changed earns, or None.

    Both halves are proved rather than assumed. HEAD has to still BE the
    frozen commit -- not merely to contain it -- because a commit made on top
    of the candidate is what a later publication would push, and an unreadable
    HEAD proves nothing and reads the same way. The tree is asked through the
    status form for the same reason: a caller whose next step ends in a push
    has to prove the tree is clean, and a read that established nothing is not
    that proof.
    """
    head = _verification_probes._head_sha(worktree)
    if head != generation.candidate_sha:
        return _MOVED_HEAD_PARK.format(frozen=generation.candidate_sha)
    tree = _verification_probes._worktree_status(worktree)
    if not tree.readable or tree.paths:
        return _DIRTY_TREE_PARK.format(frozen=generation.candidate_sha)
    return None
