# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a manifest correction's answer is allowed to come to, and the exhaustion that spends its attempt.

The answer goes through every disposition an ordinary decomposer answer does
-- the holds, the timeout, the read-only checkout, the interruption, the
manifest parser -- save one: it earns no correction of its own. Each
disposition decides what the attempt is left as.

- A park -- a timeout, a dirty checkout, a question, silence, or a second
  invalid manifest -- lands first, with the attempt still pending on the state
  it writes, and the attempt is exhausted behind it (`spends_behind_park`),
  naming the correction's own invocation. A park standing over a pending
  attempt is the one a lost exhaustion leaves, which the next tick spends with
  no second notice (`correction_reconcile`); an exhaustion landing ahead of a
  lost park would leave an issue nobody was told about.
- A usable manifest is acted on only once the issue, read afresh, still stands
  where the rejected run left it (`correction_live`) and the attempt is
  exhausted (`clears`): the exhaustion lands before the first child, split
  marker, or label, so a split whose transaction a crash interrupts is the
  split recovery's, never an attempt still pending beside its children. A
  close, a relabel, or an edit since spends the attempt and makes nothing of
  the answer, the edit left for the drift reset's fresh decomposition; a hold
  or a reading GitHub would not answer makes nothing of it and spends nothing.
- A hold, an unresolved accounting, or an interruption leaves the attempt
  pending with its start on the ledgers -- never launched again -- for the
  next tick to give up behind a human park.

An exhaustion that does not land is said locally and grants nothing: the
attempt is left pending and started, and no write here retries it.

An attempt whose context moved -- an edit's reset or a continuation retiring
the session it was saved under -- is retired (`retires`) before any decomposer
is charged behind it, the tick's own reset landed first where only it shows the
move, so the resolution covers no run the fresh decomposition makes.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.agents.models import AgentInvocation
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import record_admission as _record_admission
from orchestrator.workflow.stages.decomposition import (
    correction_checkpoint as _checkpoint,
    correction_commits as _commits,
    correction_live as _live,
    correction_records as _records,
)
from orchestrator.workflow.stages.decomposition.models import _DecomposerRunPlan

log = logging.getLogger("orchestrator.workflow")


def spends(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    attempt: _records.CorrectionAttempt,
    correction: AgentInvocation | None = None,
) -> bool:
    """Exhaust `attempt`, naming `correction` where its launch returned one; whether the record now reads it spent."""
    spent = _checkpoint.exhaust(gh, issue, state, attempt, correction)
    if not spent.settled:
        log.warning(
            "issue=#%d its manifest correction could not be recorded spent (%s); it stays pending and grants nothing",
            issue.number, getattr(spent.refusal, "value", spent.status.value),
        )
    return spent.settled


def spends_behind_park(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    run_plan: _DecomposerRunPlan,
    given_up: _records.CorrectionAttempt | None = None,
) -> None:
    """Exhaust the attempt a park its caller just wrote stands over, where one does.

    The attempt `run_plan`'s own run answers, naming that run; else
    `given_up`, an attempt armed for the run that granted no launch, naming
    none. A plan answering no attempt, with none given up, spends nothing.
    """
    if run_plan.correction is not None:
        spends(gh, issue, state, run_plan.correction, run_plan.agent_result.invocation)
    elif given_up is not None:
        spends(gh, issue, state, given_up)


def clears(gh: GitHubClient, issue: Issue, state: PinnedState, run_plan: _DecomposerRunPlan) -> bool:
    """Whether the usable manifest `run_plan`'s run answered may be acted on now.

    Every run's but a correction's may. A correction's only where the issue
    still stands as its rejected run left it and its attempt reads spent.
    """
    attempt = run_plan.correction
    if attempt is None:
        return True
    live = _live.reads(gh, issue, state, attempt.source)
    if live in {_live.Live.HELD, _live.Live.UNREAD}:
        log.info("issue=#%d its corrected manifest reads %s; acting on nothing", issue.number, live.value)
        return False
    spent = spends(gh, issue, state, attempt, run_plan.agent_result.invocation)
    if live is _live.Live.MOVED:
        log.info(
            "issue=#%d moved while its manifest correction ran; its answer is spent and acted on nothing",
            issue.number,
        )
        return False
    return spent


def retires(gh: GitHubClient, issue: Issue, state: PinnedState, attempt: _records.CorrectionAttempt) -> bool:
    """Retire a moved `attempt`; whether the tick may go on to the fresh decomposition the move buys.

    A retirement refused for want of evidence is one whose move is this
    tick's in memory alone, so that state is written and the retirement asked
    again over it. Only a caller left withheld -- a write unconfirmed, or
    landing over a comment moved since -- holds the tick; a retirement
    refused otherwise leaves the attempt pending, granting nothing.
    """
    retired = _checkpoint.retire(gh, issue, state, attempt)
    if retired.refusal is _commits.CorrectionRefusal.NO_EVIDENCE and _record_admission.written(gh, issue, state):
        retired = _checkpoint.retire(gh, issue, state, attempt)
    if not retired.settled:
        log.warning(
            "issue=#%d its moved manifest correction could not be retired (%s); it grants nothing",
            issue.number, getattr(retired.refusal, "value", retired.status.value),
        )
    return not state.withheld
