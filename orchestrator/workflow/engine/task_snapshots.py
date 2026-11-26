# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Ask an implementing developer for a task snapshot, and hand the one it returns to analytics.

Who is asked is decided by the road a report-producing attempt was frozen
on, and only two roads ask: the first implementation, and an implementing
resume -- a human's reply or an operator's `/orchestrator continue` --
which are the initial implementation request and its ordinary
continuations (`CompletionRoute.IMPLEMENTATION`, `RESUME`). Every attempt
the shared developer coordinator makes on either road, a poisoned
session's fresh retry and an Antigravity command recovery included, is
handed the request (`asked`) and has its return observed (`observe`). A fix
round, a drift resume, a refresh, a late revision, a documentation pass,
and every run that freezes no road are neither.

The request is `prompt_notes._TASK_SNAPSHOT_NOTE`, appended to the prompt
the attempt is handed. What is observed is a genuine return alone: a run
that was invoked under a tracked charge and completed -- the run-level
refusals the report reader asks first (`report_outcomes`) skipped, since
none of them carries a reply anybody finished. A run that never started, a
synthesized result, and the recovery that finishes a captured report from
its record are no return at all, and observe nothing.

The snapshot is bound to the requirements revision the road froze before
the launch -- the reading the prompt was built from, never one an edit
during the run moved the issue to -- and to the invocation the tracked
spawn stamped on the result. Where the reply's report outcome begins is the
report reader's own pattern's answer (`_outcome_start`), handed to the
recorder to ask inside its failure boundary, so the attachment is read only
above the outcome and one past it is never taken out of a report the
workflow publishes. Nothing here reads the observation back, and its
recording raises nothing into the attempt it observes.
"""
from __future__ import annotations

from orchestrator.agents.models import AgentResult
from orchestrator.observability.analytics.observations import recorder as _recorder, records as _observation_records
from orchestrator.workflow.engine import (
    completion_records as _completion_records,
    completion_routes as _routes,
    prompt_notes as _prompt_notes,
    report_outcome_models as _report_models,
    report_outcomes as _outcomes,
)

# The roads whose developer is asked to describe its task.
_DESCRIBING = frozenset((_routes.CompletionRoute.IMPLEMENTATION, _routes.CompletionRoute.RESUME))

# The refusals that are a run falling short rather than a reply it finished.
_UNFINISHED = frozenset(_report_models._ReportRefusal) - {
    _report_models._ReportRefusal.NO_MARKER, _report_models._ReportRefusal.MALFORMED,
}


def asked(handoff: _completion_records.CompletionHandoff, prompt: str) -> str:
    """The prompt an attempt on `handoff`'s road is handed: `prompt`, and the task snapshot request where it asks."""
    if handoff.route not in _DESCRIBING:
        return prompt
    return f"{prompt}\n\n{_prompt_notes._TASK_SNAPSHOT_NOTE}"


def observe(handoff: _completion_records.CompletionHandoff, agent_result: AgentResult, stage: str) -> None:
    """Record the task snapshot a genuine return on `handoff`'s road carries, or why it carries none."""
    if handoff.route not in _DESCRIBING or not _returned(agent_result):
        return
    _recorder.record_task_snapshot(
        _observation_records.ObservedRun(
            invocation=agent_result.invocation,
            stage=stage,
            route=handoff.route.value,
            requirements_revision=handoff.requirements_revision or None,
        ),
        _recorder.ObservedReply(agent_result.last_message or "", _outcome_start),
    )


def _returned(agent_result: AgentResult) -> bool:
    """Whether `agent_result` is a reply a tracked run finished.

    Not where no tracked spawn stamped it, where the backend left tool steps
    unfinished or normalized the run to a failure, or where the report
    reader refuses the run before reading its message.
    """
    if agent_result.invocation is None or agent_result.unfinished_steps:
        return False
    if agent_result.terminal_failure is not None:
        return False
    return _outcomes._report_outcome_of_run(agent_result) not in _UNFINISHED


def _outcome_start(message: str) -> int:
    """Where `message`'s report outcome begins: its first line opening on the report prefix, else its end."""
    marker = _outcomes._MARKER_LINE_RE.search(message)
    return len(message) if marker is None else marker.start()
