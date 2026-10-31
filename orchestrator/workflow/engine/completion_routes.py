# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which developer roads may leave a captured completion, and which of their returns qualify.

A completion is captured for one thing: a developer run that finished its
road's report contract, whose return a live hold or a lost tick could
otherwise discard before the report reaches the existing delivery transaction.
So the road is named by the caller that knows it (`CompletionRoute`) and never
inferred from the agent role, the backend, or an exit code. A reviewer,
decomposer, question, discussion, documentation, or ordinary conflict run is
no road here at all.

Each road's contract (`CONTRACTS`) says which workflow labels a report on it
records as its route -- the label the existing delivery stamps its record with
-- whether a `REPORT: VERIFIED` pays it, and whether it answers a handoff its
caller froze before the launch. A rewritten-head refresh is paid only by a
fresh READY report of the head it was asked about, so a verification of the
report the pull request already carried is refused here, as that road's own
outcome owner refuses it. A reviewer's change request and a pull request's
feedback round each answer a handoff, so neither is captured without one. A
requirements-drift resume settles the reading it was handed for itself, as its
own tick always has, so the report its capture becomes carries none of that
input: a pair riding the report would be carried onto every later report that
supersedes it, and a requirements baseline settled late would move the issue
back onto requirements it has since left.

Whether a return qualifies is read through the outcome owner's completed-run
reader (`report_outcomes._report_outcome_of_run`): a run that never started,
was interrupted, timed out, was refused by its provider, or exited nonzero is
refused before its message is read, and a message that never used the
contract, or reached for it and missed, is refused as that reader refuses it.
A run whose backend recorded unfinished tool steps or a terminal failure is
incomplete whatever its message says, and one no tracked spawn identified is
refused too, since nothing could bind its capture to the invocation it was.
READY and VERIFIED stay two outcomes: what is captured is the outcome the
reader answered, never one rewritten into the other.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from orchestrator.agents.models import AgentResult
from orchestrator.workflow.engine import report_outcome_models as _outcome_models, report_outcomes as _outcomes
from orchestrator.workflow.state import WorkflowLabel


class CompletionRoute(StrEnum):
    """The developer roads whose report a completion may carry."""

    # The first implementation of an issue.
    IMPLEMENTATION = "implementation"
    # A human reply or `/orchestrator continue` resuming that implementation.
    RESUME = "resume"
    # The fix a reviewer's CHANGES_REQUESTED verdict handed the developer.
    REQUESTED_CHANGES = "requested_changes"
    # A fix round answering a pull request's human feedback.
    PR_FEEDBACK = "pr_feedback"
    # A resume a requirements edit bought, on whichever stage it was read on.
    REQUIREMENTS_DRIFT = "requirements_drift"
    # The fresh report of a head this orchestrator rewrote the pull request onto.
    REPORT_REFRESH = "report_refresh"
    # The developer revision a human's guidance bought under a late adjudication.
    LATE_REVISION = "late_revision"


class Ineligible(StrEnum):
    """Why a completed developer return earns no capture, beside the outcome owner's own refusals."""

    # The label the caller names is not one this road records its report under.
    OFF_ROUTE = "off_route"
    # The road answers a frozen handoff, and the caller froze none.
    UNHANDED = "unhanded"
    # The backend recorded unfinished tool steps or a terminal failure.
    INCOMPLETE = "incomplete"
    # A verification on a road only a fresh READY report pays.
    STALE_VERIFICATION = "stale_verification"
    # No tracked spawn identified the process this result came from.
    UNIDENTIFIED = "unidentified"


@dataclass(frozen=True)
class RouteContract:
    """What one road's captured report has to be.

    `labels` are the workflow labels a report on the road is recorded under;
    `verified` is whether a verification pays it; `handed` is whether it
    answers a handoff its caller froze before the launch; `settles_input` is
    whether the road settles the input its run was handed for itself, as its
    own tick does, so the report its capture becomes carries none of it.
    """

    labels: frozenset[WorkflowLabel]
    verified: bool = True
    handed: bool = False
    settles_input: bool = False


_IMPLEMENTING = frozenset((WorkflowLabel.IMPLEMENTING,))

_FIXING = frozenset((WorkflowLabel.FIXING,))

CONTRACTS = MappingProxyType({
    CompletionRoute.IMPLEMENTATION: RouteContract(_IMPLEMENTING),
    CompletionRoute.RESUME: RouteContract(_IMPLEMENTING),
    CompletionRoute.REQUESTED_CHANGES: RouteContract(_FIXING, handed=True),
    CompletionRoute.PR_FEEDBACK: RouteContract(_FIXING, handed=True),
    CompletionRoute.REQUIREMENTS_DRIFT: RouteContract(frozenset((
        WorkflowLabel.IMPLEMENTING, WorkflowLabel.VALIDATING,
        WorkflowLabel.IN_REVIEW, WorkflowLabel.RESOLVING_CONFLICT,
    )), settles_input=True),
    CompletionRoute.REPORT_REFRESH: RouteContract(frozenset((WorkflowLabel.VALIDATING,)), verified=False),
    CompletionRoute.LATE_REVISION: RouteContract(frozenset((WorkflowLabel.DECOMPOSING,))),
})

# What a return that qualifies carries.
CapturedOutcome = _outcome_models._ReadyReport | _outcome_models._VerifiedReport


def refused_by_contract(
    route: CompletionRoute, origin: WorkflowLabel, *, verified: bool, handed: bool,
) -> Ineligible | None:
    """Why `route`'s contract refuses a report recorded under `origin`, or None.

    Asked of a return before it is captured and of a capture read back alike,
    so a record the capture would have refused reads back as damage rather
    than as a road it may take. `verified` is whether the report is a
    verification, and `handed` whether its caller froze a handoff.
    """
    contract = CONTRACTS[route]
    if origin not in contract.labels:
        return Ineligible.OFF_ROUTE
    if contract.handed and not handed:
        return Ineligible.UNHANDED
    if verified and not contract.verified:
        return Ineligible.STALE_VERIFICATION
    return None


def eligible_outcome(
    agent_result: AgentResult, route: CompletionRoute, origin: WorkflowLabel, *, handed: bool,
) -> CapturedOutcome | Ineligible | _outcome_models._ReportRefusal:
    """The report outcome `agent_result` may be captured with on `route`, or why it may not.

    The run is judged before its road, and its message by the outcome owner:
    a refusal of that reader's is answered as it gave it. An incomplete run is
    refused whatever outcome its message parsed to, and a qualifying outcome
    only once the road's contract takes it and an identity names the process.
    """
    outcome = _outcomes._report_outcome_of_run(agent_result)
    if isinstance(outcome, _outcome_models._ReportRefusal):
        return outcome
    if agent_result.unfinished_steps or agent_result.terminal_failure is not None:
        return Ineligible.INCOMPLETE
    refusal = refused_by_contract(
        route, origin, verified=isinstance(outcome, _outcome_models._VerifiedReport), handed=handed,
    )
    if refusal is not None:
        return refusal
    if agent_result.invocation is None:
        return Ineligible.UNIDENTIFIED
    return outcome
