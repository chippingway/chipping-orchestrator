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
the attempt is handed. Receiving a return reads where the analytics sink is
first (`recorder.sink_path`), and with the sink off records nothing and
keeps no grounding. With it on, a genuine return -- a run the tracked spawn
started and stamped, which completed on its own terms by its status alone:
invoked, neither interrupted nor timed out, exiting 0, and leaving no tool
step unfinished or failure normalized -- is handed to the analytics recorder
with its invocation, the requirements its conversation was handed
(`task_snapshot_grounding`), the revision the run's report is stamped with
-- the road's own, which spells the task reference a reviewer of that report
is told -- and the framing of the reply the workflow reads
(`task_snapshot_replies.framing`), which the recorder asks inside its own
failure boundary; nothing about the reply is read here first. A run that
never started, a synthesized result, and the recovery that finishes a
captured report from its record are no return and record nothing. Every
attempt, genuine or not, then keeps the host's grounding record current for
the retries that may resume its conversation.

And every return on these roads, with the sink on or off, leaves the
workflow the reply it reads (`task_snapshot_replies.workflow_reply`): its
attachment lines kept out of it without moving its framing, so no park,
notice, or published report carries one, and the report verdict is the one
the recorder was told. Nothing here reads an observation back, and
recording one raises nothing into the attempt it observes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from orchestrator.agents.models import AgentResult
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.analytics.observations import (
    recorder as _recorder,
    records as _observation_records,
)
from orchestrator.workflow import state as _workflow_state
from orchestrator.workflow.engine import (
    completion_records as _completion_records,
    completion_routes as _routes,
    prompt_notes as _prompt_notes,
    task_snapshot_grounding as _grounding,
    task_snapshot_replies as _replies,
)

log = logging.getLogger("orchestrator.workflow")

# The roads whose developer is asked to describe its task.
_DESCRIBING = frozenset((_routes.CompletionRoute.IMPLEMENTATION, _routes.CompletionRoute.RESUME))


@dataclass(frozen=True)
class Conversation:
    """The conversation one attempt ran in, as its road knows it.

    `repo_id` and `issue_number` name the issue whose host records keep its
    grounding; `resumed` is the conversation the coordinated run resumed,
    None for a fresh one; `fresh_requirements` is what a retry's road
    re-grounds a fresh conversation with, None on a road that hands its own.
    """

    repo_id: int
    issue_number: int
    resumed: str | None
    fresh_requirements: str | None


def asked(handoff: _completion_records.CompletionHandoff, prompt: str) -> str:
    """The prompt an attempt on `handoff`'s road is handed: `prompt`, and the task snapshot request where it asks."""
    if handoff.route not in _DESCRIBING:
        return prompt
    return f"{prompt}\n\n{_prompt_notes._TASK_SNAPSHOT_NOTE}"


def receive(
    handoff: _completion_records.CompletionHandoff,
    agent_result: AgentResult,
    state: PinnedState,
    conversation: Conversation,
) -> None:
    """Record the task snapshot a genuine return on `handoff`'s road carries, and leave the workflow its reply.

    The snapshot is bound to what `conversation` was handed
    (`task_snapshot_grounding.Grounding.handed`) and attributed to the stage
    the road reports under; the result's message becomes the reply the
    workflow reads.
    """
    if handoff.route not in _DESCRIBING:
        return
    path = _recorder.sink_path()
    if path is not None:
        try:
            _observe(handoff, agent_result, conversation, _grounding.Grounding.of(
                conversation.repo_id, conversation.issue_number, state,
            ), path)
        except Exception as error:  # noqa: BLE001 - an observation is lost, never the run that returned it
            log.warning(
                "issue=#%d could not observe a developer reply's task snapshot (%s)",
                conversation.issue_number, type(error).__name__,
            )
    if agent_result.last_message:
        agent_result.last_message = _replies.workflow_reply(agent_result.last_message)


def _observe(
    handoff: _completion_records.CompletionHandoff,
    agent_result: AgentResult,
    conversation: Conversation,
    grounding: _grounding.Grounding,
    path: Path,
) -> None:
    """Record a genuine return's snapshot on the sink at `path`, and keep the conversation's grounding current."""
    handed = grounding.handed(conversation.resumed, conversation.fresh_requirements, handoff.requirements_revision)
    if _returned(agent_result):
        run = _observation_records.ObservedRun(
            invocation=agent_result.invocation,
            stage=_workflow_state.stage_name(handoff.origin),
            route=handoff.route.value,
            requirements_revision=handed or None,
            report_requirements=handoff.requirements_revision or None,
        )
        reply = _recorder.ObservedReply(agent_result.last_message or "", _replies.framing)
        _recorder.record_task_snapshot(run, reply, path)
    grounding.remember(agent_result.session_id or conversation.resumed, handed)


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
