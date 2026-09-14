# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Interpret and guard a completed late run before settling or publishing its verdict.

Usage is folded before the completed run is checked for interruption and
candidate mutation, then its session and answer are recorded.
Every completion, including a reused answer or a park, re-reads the issue
owner. Only the settlement that clears this guard may hand a split to the
transaction; deferred runs leave durable state as they found it.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import guards as _guards, issue_usage as _issue_usage, usage as _usage
from orchestrator.workflow.stages.decomposition import (
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_session as _late_session,
    late_settlement as _late_settlement,
    late_transaction as _late_transaction,
    late_verdict as _late_verdict,
)
from orchestrator.workflow.stages.decomposition.late_evidence import _candidate_mutation
from orchestrator.workflow.stages.decomposition.late_models import _LateContext, _OwnerState
from orchestrator.workflow.stages.decomposition.late_result_models import _LateAdjudicationRun, _LateDisposition

log = logging.getLogger("orchestrator.workflow")



def _guarded(
    context: _LateContext, finished: _LateAdjudicationRun,
) -> _LateAdjudicationRun:
    """Read the owner again now this run is over, then act on what it left.

    Every completion comes through here, not only the ones that decided
    something: a question, a timeout, an unusable reply, and a reply refused
    for a moved candidate are all runs the issue paid for, and a closure
    during any of them strands the same generation and the same hold.

    A run the tick DECLINED is the one exception, and it is not a completion:
    an operator's `paused` label and a shutdown sweep both mean this tick did
    not happen, and durable state has to be left exactly as the prior tick
    left it -- which a write here would break.

    A split is the one verdict the settlement does not finish. It hands back
    an outcome carrying the guarantee the transaction cannot check for itself
    -- that this verdict was re-checked against an owner read taken after the
    agent finished -- and the transaction that creates the children runs from
    here, past that read, on that handoff and on no other shape.
    """
    if finished.disposition == _LateDisposition.DEFERRED:
        return finished
    reading = _late_owner._guarded_owner(context)
    if reading == _OwnerState.CLOSED:
        return _late_outcome._finished(context, _LateDisposition.CANCELLED)
    if reading == _OwnerState.UNREADABLE:
        return _late_outcome._finished(context, _LateDisposition.PARKED)
    settled = _late_settlement._settle_adjudication(context, finished)
    if settled.guarded_split is None:
        return settled
    return _late_transaction._run_late_split(context, settled)


_LAST_AGENT_ACTION_AT = "last_agent_action_at"


_TIMEOUT_PARK = "late decomposer timed out after {seconds}s"


def _settle(
    context: _LateContext, agent_result: AgentResult, worktree: Path,
) -> _LateAdjudicationRun:
    """Fold this run's usage and decline the outcomes that are not answers."""
    if _guards._paused_during_agent_run(context.gh, context.issue):
        return _late_outcome._finished(context, _LateDisposition.DEFERRED)
    context.state.set(_LAST_AGENT_ACTION_AT, _usage._now_iso())
    if not agent_result.interrupted:
        _issue_usage._accumulate_issue_usage(context.state, agent_result.usage)
    declined = _declined_run(context, agent_result, worktree)
    if declined is not None:
        return _guarded(context, declined)
    _late_session._record_late_session(context.state, agent_result)
    return _guarded(
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
