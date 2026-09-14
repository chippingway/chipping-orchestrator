# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Record durable lifetime run-budget transitions to audit and analytics streams.

Each sink is guarded independently so one failure cannot cost the other or the
workflow tick. The shared model owner defines phases and launch identities; the
field owner renders the ledger and correlation values without changing them."""
from __future__ import annotations

import logging
from typing import Any

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.observability.analytics.recording import events as _recording_events
from orchestrator.workflow.engine import (
    run_budget_fields as _run_budget_fields,
    run_budget_models as _run_budget_models,
)
from orchestrator.workflow.engine.run_ledger_models import AgentRunLedger

log = logging.getLogger("orchestrator.workflow")

# The one family every agent-run budget transition is written under. A wire
# string on both sinks, so an operator's filter and a database column key off
# it.
AGENT_RUN_BUDGET_EVENT = "agent_run_budget"


def _emit_charge(
    gh: GitHubClient,
    issue: Issue,
    phase: _run_budget_models.BudgetPhase,
    ledger: AgentRunLedger,
    launch: _run_budget_models.AgentRunLaunch,
) -> None:
    """Record one durable phase of the charge a launch took.

    Both phases are the same record under a different `phase`, because they
    describe the same launch against the same counts: what separates them is
    only how far it got, and a reader counting reservations against starts is
    exactly the reader this pair exists for.
    """
    _emit(gh, issue.number, launch.stage, {
        **_run_budget_fields._ledger_fields(phase, ledger),
        "agent_role": launch.agent_role,
        "reservation_id": _run_budget_fields._reservation_id(launch, ledger),
    })


def _emit_exhaustion(
    gh: GitHubClient,
    issue: Issue,
    ledger: AgentRunLedger,
    launch: _run_budget_models.AgentRunLaunch,
) -> None:
    """Record the launch a spent lifetime allowance turned away.

    The reading is the one the refusal was actually made on rather than one
    taken again here, so the record and the sentence the park says to the
    thread quote the same numbers.

    No `reservation_id`: a refused launch never took a charge, and a record
    naming one would correlate against a reservation nothing wrote. The stage
    and the role are still here -- they are what an operator needs to see
    which work the ceiling is stopping.
    """
    _emit(gh, issue.number, launch.stage, {
        **_run_budget_fields._ledger_fields(_run_budget_models.BudgetPhase.EXHAUSTED, ledger),
        "agent_role": launch.agent_role,
        "reason": _run_budget_fields._exhaustion_reason(ledger),
    })


def _emit_extension(
    gh: GitHubClient, issue: Issue, ledger: AgentRunLedger,
) -> None:
    """Record the wider ceiling a trusted operator command just bought.

    The stage is read off the label the issue is wearing rather than named by
    a caller, because a grant has no launch to take one from. What it says is
    where the issue was standing when a human answered its park, which is the
    whole of what an extension can say about where it happened.

    No role and no reservation, though. The ledger is spent by every role at
    every stage, so there is no one role a human bought runs for -- and a
    grant is not a launch, so there is no charge for a correlation to name.
    """
    _emit(
        gh,
        issue.number,
        _run_budget_fields._label_stage(gh, issue),
        _run_budget_fields._ledger_fields(_run_budget_models.BudgetPhase.EXTENDED, ledger),
    )


def _emit(
    gh: GitHubClient,
    issue_number: int,
    stage: str | None,
    payload: dict[str, Any],
) -> None:
    """Write one budget record to both sinks, under their own envelopes.

    Two independent writes rather than one, and neither is allowed to skip the
    other: they are separate observability surfaces, and one being unavailable
    is not a reason to lose the other. Each rides its own guard, so a client
    or a sink that raises costs the record and nothing else -- the transition
    it describes is already durable on the issue.
    """
    _emit_audit(gh, issue_number, stage, payload)
    _emit_analytics(gh, issue_number, stage, payload)


def _emit_audit(
    gh: GitHubClient,
    issue_number: int,
    stage: str | None,
    payload: dict[str, Any],
) -> None:
    try:
        gh.emit_event(
            AGENT_RUN_BUDGET_EVENT,
            issue_number=issue_number,
            stage=stage,
            **payload,
        )
    except Exception:
        log.exception(
            "issue=#%s: agent-run budget audit emission failed; continuing",
            issue_number,
        )


def _emit_analytics(
    gh: GitHubClient,
    issue_number: int,
    stage: str | None,
    payload: dict[str, Any],
) -> None:
    try:
        _recording_events.append_record(
            _recording_events.build_record(
                repo=getattr(gh, "_repo_slug", None) or "",
                issue=issue_number,
                event=AGENT_RUN_BUDGET_EVENT,
                stage=stage,
                **payload,
            ),
        )
    except Exception:
        log.exception(
            "issue=#%s: agent-run budget analytics record failed; continuing",
            issue_number,
        )
