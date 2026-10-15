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

A conversation a run showed to have FAILED -- one an exhausted account quota
stopped, which `quota_retirement` retires as the attempt returns -- is retired
for good instead, on a record of its own that `session_retirement` keeps: the
planned read here asks that record before either counter, and the pin a fresh
spawn's id goes through refuses a retired id or a missing one, so recovery
stays owed until a conversation with an id of its own is pinned.

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
the re-grounding preamble pointed at the committed branch, quoting the residual
scope a split left the issue where its record holds one -- is a property of
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
    session_retirement as _session_retirement,
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

    It keeps the pinned `dev_agent` command and zeroes both per-session
    counters (`session_retirement._clear_dev_session_pins`, which says why),
    and it records nothing of its own: a transcript retired for being long,
    quiet, or poisoned is not a conversation a later spawn must refuse to pin
    again, and the record of one that is (`session_retirement`) survives this
    drop. The only pins it does record are those dropped while that record
    owes a fresh conversation -- in either field -- so the record still names
    them once they are gone.
    """
    _session_retirement._clear_dev_session_pins(state)


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
    A conversation the retirement record names (`session_retirement`), or any
    pinned while that record still owes a fresh one, is retired the same way
    whatever either counter says. Retirement drops the pinned session id
    BEFORE the spawn (via
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
    resume_count = int(state.get(_state._DEV_RESUME_COUNT) or 0)
    session, retirement_reason = _planned_dev_session(state)
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


def _planned_dev_session(state: PinnedState) -> tuple[_models._DevSession, str | None]:
    """The locked dev session a resume over `state` opens with, and why it retires first, if it does.

    Read only: `_resolve_dev_session_for_resume` stages the retirement, so a
    reader asking which launch a resume would be -- the charge a handed change
    request's recovery correlates (`execution._first_launch_fingerprint`) --
    plans it without retiring anything.

    The retirement record is asked before either counter, because publication
    and every rotation zero those: a conversation retired as failed stays
    retired however healthy the counters read afterwards.
    """
    session = _models._DevSession(*_session_read._read_dev_session(state))
    recorded = _session_retirement._retired_session_reason(state, session.session_id)
    if recorded is not None:
        return session, recorded
    silent_count = int(state.get(_state._SILENT_PARK_COUNT) or 0)
    resume_count = int(state.get(_state._DEV_RESUME_COUNT) or 0)
    return session, _dev_session_retirement_reason(session.session_id, resume_count, silent_count)


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
    reaches the agent and is handed to it again on the next poll. An EMPTY
    frozen conversation is still the caller's answer -- a retry whose only
    fresh words were the commands it consumes freezes one -- so only a caller
    with no frozen read at all (None) gets the read taken here.

    The split rationale the preamble quotes is the options' own, which the
    resume read off the issue's record (`resume_request._DevResumeOptions`)
    rather than off this conversation, so a replacement session is handed the
    residual scope its predecessor's first spawn was, however far back on the
    thread the split summary sits. A resume is handed nothing: the transcript
    it replays already holds it.
    """
    if not fresh:
        return followup_text
    preamble_specs = (
        [] if options.followup_has_tracked_repos else config.default_repo_specs()
    )
    conversation = options.thread_text
    if conversation is None:
        conversation = _prompt_context._recent_comments_text(issue)
    preamble = _prompts._build_fresh_respawn_preamble(
        spec, issue, conversation, preamble_specs, options.split_rationale,
    )
    return f"{preamble}\n\n{followup_text}"


def _persist_dev_session_after_run(
    state: PinnedState,
    agent_result: AgentResult,
    *,
    fresh_spawn: bool,
    resume_count: int = 0,
    resumed_session_id: str | None = None,
) -> None:
    """Record the session id / resume budget after a dev run.

    A fresh spawn that produced a session id pins it and zeroes the resume
    budget so the new session starts its own count -- covering both rotation /
    poisoned-session recovery (which already reset the count) and the entry
    case where a stale count left by a prior session would otherwise rotate the
    brand-new session early. A resumed session -- `resumed_session_id`, the
    conversation the plan resumed -- is charged one against the budget so the
    next tick can rotate once the transcript has grown enough.

    The pin goes through `session_retirement._pin_dev_session`, so a fresh
    spawn that returns no id, or hands a retired conversation's id back, pins
    nothing and leaves the recovery owed. The budget a resume charges is the
    pinned conversation's, so it is charged only while that is still the
    conversation that ran and the record does not forbid resuming it: one
    retired while it ran is charged nothing, and neither is the fresh
    conversation a recovery may have pinned in its place meanwhile, whose
    budget is its own from zero.

    It writes nothing but the session's own fields -- clearing the park a
    resume answered is the resume's (`execution`) -- so the first spawn on an
    unparked tick (`spawn._spawn_implementer`) pins through here too, and no
    road pins a developer id around the retirement record.
    """
    if fresh_spawn:
        _session_retirement._pin_dev_session(state, agent_result.session_id)
        return
    pinned = _session_read._read_dev_session(state)[3]
    if pinned is None or pinned != resumed_session_id:
        return
    if _session_retirement._retired_session_reason(state, pinned) is None:
        state.set(_state._DEV_RESUME_COUNT, resume_count + 1)
