# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Ask an implementing developer for a task snapshot, record it, and keep it out of the reply the workflow reads.

Who is asked is decided by the road a report-producing attempt was frozen
on, and only two roads ask: the first implementation, and an implementing
resume -- a human's reply or an operator's `/orchestrator continue` --
which are the initial implementation request and its ordinary
continuations (`CompletionRoute.IMPLEMENTATION`, `RESUME`). Every attempt
the shared developer coordinator makes on either road, a poisoned
session's fresh retry and an Antigravity command recovery included, is
handed the request (`asked`), and every return on them is received
(`receive`). A fix round, a drift resume, a refresh, a late revision, a
documentation pass, and every run that freezes no road are neither.

The request is `prompt_notes._TASK_SNAPSHOT_NOTE`, appended to the prompt
the attempt is handed. Receiving a return does two things. A genuine one --
a run the tracked spawn started and stamped, which completed on its own
terms by its status alone: invoked, neither interrupted nor timed out,
exiting 0, and leaving no tool step unfinished or failure normalized -- is
handed to the analytics recorder with its invocation, the requirements the
attempt's prompt was handed (which its road answers for), and the report
reader's framing of the reply (`_framing`), which the recorder asks inside
its own failure boundary; nothing about the reply is read here first. A
run that never started, a synthesized result, and the recovery that finishes
a captured report from its record are no return and record nothing.

And every return on these roads, genuine or not, leaves the workflow the
reply it reads: the attachment lines above the report outcome are taken out
of the result's message (`_workflow_reply`), so a reply carrying nothing
else reads as silent, no park or notice quotes the line, and a report
outcome reads as it would without it. Lines at or past the outcome stay,
so the report reader still refuses text after an outcome and still
publishes a report as it was written. Nothing here reads an observation
back, and recording one raises nothing into the attempt it observes.
"""
from __future__ import annotations

from orchestrator.agents.models import AgentResult
from orchestrator.observability.analytics.observations import (
    attachments as _attachments,
    recorder as _recorder,
    records as _observation_records,
)
from orchestrator.workflow.engine import (
    completion_records as _completion_records,
    completion_routes as _routes,
    prompt_notes as _prompt_notes,
    report_outcome_models as _report_models,
    report_outcomes as _outcomes,
)

# The roads whose developer is asked to describe its task.
_DESCRIBING = frozenset((_routes.CompletionRoute.IMPLEMENTATION, _routes.CompletionRoute.RESUME))


def asked(handoff: _completion_records.CompletionHandoff, prompt: str) -> str:
    """The prompt an attempt on `handoff`'s road is handed: `prompt`, and the task snapshot request where it asks."""
    if handoff.route not in _DESCRIBING:
        return prompt
    return f"{prompt}\n\n{_prompt_notes._TASK_SNAPSHOT_NOTE}"


def receive(
    handoff: _completion_records.CompletionHandoff,
    agent_result: AgentResult,
    stage: str,
    requirements_revision: str,
) -> None:
    """Record the task snapshot a genuine return on `handoff`'s road carries, and leave the workflow its reply.

    `requirements_revision` is what the attempt's prompt was handed. The
    result's message becomes the reply with its attachment lines above the
    outcome taken out, on every return a describing road receives.
    """
    if handoff.route not in _DESCRIBING:
        return
    message = agent_result.last_message or ""
    if _returned(agent_result):
        _recorder.record_task_snapshot(
            _observation_records.ObservedRun(
                invocation=agent_result.invocation,
                stage=stage,
                route=handoff.route.value,
                requirements_revision=requirements_revision or None,
            ),
            _recorder.ObservedReply(message, _framing),
        )
    agent_result.last_message = _workflow_reply(message)


def _returned(agent_result: AgentResult) -> bool:
    """Whether `agent_result` is a reply a tracked run finished, by the run's status alone."""
    shortfalls = (
        agent_result.invocation is None,
        not agent_result.invoked,
        agent_result.interrupted,
        agent_result.timed_out,
        agent_result.exit_code != 0,
        bool(agent_result.unfinished_steps),
        agent_result.terminal_failure is not None,
    )
    return not any(shortfalls)


def _framing(message: str) -> _recorder.Framing:
    """Where `message`'s report outcome begins, and what the report reader reads that outcome as."""
    outcome = _outcomes._parse_report_outcome(message)
    return _recorder.Framing(_outcome_start(message), _outcome_kind(outcome))


def _outcome_kind(outcome: _report_models._ReportOutcome) -> str:
    """`ready` or `verified` for an outcome, and the refusal's own spelling -- `no_marker`, `malformed` -- otherwise."""
    if isinstance(outcome, _report_models._ReadyReport):
        return "ready"
    if isinstance(outcome, _report_models._VerifiedReport):
        return "verified"
    return outcome.value


def _outcome_start(message: str) -> int:
    """Where `message`'s report outcome begins: its first line opening on the report prefix, else its end."""
    marker = _outcomes._MARKER_LINE_RE.search(message)
    return len(message) if marker is None else marker.start()


def _workflow_reply(message: str) -> str:
    """`message` as the workflow reads it: every attachment line above its report outcome taken out."""
    outcome_at = _outcome_start(message)
    above = _attachments.without_attachments(message[:outcome_at])
    outcome = message[outcome_at:]
    return f"{above}{outcome}"
