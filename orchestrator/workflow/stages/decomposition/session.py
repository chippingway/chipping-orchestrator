# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The decomposer session an issue is locked to: taken, resumed, and retired.

A resume has to land on the backend that opened the session -- there is no
bridge between a codex session id and a claude one -- so the agent spec is
pinned on the issue at the first spawn, before the spawn can fail, and read
back from there on every later tick whatever the current `DECOMPOSE_AGENT`
says. That lock is what makes an env flip safe to do while issues are in
flight, and writing it early is what keeps a backend that returned no session
id from leaving the issue unattributed.

A human reply resumes the session with the new comments quoted, and two
callers outside this owner retire it instead. The drift reset does, because a
conversation held against the body the human has since rewritten answers a
question nobody is asking any more. The continuation that lifts a spent-budget
park does too, and there a reply resumes nothing at all: what a trusted
`/orchestrator continue` buys is the fresh spawn the budget refused, so the
conversation that ran out is not the one it pays for.

Both retire through one step, and only the session id. The locked spec must
outlive either reset for the same reason it exists, and the retirement is
separate from the run that follows it because that run cannot do it: a spawn
records an id only where the backend hands one back, so a question or a
timeout that surfaced none would leave the retired conversation resumable.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import decomposition as _worktree_decomposition
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    decomposition_prompts as _decomposition_prompts,
    prompt_context as _prompt_context,
    retry_budget as _retry_budget,
    run_charge_state as _run_charge_state,
    usage as _usage,
)
from orchestrator.workflow.stages.decomposition import state as _state
from orchestrator.workflow.stages.decomposition.models import _DecomposerSession

# What this stage's spawns are charged and attributed under. The budget is
# shared with implementing, so the name is what tells a park taken here from
# one taken there.
_DECOMPOSING_STAGE = "decomposing"


def _read_decomposer_session(
    state: PinnedState,
) -> tuple[str, str, tuple[str, ...], str | None]:
    """Return (spec, backend, extra_args, decomposer_session_id) for an issue.

    Mirrors `_read_dev_session`: `spec` is the full configured agent
    command string the next run will use, returned so callers can
    persist it verbatim BEFORE invoking `run_agent` -- a fresh
    decomposer that produces a manifest without surfacing a session id
    (a backend hiccup in the JSONL output, an empty `-o` file) would
    otherwise leave `decomposer_agent` unset and a later
    `DECOMPOSE_AGENT` env flip could retarget the awaiting-human
    resume at a backend that never ran on this issue.

    Legacy bare-backend values (`"codex"` / `"claude"`) re-parse to
    `(backend, ())` and round-trip cleanly. When the issue has never
    been spawned, returns the current config's
    `(DECOMPOSE_AGENT_SPEC, DECOMPOSE_AGENT, DECOMPOSE_AGENT_ARGS, None)`.
    """
    stored = state.get("decomposer_agent")
    if stored:
        spec = str(stored)
        backend, args = config._parse_agent_spec("decomposer_agent", spec)
        sid = state.get("decomposer_session_id")
        return spec, backend, args, None if sid is None else str(sid)
    return (
        config.DECOMPOSE_AGENT_SPEC,
        config.DECOMPOSE_AGENT,
        config.DECOMPOSE_AGENT_ARGS,
        None,
    )


def _spawn_fresh_decomposer(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
) -> AgentResult | None:
    """Consume a retry slot and spawn a fresh decomposer session.

    Returns the agent result, or None when the retry budget is exhausted. The
    shared parking form has already taken the park and said what it is for by
    then, so the caller returns; the write below is what commits a park it
    found already standing, which that form deliberately leaves undone.
    """
    if not _retry_budget._charge_or_park(
        gh, issue, state, stage=_DECOMPOSING_STAGE,
    ):
        gh.write_pinned_state(issue, state)
        return None
    wt = _worktree_decomposition._ensure_decompose_worktree(spec, issue.number)
    session = _DecomposerSession(*_read_decomposer_session(state))
    # Persist the spec BEFORE the spawn so a backend hiccup
    # that yields no `session_id` -- yet still produces a
    # manifest in the worktree or parks awaiting human -- does
    # not leave `decomposer_agent` unset. A later
    # `DECOMPOSE_AGENT` flip would otherwise retarget the next
    # awaiting-human resume at a backend that never ran on
    # this issue. Storing the parsed backend alone would also
    # strip configured CLI args on subsequent resumes.
    state.set("decomposer_agent", session.spec)
    decomposer_result = _usage._run_agent_tracked(
        gh, _run_charge_state.AgentRunBudget(issue=issue, state=state),
        agent_role="decomposer",
        stage="decomposing",
        backend=session.backend,
        prompt=_decomposition_prompts._build_decompose_prompt(
            spec, issue, _prompt_context._recent_comments_text(issue),
            config.default_repo_specs(),
        ),
        cwd=wt,
        agent_spec=session.spec,
        extra_args=session.extra_args,
        retry_count=state.get("retry_count"),
    )
    if decomposer_result.session_id:
        state.set("decomposer_session_id", decomposer_result.session_id)
    return decomposer_result


def _decomposer_followup(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> str | None:
    comments = filter_trusted(
        gh.comments_after(issue, state.get(_state._LAST_ACTION_COMMENT_ID))
    )
    if not comments:
        return None
    state.set(
        _state._LAST_ACTION_COMMENT_ID,
        max(comment.id for comment in comments),
    )
    return "\n\n".join(
        _prompt_context._quote_comment_line(comment)
        for comment in comments if comment.body
    )


def _resume_decomposer_on_human_reply(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState
) -> AgentResult | None:
    """Resume the decomposer's locked-backend session with new comments.

    Returns the agent result, or None if there are no new comments since
    the last park (caller should return without writing state).

    Mirrors `_resume_developer_on_human_reply` but on the decomposer
    session. The backend is locked to whichever wrote
    `decomposer_session_id`; resuming across backends would need an
    inter-backend session bridge that does not exist.
    """
    followup = _decomposer_followup(gh, issue, state)
    if followup is None:
        return None
    wt = _worktree_decomposition._decompose_worktree_path(spec, issue.number)
    if not wt.exists():
        wt = _worktree_decomposition._ensure_decompose_worktree(
            spec, issue.number,
        )
    session = _DecomposerSession(*_read_decomposer_session(state))
    decomposer_result = _usage._run_agent_tracked(
        gh, _run_charge_state.AgentRunBudget(issue=issue, state=state),
        agent_role="decomposer",
        stage="decomposing",
        backend=session.backend,
        prompt=followup,
        cwd=wt,
        agent_spec=session.spec,
        resume_session_id=session.session_id,
        extra_args=session.extra_args,
        retry_count=state.get("retry_count"),
    )
    state.set(_state._AWAITING_HUMAN, False)
    return decomposer_result


def _retire_decomposer_session(state: PinnedState) -> None:
    """Drop the session id, so the next spawn opens a conversation of its own.

    The spec (`decomposer_agent`) is deliberately left where it is: what is
    retired here is a transcript, not the backend choice locked on this issue,
    and a fresh spawn has to land on the same CLI the pinned session id was
    written by.

    Every caller that decides the NEXT run is a fresh one calls this, and it
    is separate from that run because the run cannot do it: a spawn records an
    id only when the backend hands one back, so a timeout or a question that
    surfaced none would leave the retired id standing and the resume after it
    replaying the conversation this issue was moved on from.
    """
    state.set("decomposer_session_id", None)
