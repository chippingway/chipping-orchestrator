# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One resume, the single retry behind it, and what each attempt may persist.

A resume is not one agent run: a session whose transcript was garbage-collected
or outgrew the context window fails deterministically, and the only recovery is
to drop the pinned id and spawn fresh in the same worktree. That retry happens
here rather than a tick later so a Claude session GC'd between polls does not
park the issue for two ticks before recovering.

The order the attempts and the writes are in is the contract. The pause check
runs after BOTH runs, because each opens its own live-pause window -- the first
before the retry spawns a second agent, the second before anything is persisted
-- and a fired guard returns before the session id is pinned and before
`awaiting_human` is cleared, so the next tick re-derives the resume from
untouched durable state. The stage the run is attributed to is resolved once, at
build time, and an explicit `stage` wins over the label read off the issue: a
caller that just relabeled (validating -> fixing) names the stage it moved to,
so the attribution does not rest on the `Issue` it hands down -- one that
relabel did not go through would charge the developer's run to the reviewer's
stage.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.agents.models import AgentResult, is_shutdown_sweep_interrupted
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage import protocol as _protocol
from orchestrator.workflow.engine import (
    guards as _guards,
    issue_usage as _issue_usage,
    observations as _observations,
    prompt_notes as _prompt_notes,
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    models as _models,
    resume_request as _resume_request,
    session as _session,
    state as _state,
    worktree as _worktree,
)

log = logging.getLogger("orchestrator.workflow")


@dataclass(frozen=True)
class _DevResumeContext:
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    followup_text: str
    options: _resume_request._DevResumeOptions
    worktree: Path
    plan: _models._DevResumePlan
    stage: str

    @classmethod
    def build(
        cls, request: _resume_request._DevResumeRequest,
    ) -> _DevResumeContext:
        if len(request.resume_args) != 2:
            raise TypeError("expected state and followup_text")
        state, followup_text = request.resume_args
        options = _resume_request._DevResumeOptions.from_fields(request.option_fields)
        worktree = _worktree._ensure_resume_worktree(request.spec, request.issue, state)
        plan = _session._resolve_dev_session_for_resume(request.issue, state)
        return cls(
            gh=request.gh,
            spec=request.spec,
            issue=request.issue,
            state=state,
            followup_text=followup_text,
            options=options,
            worktree=worktree,
            plan=plan,
            stage=request.resolved_stage,
        )

    def execute(self) -> tuple[Path, AgentResult, bool]:
        agent_result, paused = self._run_attempt(
            fresh=self.plan.fresh_spawn,
            session_id=self.plan.session.session_id,
        )
        if paused:
            return self.worktree, agent_result, True
        fresh_spawn = self.plan.fresh_spawn
        if self._needs_fresh_retry(agent_result):
            log.info(
                "issue=#%d dropping poisoned dev session %r after poisoned-session "
                "marker (stale or context overflow); retrying once as a fresh spawn",
                self.issue.number, self.plan.session.session_id,
            )
            _session._drop_poisoned_dev_session(self.state)
            fresh_spawn = True
            agent_result, paused = self._run_attempt(
                fresh=True, session_id=None,
            )
            if paused:
                return self.worktree, agent_result, True
        _session._persist_dev_session_after_run(
            self.state,
            agent_result,
            fresh_spawn=fresh_spawn,
            resume_count=self.plan.resume_count,
        )
        return self.worktree, agent_result, False

    def _run_attempt(
        self, *, fresh: bool, session_id: str | None,
    ) -> tuple[AgentResult, bool]:
        session = self.plan.session
        agent_result = _usage._run_agent_tracked(
            self.gh,
            _run_charge_state.AgentRunBudget(
                issue=self.issue, state=self.state,
            ),
            agent_role="developer",
            stage=self.stage,
            backend=session.backend,
            prompt=_session._build_dev_spawn_prompt(
                self.spec,
                self.issue,
                self.followup_text,
                self.options,
                fresh=fresh,
            ),
            cwd=self.worktree,
            agent_spec=session.spec,
            resume_session_id=session_id,
            extra_args=session.extra_args,
            review_round=self.state.get("review_round", 0),
            retry_count=self.state.get(_state._RETRY_COUNT),
        )
        _issue_usage._accumulate_issue_usage(self.state, agent_result.usage)
        paused = (
            self.options.pause_guard
            and _guards._paused_during_agent_run(self.gh, self.issue)
        )
        return agent_result, paused

    def _needs_fresh_retry(self, agent_result: AgentResult) -> bool:
        """Whether a poisoned session earns this issue a second spawn.

        Not while a poll has this issue latched closed. The retry exists so a
        session GitHub's own transcript lost does not cost the issue a park,
        and an issue somebody has closed is owed neither: it is a second
        agent, on somebody's repository, against work nobody wants. The
        reading costs no request, and the poisoned session id is left where it
        is -- dropping it is what authorizes the retry, and there is no retry.
        """
        if not (
            self.plan.session.session_id is not None
            and not self.plan.fresh_spawn
            and _session._is_poisoned_session_failure(
                self.plan.session.backend, agent_result,
            )
        ):
            return False
        if not _observations.close_observed(
            self.spec.slug, self.issue.number,
        ):
            return True
        log.warning(
            "repo=%s issue=#%d was observed closed by a poll while its "
            "developer ran; not retrying the poisoned session as a second "
            "fresh spawn", self.spec.slug, self.issue.number,
        )
        return False


def _is_incomplete_agy_result(backend: str, agent_result: AgentResult) -> bool:
    """True when an AGY run completed its process with unfinished tool steps."""
    return backend == _protocol.AGY and bool(agent_result.unfinished_steps)


def _should_recover_incomplete_agy(
    backend: str,
    agent_result: AgentResult,
    paused: bool,
) -> bool:
    """Whether an incomplete AGY command outcome earns an immediate continuation.

    Stops recovery on a freshly observed pause, a launch the run circuit
    refused, a shutdown sweep interruption, a process timeout, a missing
    recorded conversation id, or an outcome that is non-AGY or normally
    completed.
    """
    if paused or not agent_result.invoked:
        return False
    if is_shutdown_sweep_interrupted(agent_result) or agent_result.timed_out:
        return False
    return _is_incomplete_agy_result(backend, agent_result) and bool(agent_result.session_id)


@dataclass(frozen=True)
class _DevRunCoordinator:
    _gh: GitHubClient
    _budget: _run_charge_state.AgentRunBudget | None
    _options: dict[str, object]

    def coordinate(self) -> tuple[AgentResult, bool]:
        initial_result = self._options.get("initial_result")
        if initial_result is None:
            agent_result, paused = self._run_agent(
                str(self._options.get("prompt", "")),
                self._options.get("resume_session_id"),
            )
        else:
            agent_result = initial_result
            paused = bool(self._options.get("initial_paused", False))

        backend = str(self._options["backend"])
        if _should_recover_incomplete_agy(backend, agent_result, paused):
            log.info(
                "issue=#%d AGY run ended with unfinished tool steps on session %r; "
                "retrying once with command recovery prompt",
                self._issue().number, agent_result.session_id,
            )
            return self._run_agent(
                _prompt_notes._DEVELOPER_AGY_RECOVERY_PROMPT,
                agent_result.session_id,
            )
        return agent_result, paused

    def _issue(self) -> Issue:
        return self._options["issue"]

    def _state(self) -> PinnedState:
        return self._options["state"]

    def _resolved_budget(self) -> _run_charge_state.AgentRunBudget:
        if self._budget is not None:
            return self._budget
        return _run_charge_state.AgentRunBudget(
            issue=self._issue(),
            state=self._state(),
        )

    def _run_agent(
        self, prompt: str, resume_session_id: str | None,
    ) -> tuple[AgentResult, bool]:
        agent_result = _usage._run_agent_tracked(
            self._gh,
            self._resolved_budget(),
            agent_role="developer",
            stage=self._options["stage"],
            backend=self._options["backend"],
            prompt=prompt,
            cwd=self._options["worktree"],
            agent_spec=self._options.get("agent_spec"),
            resume_session_id=resume_session_id,
            extra_args=self._options.get("extra_args", ()),
            timeout=self._options.get("timeout"),
            review_round=self._options.get(
                "review_round", self._state().get("review_round", 0),
            ),
            retry_count=self._options.get(
                "retry_count", self._state().get(_state._RETRY_COUNT),
            ),
        )
        _issue_usage._accumulate_issue_usage(self._state(), agent_result.usage)
        paused = (
            self._options.get("pause_guard", True)
            and _guards._paused_during_agent_run(self._gh, self._issue())
        )
        return agent_result, bool(paused)


def _coordinate_developer_run(
    gh: GitHubClient,
    budget: _run_charge_state.AgentRunBudget | None = None,
    **kwargs: object,
) -> tuple[AgentResult, bool]:
    """Execute or recover a developer run with bounded AGY command continuation.

    Recognizes the structured AGY incomplete-command outcome and permits at
    most one immediate automatic continuation of the recorded conversation.
    The continuation prompt instructs AGY to inspect the interrupted command,
    rerun cancelled or partial verification where needed, and continue the
    current implementation or fix rather than treating prior output as success.

    Every continuation invokes `_run_agent_tracked` with the same issue
    budget, worktree, backend spec, stage attribution, timeout behavior, and
    conversation id. A missing conversation, timeout, shutdown interruption,
    never-invoked run-budget refusal, or freshly observed pause stops recovery.
    A second premature exit returns the structured failure for child 3 to park.
    No loop or direct backend/subprocess call is made.
    """
    return _DevRunCoordinator(gh, budget, kwargs).coordinate()


_coordinate_agy_recovery = _coordinate_developer_run
