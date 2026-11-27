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

The request is `prompt_notes._TASK_SNAPSHOT_NOTE`, appended to the prompt the
attempt is handed. Receiving a return reads where the analytics sink is first
(`recorder.sink_path`), and with the sink off records nothing and keeps no
grounding. With it on, a genuine return -- a run the tracked spawn started
and stamped that reached the agent, and completed on its own terms -- is
handed to the analytics recorder. Reaching the agent means invoked, with
neither the provider nor the CLI refusing the turn: not a provider refusal
(`provider_failures.is_provider_refusal`, which settles that from the
backend's own verdict where there is one) nor a Codex turn that ended on
`turn.failed`, both read off the stream's records that decode at all, so a
record the usage parser refuses hides no closing event and the observation
stands on no usage parse; and not a return the launching stage reads as its
CLI's own refusal -- a conversation the CLI could not open or whose
transcript overflowed, or an exhausted quota -- which that stage classifies
with the readers it parks and retries on and hands in as `refused`, asked
inside the failure boundary below. Completing on its own terms means neither
interrupted nor timed out, exiting 0, and leaving no tool step unfinished or
failure normalized. The recorder is handed it with its invocation, the
requirements its conversation was handed (`task_snapshot_grounding`), the
repository the run's report is published under and the revision it is stamped
with -- the road's own, which spell the task reference a reviewer of that
report is told -- and the framing of the reply the workflow reads
(`task_snapshot_replies.framing`), which the recorder asks inside its own
failure boundary; nothing about the reply is read here first. A run that
never started, a synthesized result, and the recovery that finishes a
captured report from its record are no return and record nothing. Every
attempt that reached the agent, genuine or not, then keeps the host's
grounding record current for the retries that may resume its conversation; a
launch refused before it started, or a turn the provider or the CLI refused,
handed the conversation nothing, and leaves the record as it stands.

And every return on these roads, with the sink on or off, leaves the
workflow the reply it reads (`task_snapshot_replies.workflow_reply`): its
attachment lines kept out of it without moving its framing, so no park,
notice, or published report carries one, and the report verdict is the one
the recorder was told. Nothing here reads an observation back, and
recording one raises nothing into the attempt it observes.
"""
from __future__ import annotations

import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from orchestrator.agents import (
    codex_events as _codex_events,
    models as _agent_models,
    provider_failures as _provider_failures,
)
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
    grounding; `resumed` is the conversation the attempt's own launch
    resumed -- an Antigravity command recovery's the one the attempt before
    it returned -- None for a fresh one; `fresh_requirements` fingerprints what a retry's
    road re-grounds a fresh conversation with, asked only for such an
    attempt, None on a road that hands its own; and `repository` is the
    repository as configured -- the one the run's
    report is published under, which its settled record keeps -- and spells
    the task reference.
    """

    repo_id: int
    issue_number: int
    resumed: str | None
    fresh_requirements: _grounding.Fingerprint | None
    repository: str


def asked(handoff: _completion_records.CompletionHandoff, prompt: str) -> str:
    """The prompt an attempt on `handoff`'s road is handed: `prompt`, and the task snapshot request where it asks."""
    if handoff.route not in _DESCRIBING:
        return prompt
    return f"{prompt}\n\n{_prompt_notes._TASK_SNAPSHOT_NOTE}"


def receive(
    handoff: _completion_records.CompletionHandoff,
    agent_result: _agent_models.AgentResult,
    state: PinnedState,
    conversation: Conversation,
    *,
    refused: Callable[[], bool],
) -> None:
    """Record the task snapshot a genuine return on `handoff`'s road carries, and leave the workflow its reply.

    The snapshot is bound to what `conversation` was handed
    (`task_snapshot_grounding.Grounding.handed`) and attributed to the stage
    the road reports under; the result's message becomes the reply the
    workflow reads. `refused` asks the launching stage whether the CLI
    answered the attempt with a refusal of its own: such a return is observed
    nowhere and moves no grounding. It is asked inside the failure boundary,
    and only once the road asks for a snapshot and the sink is on, so a
    reading that fails is a lost observation like any other: warned of once,
    that warning attempted best-effort, so nothing here keeps the reply from
    the workflow.
    """
    if handoff.route not in _DESCRIBING:
        return
    path = _recorder.sink_path()
    if path is not None:
        try:
            # A turn the CLI refused reached no agent, so nothing about it is observed.
            if not refused():
                _observe(handoff, agent_result, conversation, _grounding.Grounding.of(
                    conversation.repo_id, conversation.issue_number, state,
                ), path)
        except Exception as error:  # noqa: BLE001 - an observation is lost, never the run that returned it
            # Attempted once: a logger that fails loses the warning with the
            # observation, never the reply's settlement below.
            with contextlib.suppress(Exception):
                log.warning(
                    "issue=#%d could not observe a developer reply's task snapshot (%s)",
                    conversation.issue_number, type(error).__name__,
                )
    if agent_result.last_message:
        agent_result.last_message = _replies.workflow_reply(agent_result.last_message)


def _observe(
    handoff: _completion_records.CompletionHandoff,
    agent_result: _agent_models.AgentResult,
    conversation: Conversation,
    grounding: _grounding.Grounding,
    path: Path,
) -> None:
    """Keep the conversation's grounding current, then record a genuine return's snapshot on the sink at `path`.

    Only an attempt that reached the agent touches the grounding: one that
    never did was handed nothing, so the conversation it named is grounded
    where it was. The grounding is kept first, so a record the host will not
    read or a change it will not take fails the observation before anything
    is recorded.
    """
    if not _reached(agent_result):
        return
    handed = grounding.handed(conversation.resumed, conversation.fresh_requirements, handoff.requirements_revision)
    grounding.remember(agent_result.session_id or conversation.resumed, handed)
    if _returned(agent_result):
        run = _observation_records.ObservedRun(
            invocation=agent_result.invocation,
            stage=_workflow_state.stage_name(handoff.origin),
            route=handoff.route.value,
            requirements_revision=handed or None,
            report_requirements=handoff.requirements_revision or None,
            report_repository=conversation.repository or None,
        )
        reply = _recorder.ObservedReply(agent_result.last_message or "", _replies.framing)
        _recorder.record_task_snapshot(run, reply, path)


def _reached(agent_result: _agent_models.AgentResult) -> bool:
    """Whether `agent_result`'s launch reached the agent: a process started, its turn neither refused nor failed.

    Refused by the provider as the backend's own verdict says
    (`provider_failures.is_provider_refusal`), or a Codex turn that ended on
    `turn.failed`, whatever its code (`codex_events.codex_turn_failure`) --
    both read off the stream's records that decode at all (`_decodable`).
    The CLI's own refusals are the launching stage's to read, and arrive as
    `receive`'s `refused`.
    """
    if not agent_result.invoked:
        return False
    read = replace(agent_result, stdout=_decodable(agent_result.stdout or ""))
    return not (_provider_failures.is_provider_refusal(read) or _codex_events.codex_turn_failure(read.stdout))


def _decodable(stdout: str) -> str:
    """`stdout` with only its lines JSON decodes at all.

    The terminal readers are handed these alone, so a record the usage parser
    refuses -- an integer past the conversion limit, say -- hides no closing
    event: the observation stands on the stream's terminal evidence, never on
    a usage parse, and a refused or failed turn is still told apart.
    """
    decoded = []
    for line in stdout.splitlines():
        try:
            json.loads(line)
        except (ValueError, RecursionError):
            continue
        decoded.append(line)
    return "\n".join(decoded)


def _returned(agent_result: _agent_models.AgentResult) -> bool:
    """Whether `agent_result`, which reached the agent, is a reply a tracked run finished, by the run's status."""
    shortfalls = (
        agent_result.invocation is None,
        agent_result.interrupted,
        agent_result.timed_out,
        agent_result.exit_code != 0,
        bool(agent_result.unfinished_steps),
        agent_result.terminal_failure is not None,
    )
    return not any(shortfalls)
