# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""When the locked dev session is kept, retired, or refused a spawn at all.

One session is pinned per issue and every resume replays its whole transcript,
so the interesting decisions are all about when to stop replaying. Four
conditions retire it -- the resume budget (`DEV_SESSION_MAX_RESUMES`), the
silent-park streak, a poisoned-session marker the run itself returned, and the
continuation a human buys a spent spawn budget out of (`retry_cap`), whose
whole purchase is a fresh attempt -- and all four end in the same
`_drop_poisoned_dev_session`, because the fresh spawn that follows must keep
the pinned `dev_agent` spec (neither a transcript problem nor a spent budget is
a backend-selection problem) while clearing the id and both counters.
Retirement drops the id BEFORE the spawn so a spawn that returns no id of its
own cannot leave the next tick resuming the session this one just retired.

The retry budget is the other gate, and it is deliberately not per-session:
the 24h window counts fresh spawns per ISSUE, shared with decomposing, so a
stuck issue cannot burn a day of tokens by rotating sessions. Only fresh spawns
are counted -- a resume on a human reply is an unblock signal, not a retry.
None of it is here: the budget, the park an exhausted one takes, and the
sentence that park owes the thread all live on
`workflow/engine/retry_budget.py`, which every stage's gate is decided by and
whose parking form the spawn road calls directly. What this owner still knows
about it is the retirement -- a continuation buys a FRESH spawn, so the
conversation that ran the budget out may not still be pinned when it finishes.

`_build_dev_spawn_prompt` is here for the same reason: a resume carries the
requirements in its replayed transcript, so what a fresh spawn needs instead --
the re-grounding preamble pointed at the committed branch -- is a property of
the rotation decision made above it, not of the caller that asked for a resume.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    prompt_context as _prompt_context,
    prompts as _prompts,
)
from orchestrator.workflow.stages.implementing import (
    models as _models,
    resume_request as _resume_request,
    session_read as _session_read,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")


def _is_poisoned_session_failure(
    backend: str, agent_result: AgentResult,
) -> bool:
    """True iff resuming this session is futile and a fresh spawn is the only
    recovery: the session was GC'd (stale) or its transcript overflowed the
    model context window. Both clear the pinned session id and retry once as
    a fresh spawn in `_resume_dev_with_text`.
    """
    return (
        _session_read._is_stale_session_failure(backend, agent_result)
        or _session_read._is_context_overflow_failure(backend, agent_result)
    )


def _drop_poisoned_dev_session(state: PinnedState) -> None:
    """Clear the pinned dev session id (and legacy `codex_session_id`).

    One retirement for every reason there is to stop replaying a transcript:
    the three the callers here decide, plus the continuation that buys a spent
    budget one more attempt, which is a fresh spawn by definition and so may
    not leave the retired session pinned for the next reply to resume.

    Preserves the stored `dev_agent` spec when one is already pinned --
    a poisoned session is a transcript problem, not a backend-selection
    problem, so the fresh spawn that follows must replay the exact same
    backend+args. Writing the parsed backend back here would silently
    strip the configured CLI args from the spec and switch a `codex -m
    gpt-5.5 -c '...'` issue back to bare `codex` on the next resume.

    When the issue is on the legacy `codex_session_id` schema (no
    `dev_agent` ever written), pin `dev_agent="codex"` BEFORE clearing
    the legacy field. Without this, the next `_read_dev_session` would
    fall through to the config default and a `DEV_AGENT=claude` flip
    would silently switch the issue from codex to claude on retry.

    Clearing the legacy field too leaves no trace of the dropped
    session anywhere.
    """
    stored_spec = state.get(_state._DEV_AGENT)
    if not stored_spec and state.get(_state._CODEX_SESSION_ID) is not None:
        state.set(_state._DEV_AGENT, "codex")
    state.set(_state._DEV_SESSION_ID, None)
    state.set(_state._CODEX_SESSION_ID, None)
    state.set(_state._SILENT_PARK_COUNT, 0)
    # The resume budget is per-session; clearing the session resets it so the
    # fresh spawn that follows starts its own count from zero.
    state.set(_state._DEV_RESUME_COUNT, 0)


def _resolve_dev_session_for_resume(
    issue: Issue, state: PinnedState
) -> _models._DevResumePlan:
    """Read the locked dev session and decide fresh-spawn vs resume.

    Returns a plan whose session locks the agent spec, backend, arguments,
    and session id alongside the fresh-spawn decision and resume count.

    The plan's session id is cleared to None -- and `fresh_spawn` set True --
    when the session must be retired proactively: either the resume budget
    (`DEV_SESSION_MAX_RESUMES`) or the silent-park streak
    (`_SILENT_PARKS_BEFORE_FRESH_SESSION`) is exhausted. `--resume` replays
    the entire accumulated transcript every time, so a session resumed many
    times creeps toward the model context window; rotating proactively rebuilds
    a small prompt from durable state and caps that creep before it overflows.
    Retirement drops the pinned session id BEFORE the spawn (via
    `_drop_poisoned_dev_session`, which also zeroes `dev_resume_count`) so a
    fresh spawn that returns no session id does not leave the next tick reading
    the retired id and burning another retry.

    A None session id on entry (no live session to resume: the documenting
    initial pass, or a prior backend hiccup that committed but dropped
    `dev_session_id` while leaving `dev_agent` pinned) also yields
    `fresh_spawn=True`. Such a spawn opens a NEW session -- re-grounded by the
    caller and its returned id persisted -- and is NOT charged against the
    resume budget, whose checks require a non-None session id.
    """
    session = _models._DevSession(*_session_read._read_dev_session(state))
    silent_count = int(state.get(_state._SILENT_PARK_COUNT) or 0)
    resume_count = int(state.get(_state._DEV_RESUME_COUNT) or 0)
    retirement_reason = _dev_session_retirement_reason(
        session.session_id, resume_count, silent_count,
    )
    if retirement_reason is not None:
        log.info(
            "issue=#%d retiring dev session %r (%s); starting fresh",
            issue.number, session.session_id, retirement_reason,
        )
        _drop_poisoned_dev_session(state)
        session = _models._DevSession(
            session.spec, session.backend, session.extra_args, None,
        )
    return _models._DevResumePlan(
        session=session,
        fresh_spawn=session.session_id is None,
        resume_count=resume_count,
    )


def _dev_session_retirement_reason(
    session_id: str | None, resume_count: int, silent_count: int,
) -> str | None:
    if session_id is None:
        return None
    max_resumes = config.DEV_SESSION_MAX_RESUMES
    if max_resumes > 0 and resume_count >= max_resumes:
        return f"resume budget reached: {resume_count} >= {max_resumes}"
    if silent_count >= _state._SILENT_PARKS_BEFORE_FRESH_SESSION:
        return f"{silent_count} consecutive silent parks"
    return None


def _build_dev_spawn_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    followup_text: str,
    options: _resume_request._DevResumeOptions,
    *,
    fresh: bool,
) -> str:
    """Prompt text for a dev resume/spawn.

    A resume already carries the issue requirements + conversation in its
    replayed transcript, so it gets the bare followup. A fresh spawn has no
    transcript, so it is re-grounded with `_build_fresh_respawn_preamble`
    (issue body + recent comments) pointed at the committed branch where the
    retired session's work survives. When the followup already embeds the
    tracked-repos block (documentation prompts), no sibling specs are passed so
    the block builder returns "" -- otherwise the composed prompt would list
    the tracked repos twice.

    The conversation is the caller's frozen one wherever it holds one, because
    the prompt and the record of what the prompt delivered have to come off
    ONE reading of the thread: taken here instead, this read is minutes newer
    than the batch its caller will settle, so a comment written in between
    reaches the agent and is handed to it again on the next poll. A caller
    with no frozen read -- every resume whose followup is built from something
    other than the thread -- gets the read taken here, as it always was.
    """
    if not fresh:
        return followup_text
    preamble_specs = (
        [] if options.followup_has_tracked_repos else config.default_repo_specs()
    )
    preamble = _prompts._build_fresh_respawn_preamble(
        spec,
        issue,
        options.thread_text or _prompt_context._recent_comments_text(issue),
        preamble_specs,
    )
    return f"{preamble}\n\n{followup_text}"


def _persist_dev_session_after_run(
    state: PinnedState,
    agent_result: AgentResult,
    *,
    fresh_spawn: bool,
    resume_count: int,
) -> None:
    """Record the session id / resume budget after a dev run and clear the
    awaiting-human flag (the caller reacted to a fresh human signal).

    A fresh spawn that produced a session id pins it and zeroes the resume
    budget so the new session starts its own count -- covering both rotation /
    poisoned-session recovery (which already reset the count) and the entry
    case where a stale count left by a prior session would otherwise rotate the
    brand-new session early. A resumed session is charged one against the
    budget so the next tick can rotate once the transcript has grown enough.
    """
    if fresh_spawn:
        if agent_result.session_id:
            state.set(_state._DEV_SESSION_ID, agent_result.session_id)
            state.set(_state._DEV_RESUME_COUNT, 0)
    else:
        state.set(_state._DEV_RESUME_COUNT, resume_count + 1)
    state.set(_state._AWAITING_HUMAN, False)
