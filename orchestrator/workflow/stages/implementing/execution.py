# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One resume, the single retry behind it, and what each attempt may persist.

A resume is not one agent run: a session whose transcript was garbage-collected
or outgrew the context window fails deterministically, and the only recovery is
to drop the pinned id and spawn fresh in the same worktree. That retry happens
here rather than a tick later so a Claude session GC'd between polls does not
park the issue for two ticks before recovering.

The order the attempts and the writes are in is the contract. The command the
plan locked is pinned before the first attempt, as the first spawn pins its
own, so no conversation a resume opens is pinned under no command. The pause
check runs after BOTH runs, because each opens its own live-pause window -- the
first before the retry spawns a second agent, the second before anything is
persisted -- and a fired guard returns before the session id is pinned and
before `awaiting_human` is cleared, so the next tick re-derives the resume from
untouched durable state. Two writes are not left to that. Each attempt's usage
is accounted as it returns, at the tracked boundary ahead of everything here
(`usage._run_agent_tracked`), so a poisoned session's exit is counted though
only its retry is handed back, and an attempt whose accounting stayed
unresolved answers paused, so no retry is spawned behind it. The other is the
retirement of a conversation an exhausted account quota stopped, which every
attempt lands as it returns (`quota_retirement`), ahead of its pause check: a
tick that writes nothing still never resumes it, and the post-run persistence
refuses to pin it again. One the comment would not take answers paused too, so the tick
is held as a pause holds it, and every launch after it -- a restarted poller's
included -- is refused with the run circuit's own answer until a later reading
lands it; the resume plan built here asks first, so a retirement landed then is
one the plan reads, and one that will not land or will not read there keeps
that tick from launching at all. A resume of a conversation the tick's state
records as retired, which only a plan made before that retirement landed can
still name, is refused the same way, and so is an Antigravity launch the host
will not first record as owing its conversation's retirement -- the record its
return clears where no quota stopped it. The stage
the run is attributed to is resolved once,
at build time, and an explicit `stage` wins over the label read off the issue:
a caller that just relabeled (validating -> fixing) names the stage it moved to
-- as does the recovery of a launch a handed request owes, on an issue already
on `fixing` -- so the attribution does not rest on the `Issue` it hands down:
one a relabel did not go through would charge the developer's run to the
reviewer's stage.

What an attempt is charged under is spelled once (`_launch_identity`), so a
reader asking which launch a resume over the pinned state would charge -- a
handed change request's recovery telling that developer's charge from another
road's -- reads it without resuming (`_first_launch_fingerprint`).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.agents.models import AgentResult, is_shutdown_sweep_interrupted
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.observability.usage import protocol as _protocol
from orchestrator.workflow.engine import (
    guards as _guards,
    observations as _observations,
    prompt_notes as _prompt_notes,
    run_charge_state as _run_charge_state,
    run_circuit as _run_circuit,
    run_requests as _run_requests,
    usage as _usage,
)
from orchestrator.workflow.stages.implementing import (
    models as _models,
    quota_retirement as _quota_retirement,
    resume_request as _resume_request,
    session as _session,
    session_retirement as _session_retirement,
    state as _state,
    worktree as _worktree,
)

log = logging.getLogger("orchestrator.workflow")

# The role every attempt here is charged as, and the round it is charged at,
# as the pinned state and the launch both name it.
_DEVELOPER = "developer"

_REVIEW_ROUND = "review_round"

# The launch option naming the backend an attempt runs on.
_BACKEND = "backend"


@dataclass(frozen=True)
class _DevResumeContext:
    request: _resume_request._DevResumeRequest
    worktree: Path
    plan: _models._DevResumePlan
    stage: str
    # The split rationale a FRESH spawn is re-grounded with, read once off the
    # issue's own record as the run is built (`resume_request`). None is a
    # record holding none.
    split_rationale: str | None

    @classmethod
    def build(
        cls, request: _resume_request._DevResumeRequest,
    ) -> _DevResumeContext:
        split_rationale = request.split_rationale
        worktree = _worktree._ensure_resume_worktree(request.spec, request.issue, request.state)
        # A quota retirement an earlier tick could not land is landed ahead of
        # the plan, so the plan reads it. One that still will not land, or will
        # not read, withholds the state, and the coordinator refuses the launch
        # on it -- whatever a second attempt there answers, or an operator
        # does to the record meanwhile -- so this tick, which can no longer
        # record what the launch leads to, makes none.
        _quota_retirement._reconcile(request.gh, request.issue, request.state)
        plan = _session._resolve_dev_session_for_resume(request.issue, request.state)
        return cls(
            request=request,
            worktree=worktree,
            plan=plan,
            stage=request.resolved_stage,
            split_rationale=split_rationale,
        )

    def execute(self) -> tuple[Path, AgentResult, bool]:
        state = self.request.state
        # The command the plan locked is pinned before any attempt, as the
        # first spawn pins its own (`spawn`). Where no `dev_agent` was pinned
        # the plan read the configuration, and a fresh conversation pinned
        # under no command would be resumed by the next reply under whatever
        # the configuration says by then -- if at all, since the session read
        # resolves no conversation without one. A pinned command is rewritten
        # as it reads; a conversation pinned under none, which this plan
        # does not resume, is dropped first.
        _session._pin_dev_command(state, self.plan.session.spec)
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
                self.request.issue.number, self.plan.session.session_id,
            )
            _session._drop_poisoned_dev_session(state)
            fresh_spawn = True
            agent_result, paused = self._run_attempt(
                fresh=True, session_id=None,
            )
            if paused:
                return self.worktree, agent_result, True
        _session._persist_dev_session_after_run(
            state,
            agent_result,
            fresh_spawn=fresh_spawn,
            resume_count=self.plan.resume_count,
            resumed_session_id=self.plan.session.session_id,
        )
        # A resume answers a fresh human signal, so the park it was waiting
        # on is over once the run is back.
        state.set(_state._AWAITING_HUMAN, False)
        return self.worktree, agent_result, False

    def _run_attempt(
        self, *, fresh: bool, session_id: str | None,
    ) -> tuple[AgentResult, bool]:
        session = self.plan.session
        request = self.request
        return _coordinate_developer_run(
            request.gh,
            _run_charge_state.AgentRunBudget(
                issue=request.issue, state=request.state, owed=request.owed,
            ),
            issue=request.issue,
            state=request.state,
            worktree=self.worktree,
            prompt=_session._build_dev_spawn_prompt(request, self.split_rationale, fresh=fresh),
            extra_args=session.extra_args,
            pause_guard=request.pause_guard,
            **_launch_identity(request.state, self.stage, session, session_id),
        )

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
        slug, issue_number = self.request.spec.slug, self.request.issue.number
        if not _observations.close_observed(slug, issue_number):
            return True
        log.warning(
            "repo=%s issue=#%d was observed closed by a poll while its "
            "developer ran; not retrying the poisoned session as a second "
            "fresh spawn", slug, issue_number,
        )
        return False


def _launch_identity(
    state: PinnedState, stage: str, session: _models._DevSession, session_id: str | None,
) -> dict:
    """Every field one developer attempt is fingerprinted by, beside its role."""
    return {
        _BACKEND: session.backend,
        "stage": stage,
        "agent_spec": session.spec,
        "resume_session_id": session_id,
        _REVIEW_ROUND: state.get(_REVIEW_ROUND, 0),
        "retry_count": state.get(_state._RETRY_COUNT),
    }


def _first_launch_fingerprint(state: PinnedState, stage: str) -> str:
    """The fingerprint a resume over `state` charges its first attempt under, read without resuming.

    The session is the one that resume opens with, retired where its budget or
    silent streak is spent (`session._planned_dev_session`), so a reader can
    tell a charge that launch took from another road's.
    """
    session, retired = _session._planned_dev_session(state)
    identity = _launch_identity(state, stage, session, None if retired else session.session_id)
    return _run_requests._AgentRunRequest(agent_role=_DEVELOPER, prompt="", cwd=Path(), **identity).fingerprint


def _is_incomplete_agy_result(backend: str, agent_result: AgentResult) -> bool:
    """True when an AGY run completed its process with unfinished tool steps."""
    return backend == _protocol.AGY and bool(agent_result.unfinished_steps)


def _should_recover_incomplete_agy(
    backend: str,
    agent_result: AgentResult,
    paused: bool,
    state: PinnedState,
) -> bool:
    """Whether an incomplete AGY command outcome earns an immediate continuation.

    Stops recovery on a freshly observed pause or an attempt whose accounting
    is unresolved (both answered `paused`), a launch the run circuit
    refused, a shutdown sweep interruption, a process timeout, an exhausted
    account quota, a missing recorded conversation id, an outcome that is
    non-AGY or normally completed, or a conversation `state` records as retired
    (`session_retirement._held_retirement`). The quota stops it whatever
    unfinished steps it left beside the error: the continuation would resume
    the conversation the quota just retired (`quota_retirement`), on an account
    that cannot run it until the reset. The last is a fresh run handing a
    failed conversation's id back: continuing it would resume the very
    conversation the post-run pin then refuses, with the recovery still owed.
    """
    if paused or not agent_result.invoked:
        return False
    if (
        is_shutdown_sweep_interrupted(agent_result)
        or agent_result.timed_out
        or _quota_retirement._quota_failure(agent_result)
    ):
        return False
    if not (_is_incomplete_agy_result(backend, agent_result) and agent_result.session_id):
        return False
    return agent_result.session_id not in _session_retirement._held_retirement(state)[0]


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
            held = self._held_on_quota(agent_result, self._options.get("resume_session_id"))
            paused = held or agent_result.unaccounted or bool(self._options.get("initial_paused", False))

        backend = str(self._options[_BACKEND])
        if _should_recover_incomplete_agy(backend, agent_result, paused, self._state()):
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
        if self._launch_held(resume_session_id):
            return _run_circuit._refused_run(), False
        agent_result = _usage._run_agent_tracked(
            self._gh,
            self._resolved_budget(),
            agent_role=_DEVELOPER,
            stage=self._options["stage"],
            backend=self._options[_BACKEND],
            prompt=prompt,
            cwd=self._options["worktree"],
            agent_spec=self._options.get("agent_spec"),
            resume_session_id=resume_session_id,
            extra_args=self._options.get("extra_args", ()),
            timeout=self._options.get("timeout"),
            review_round=self._options.get(
                _REVIEW_ROUND, self._state().get(_REVIEW_ROUND, 0),
            ),
            retry_count=self._options.get(
                "retry_count", self._state().get(_state._RETRY_COUNT),
            ),
        )
        paused = self._held_on_quota(agent_result, resume_session_id) or agent_result.unaccounted or (
            self._options.get("pause_guard", True)
            and _guards._paused_during_agent_run(self._gh, self._issue())
        )
        return agent_result, bool(paused)

    def _launch_held(self, resume_session_id: str | None) -> bool:
        """Whether this launch is not to be made, for a quota retirement or for the conversation it resumes.

        Answered with the run circuit's own refusal (`_refused_run`), which
        every caller already returns on without writing, and asked before the
        circuit charges anything: no run was made. A quota retirement no
        commit has confirmed, or the host still owes, holds it, and a tick
        whose state is withheld makes no launch at all, even where a later
        attempt lands the retirement (`quota_retirement._holds_the_launch`).
        Once whatever was owed has landed on the tick's state, a resume of a
        conversation that state records as retired is refused too: only a
        plan made before the retirement landed still names it, and the run
        would be the very conversation the record retires. Last, an
        Antigravity launch -- the one backend whose failure record says
        whether a quota stopped it -- owes the retirement of the conversation
        it runs on the host before it is made (`quota_retirement._armed`), and
        is held where the host will not take that.
        """
        state = self._state()
        if _quota_retirement._holds_the_launch(self._gh, self._issue(), state):
            return True
        if resume_session_id in _session_retirement._held_retirement(state)[0]:
            log.warning(
                "issue=#%d refusing to resume dev session %r, which the pinned state records as retired",
                self._issue().number, resume_session_id,
            )
            return True
        if self._options[_BACKEND] != _protocol.AGY:
            return False
        return not _quota_retirement._armed(self._gh, self._issue(), resume_session_id)

    def _held_on_quota(self, agent_result: AgentResult, launched: str | None) -> bool:
        """Retire the conversation an attempt ran -- `launched` where it names none -- if a quota stopped it.

        Asked of every attempt as it returns, ahead of its pause check: a
        caller honoring a pause writes nothing, which is why the retirement
        lands apart from that caller's write. True where it could not be
        confirmed, which holds the tick exactly as a live pause does -- the
        caller writing nothing over the comment the commit was refused on.
        """
        return not _quota_retirement._retire_quota_conversation(
            self._gh, self._issue(), self._state(), agent_result, launched,
        )


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
    conversation id. A missing or retired conversation, timeout, shutdown
    interruption, never-invoked run-budget refusal, exhausted account quota,
    or freshly observed pause stops recovery.
    A second premature exit returns the structured failure for child 3 to park.
    No loop or direct backend/subprocess call is made.

    Each attempt is its own invocation, accounted as it returns at the tracked
    boundary (`usage._run_agent_tracked`), so the first of two attempts is
    counted though only the second is handed back. An attempt whose accounting
    is unresolved (`AgentResult.unaccounted`) answers held, as a live pause
    does: no continuation is made behind it, and the caller disposes of
    nothing.

    Every attempt -- the first, handed in or run here, and the continuation
    -- is the developer result boundary an account quota is decided at: the
    conversation the attempt ran, or the one it was launched to resume where
    the failure named none, is retired durably before the attempt is handed
    back (`quota_retirement`), so no later launch on any road resumes it and
    neither post-run persistence pins it again. A retirement the comment would
    not take answers paused, withholding the caller's state from its
    whole-state write, and is owed from a record the host keeps: each launch
    made here after it answers the run circuit's refusal, uncharged, until the
    retirement lands -- and on a tick whose state is withheld, after it lands
    too. So does a resume of a conversation the state records as retired, and
    an Antigravity launch the host will not first record as owing the
    retirement of the conversation it runs, which the attempt's return clears
    where no quota stopped it.
    """
    return _DevRunCoordinator(gh, budget, kwargs).coordinate()
