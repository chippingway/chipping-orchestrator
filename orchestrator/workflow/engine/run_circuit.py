# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reserve and start a lifetime agent-run charge before invoking any process.

Only the logical launch holding a reserved charge can reuse it. The state owner
reads and persists each step before its budget event is emitted; exhaustion
parks the issue on that same durable reading and always refuses invocation."""
from __future__ import annotations

import logging

from orchestrator.agents.models import AgentResult
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    run_budget as _run_budget,
    run_budget_models as _run_budget_models,
    run_charge_state as _run_charge_state,
    run_ledger as _run_ledger,
    run_limit as _run_limit,
)
from orchestrator.workflow.engine.run_budget_models import AgentRunLaunch
from orchestrator.workflow.engine.run_ledger_models import AgentRunLedger

log = logging.getLogger("orchestrator.workflow")

# What a launch that never happened reports as its status. Negative, like
# every other code in this repository that is not an ordinary exit, because
# there was no process to take one from.
_NO_PROCESS_EXIT_CODE = -1


def _refused_run() -> AgentResult:
    """What a launch this owner turned away answers its caller with.

    Marked as an interrupted run because that is what it is to everything
    above: a run with no trustworthy outcome, whose whole contract is that the
    handler returns without writing durable state. Every spawning stage
    already reads that answer through `_ignore_if_interrupted`, so a refusal
    reaches a park, a watermark, and a session record the same way a shutdown
    kill does -- by reaching none of them.

    And marked as never invoked, which a shutdown kill is not. Several stages
    inspect the worktree BEFORE they ask about interruption, on purpose: a run
    the sweep killed can have written before it died, and what it left is an
    operator's to look at whether or not the run counted. A refusal wrote
    nothing, so a tree that is dirty for some older reason is not this
    launch's doing -- and a park taken in its name would overwrite the one
    this owner just recorded with a reason about a process that never existed.
    `_ignore_if_never_invoked` is what those roads ask first.
    """
    return AgentResult(
        session_id=None,
        last_message="",
        exit_code=_NO_PROCESS_EXIT_CODE,
        timed_out=False,
        stdout="",
        stderr="",
        interrupted=True,
        invoked=False,
    )


def _charge_launch(
    gh: GitHubClient, budget: _run_charge_state.AgentRunBudget, launch: AgentRunLaunch,
) -> bool:
    """Whether this launch has paid for the process it is about to invoke.

    The whole circuit, in the order its answers have to be taken. The ledger
    is read off durable state rather than off the caller's, because the
    caller's has been carried since the tick's own read and a charge decided
    on a stale count is a ceiling enforced against a number that has moved.

    A charge already standing for this launch is one a previous tick took and
    never spawned, so it is honored rather than charged again -- and honored
    without asking the allowance, since the run it stands for is already paid
    for and refusing it would spend the charge on nothing. Every other launch
    is a new attempt: it is refused where the allowance has nothing left, and
    otherwise reserved, started, and let through.
    """
    durable = _run_charge_state._durable_state(gh, budget.issue)
    if durable is None:
        return False
    ledger = _run_ledger._read_ledger(durable)
    if not ledger.pending_for(launch.fingerprint):
        if ledger.spent:
            _park_spent(gh, budget, durable, ledger, launch)
            return False
        if not _reserve(gh, budget, durable, launch):
            return False
    return _start(gh, budget, durable, launch)


def _reserve(
    gh: GitHubClient,
    budget: _run_charge_state.AgentRunBudget,
    durable: PinnedState,
    launch: AgentRunLaunch,
) -> bool:
    """Charge this launch one run, and record the charge if it landed.

    The record follows the write rather than the staging, so what reaches a
    sink is a run this issue durably owes rather than one a refused request
    left it never charged for.
    """
    recorded = dict(durable.data)
    charged = _run_ledger._reserve_run(durable, launch.fingerprint)
    if not _run_charge_state._persist(gh, budget, durable, recorded):
        return False
    _run_budget._emit_charge(
        gh, budget.issue, _run_budget_models.BudgetPhase.RESERVED, charged, launch,
    )
    return True


def _start(
    gh: GitHubClient,
    budget: _run_charge_state.AgentRunBudget,
    durable: PinnedState,
    launch: AgentRunLaunch,
) -> bool:
    """Move this launch's charge to the phase a spawn is about to happen in.

    Recorded once per charge rather than once per launch that reached here: a
    launch honoring a reservation an earlier tick left standing pays for no
    new run, so the only budget transition it has to report is this one.
    """
    recorded = dict(durable.data)
    _run_ledger._start_reserved_run(durable)
    if not _run_charge_state._persist(gh, budget, durable, recorded):
        return False
    _run_budget._emit_charge(
        gh,
        budget.issue,
        _run_budget_models.BudgetPhase.STARTED,
        _run_ledger._read_ledger(durable),
        launch,
    )
    return True


def _park_spent(
    gh: GitHubClient,
    budget: _run_charge_state.AgentRunBudget,
    durable: PinnedState,
    ledger: AgentRunLedger,
    launch: AgentRunLaunch,
) -> None:
    """Stop this issue on the reading the refusal was made on.

    The park owner is handed the ledger rather than taking one, so the
    sentence a human is shown quotes the allowance and the spend this launch
    was actually turned away on. It writes the durable half itself, which is
    why the caller's object is merged into afterwards rather than written:
    a refusal is answered with an interrupted run, and the handler above is
    about to return without a write of its own.

    The launch travels with them for the same reason: the park is the whole of
    what an issue's lifetime ends in, and the record it leaves on the budget
    stream is the only place the work the ceiling actually stopped is named.

    A park that could not be taken still refuses the launch. The allowance is
    spent either way, and the poll comes back to a park that was never
    recorded -- while a spawn let through because the announcement failed is a
    run nothing gets back.
    """
    recorded = dict(durable.data)
    try:
        _run_limit._park_exhausted(gh, budget.issue, durable, ledger, launch)
    except Exception:
        log.exception(
            "issue=#%d has spent every agent run it is allowed, and the park "
            "that says so could not be taken; invoking nothing regardless",
            budget.issue.number,
        )
        return
    _run_charge_state._merge_circuit_fields(recorded, durable, budget.state)
