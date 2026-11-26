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
the attempt is handed. Receiving a return does three things. A genuine one --
a run the tracked spawn started and stamped, which completed on its own
terms by its status alone: invoked, neither interrupted nor timed out,
exiting 0, and leaving no tool step unfinished or failure normalized -- is
handed to the analytics recorder with its invocation, the requirements its
conversation was handed (`task_snapshot_grounding`), the revision the run's
report is stamped with -- the road's own, which spells the task reference a
reviewer of that report is told -- and the report reader's framing of the
reply (`_framing`), which the recorder asks inside its own failure boundary;
nothing about the reply is read here first. A run that never started, a
synthesized result, and the recovery that finishes a captured report from
its record are no return and record nothing. Where the conversation was
handed something other than the baseline the issue records, that grounding
is staged on the pinned state for the continuations that resume it.

And every return on these roads, genuine or not, leaves the workflow the
reply it reads: every attachment line but those past the outcome's last
marker line -- above the outcome, and inside a report block -- is taken out
of the result's message (`_workflow_reply`), so a reply carrying nothing
else reads as silent, no park or notice quotes the line, and the report the
workflow publishes, and the digest it is identified by, are what they would
be without it. Lines past the outcome stay, so the report reader still
refuses text after an outcome. A reply nothing can take the line out of is
read as written, with one warning. Nothing here reads an observation back,
and recording one raises nothing into the attempt it observes.
"""
from __future__ import annotations

import logging
from types import MappingProxyType

from orchestrator.agents.models import AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.analytics.observations import (
    attachments as _attachments,
    recorder as _recorder,
    records as _observation_records,
)
from orchestrator.workflow import state as _workflow_state
from orchestrator.workflow.engine import (
    completion_records as _completion_records,
    completion_routes as _routes,
    prompt_notes as _prompt_notes,
    report_outcome_models as _report_models,
    report_outcomes as _outcomes,
    task_snapshot_grounding as _grounding,
)

log = logging.getLogger("orchestrator.workflow")

# What an outcome the report reader accepts is read as.
_OUTCOME_KINDS = MappingProxyType({_report_models._ReadyReport: "ready", _report_models._VerifiedReport: "verified"})

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
    state: PinnedState,
    resumed: str | None,
    fresh_requirements: str | None,
) -> None:
    """Record the task snapshot a genuine return on `handoff`'s road carries, and leave the workflow its reply.

    The snapshot is bound to what the attempt's conversation was handed
    (`task_snapshot_grounding.handed`): `resumed` is the conversation the
    coordinated run resumed, None for a fresh one, and `fresh_requirements`
    what the road re-grounds a fresh one with apart from its handoff. Where
    that is not the baseline the issue records, the conversation's grounding
    is kept for its continuations. The snapshot is attributed to the stage
    the road reports under, and the result's message becomes the reply the
    workflow reads.
    """
    if handoff.route not in _DESCRIBING:
        return
    handed = _grounding.handed(state, resumed, fresh_requirements, handoff.requirements_revision)
    message = agent_result.last_message or ""
    if _returned(agent_result):
        _recorder.record_task_snapshot(
            _observation_records.ObservedRun(
                invocation=agent_result.invocation,
                stage=_workflow_state.stage_name(handoff.origin),
                route=handoff.route.value,
                requirements_revision=handed or None,
                report_requirements=handoff.requirements_revision or None,
            ),
            _recorder.ObservedReply(message, _framing),
        )
    _grounding.remember(state, agent_result.session_id, handed)
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
    """Where `message`'s report outcome begins, and what the report reader reads that outcome as.

    `ready` or `verified` for an outcome, and the refusal's own spelling --
    `no_marker`, `malformed` -- otherwise.
    """
    outcome = _outcomes._parse_report_outcome(message)
    kind = _OUTCOME_KINDS.get(type(outcome)) or outcome.value
    return _recorder.Framing(_outcome_start(message), kind)


def _outcome_start(message: str) -> int:
    """Where `message`'s report outcome begins: its first line opening on the report prefix, else its end."""
    marker = _outcomes._MARKER_LINE_RE.search(message)
    return len(message) if marker is None else marker.start()


def _workflow_reply(message: str) -> str:
    """`message` as the workflow reads it; as written, where nothing can take the attachment out of it."""
    try:
        return _stripped(message)
    except Exception as error:  # noqa: BLE001 - a reply the attachment cannot be taken out of is read as written
        log.warning(
            "could not take a task snapshot attachment out of a developer reply (%s); reading it as written",
            type(error).__name__,
        )
        return message


def _stripped(message: str) -> str:
    """`message` with every attachment line taken out but those past its report outcome's last marker line."""
    markers = tuple(_outcomes._MARKER_LINE_RE.finditer(message))
    kept_from = markers[-1].end() if markers else len(message)
    above = _attachments.without_attachments(message[:kept_from])
    trailing = message[kept_from:]
    return f"{above}{trailing}"
