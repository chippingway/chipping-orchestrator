# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which rejected initial decomposer answer earns a manifest correction, and how its conversation is resumed.

Only one kind of answer earns one (`earned`): the authoritative manifest
parser's concrete parse or structural error over a run that completed --
invoked, not interrupted, not timed out, a zero exit with no terminal failure
or unfinished step -- whose usage is accounted and whose checkout the caller
already proved read-only, that is no correction's own answer, and that saved a
conversation the pinned command can resume (`resumable`). A question or
silence parses to no error, and a failed or incomplete return, a timeout, an
interruption, or a dirty checkout never reaches the parser as a completed run,
so each keeps the disposition it always had, and so does a run with no
session to resume or a command that does not parse: the ordinary park is the
actionable one, never a fresh decomposition spawned in its place.

The error is asked of the parser again rather than carried from the caller,
so nothing but that refusal of the run's own final answer is what a
correction is handed. The requirements are the baseline the record carries
once the run's own settlement is staged -- the revision a frozen read handed
it, or the one the drift check measured its tick by -- since the arming is
held to that baseline reading as this very digest.

The launch it buys (`resumed`) is that saved session resumed under the pinned
command -- backend and arguments alike, whatever `DECOMPOSE_AGENT` says now --
in the issue's read-only decompose checkout the session was opened in, handed
the exact error and the whole output contract
(`engine/decomposition_prompts._build_correction_prompt`), and identified by
nothing that moves between ticks, so a charge it reserved is its own to start
on any later tick.
"""
from __future__ import annotations

import logging
from typing import NoReturn

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import environment as _environment, models as _config_models
from orchestrator.git.worktrees import decomposition as _worktree_decomposition
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    decomposition_prompts as _prompts,
    drift as _engine_drift,
    run_requests as _run_requests,
)
from orchestrator.workflow.stages.decomposition import (
    correction_records as _records,
    manifest as _manifest,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.models import _DecomposerRunPlan

log = logging.getLogger("orchestrator.workflow")

# What a correction's launch is charged and attributed under: the initial
# decomposition's own stage and role, since it is that decomposition's answer.
STAGE = "decomposing"
_ROLE = "decomposer"


def earned(issue: Issue, state: PinnedState, run_plan: _DecomposerRunPlan) -> _records.CorrectionSource | None:
    """The rejected run `run_plan` describes, as the attempt it earns is armed for; None where it earns none."""
    run = run_plan.agent_result
    if run_plan.correction is not None or not _completed(run):
        return None
    parsed, diagnostic = _manifest._parse_manifest(run.last_message or "")
    if parsed is not None or diagnostic is None:
        return None
    saved = _saved(state)
    if saved is None:
        log.info("issue=#%d its rejected manifest saved no conversation to correct; parking it", issue.number)
        return None
    return _records.CorrectionSource(run.invocation, state.get(_engine_drift._USER_CONTENT_HASH), *saved, diagnostic)


def resumable(command: str) -> tuple[str, tuple[str, ...]] | None:
    """The backend and arguments a pinned decomposer `command` resumes under, or None where it parses to none."""
    try:
        return _environment.parse_agent_spec(_state._DECOMPOSER_AGENT, command, _refuse)
    except ValueError:
        return None


def resumed(
    spec: _config_models.RepoSpec, issue: Issue, source: _records.CorrectionSource,
) -> _run_requests._AgentRunRequest:
    """`source`'s saved session resumed under its pinned command, in the issue's read-only checkout, asked to correct.

    The command is one its arming, or the reconciliation launching it on a
    later tick, already found `resumable`. The request names no retry count:
    its launch is that saved session under that command, whichever tick and
    daily window launch it, so a charge it reserved and never started is the
    same launch's to start (`run_requests._AgentRunRequest.fingerprint`) after
    the window rolls over, never a second charge beside it.
    """
    backend, extra_args = resumable(source.command)
    checkout = _worktree_decomposition._decompose_worktree_path(spec, issue.number)
    if not checkout.exists():
        checkout = _worktree_decomposition._ensure_decompose_worktree(spec, issue.number)
    return _run_requests._AgentRunRequest(
        agent_role=_ROLE,
        stage=STAGE,
        backend=backend,
        prompt=_prompts._build_correction_prompt(source.diagnostic),
        cwd=checkout,
        agent_spec=source.command,
        resume_session_id=source.session,
        extra_args=extra_args,
    )


def _saved(state: PinnedState) -> tuple[str, str] | None:
    """The pinned decomposer command and session a correction would resume, or None where either is no resumable one."""
    command = state.get(_state._DECOMPOSER_AGENT)
    session = state.get(_state._DECOMPOSER_SESSION_ID)
    if not isinstance(command, str) or not isinstance(session, str):
        return None
    return None if resumable(command) is None else (command, session)


def _completed(run: AgentResult) -> bool:
    """Whether `run` is a completed, accounted process whose answer is its own to stand by."""
    if not run.invoked or run.interrupted or run.timed_out:
        return False
    if run.exit_code != 0 or run.terminal_failure is not None or run.unfinished_steps:
        return False
    return not run.unaccounted and run.invocation is not None


def _refuse(message: str) -> NoReturn:
    """Raise where the pinned command does not parse, rather than abort the process as a setting would."""
    raise ValueError(message)
