# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What keeps a multi-turn Q&A on one agent, and what it is fed each round.

A question thread can run for many ticks, and each helper here exists because
something between two rounds is allowed to change underneath it. The configured
`DECOMPOSE_AGENT` can be flipped, so the spec that actually ran is pinned and
read back rather than re-resolved. The issue thread can gain an untrusted reply,
so the consume filter drops those before they can steer the agent OR advance the
watermark. And the CLI can hand back no session id, which is why both prompt
builders sit together: the resume degrades to the full first-round prompt in
that case, because a followup handed to a fresh agent would arrive with no issue
body to answer against.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    conversation_prompts as _conversation_prompts,
    prompt_context as _prompt_context,
)
from orchestrator.workflow.stages.question import models as _models, state as _state


def _read_question_session(
    state: PinnedState,
) -> _models._QuestionSession:
    """Return the locked question-agent identity for an issue.

    Mirrors `_read_dev_session` / `_read_decomposer_session`: `spec` is
    the full configured command string the next run will use. Callers
    persist it verbatim BEFORE invoking `run_agent` so a fresh spawn
    that yields no `session_id` (CLI hiccup, empty `-o` file) still
    records the role identity and a later `DECOMPOSE_AGENT` env flip
    cannot retarget the next awaiting-human resume at a different
    backend.

    Legacy bare-backend values (`"codex"` / `"claude"`) round-trip
    cleanly to `(backend, ())`. When the issue has never spawned a
    question agent, the returned fields carry the current decomposer spec,
    backend, args, and an empty session id.
    """
    stored = state.get(_state._QUESTION_AGENT_KEY)
    if stored:
        spec = str(stored)
        backend, args = config._parse_agent_spec(
            _state._QUESTION_AGENT_KEY, spec,
        )
        session_id = state.get(_state._QUESTION_SESSION_KEY)
        return _models._QuestionSession(
            agent_spec=spec,
            backend=backend,
            extra_args=args,
            session_id=(
                None if session_id is None else str(session_id)
            ),
        )
    return _models._QuestionSession(
        agent_spec=config.DECOMPOSE_AGENT_SPEC,
        backend=config.DECOMPOSE_AGENT,
        extra_args=config.DECOMPOSE_AGENT_ARGS,
        session_id=None,
    )


def _consume_new_human_replies(
    gh: GitHubClient, issue: Issue, state: PinnedState
) -> list | None:
    """Return new issue-thread comments since the last park, advancing the
    consume watermark past them.

    Returns None when nothing new arrived (caller returns without writing
    state). Mirrors `_resume_developer_on_human_reply`: the watermark advances
    BEFORE the spawn so a crashed / timed-out resume still records the comments
    as consumed (the agent did see them via the followup prompt).

    Untrusted authors are dropped up front: the live resume path feeds these
    comments straight into `_build_question_followup_prompt`, so with
    `ALLOWED_ISSUE_AUTHORS` set an outsider's reply must not steer the question
    agent NOR advance the consumed watermark. Only trusted comments are
    consumed, so an outsider reply trailing a trusted one is left unconsumed
    rather than persisted as the watermark; an all-untrusted batch leaves
    nothing to act on and is treated as "no new reply".
    """
    last_action_id = state.get("last_action_comment_id")
    new_comments = filter_trusted(gh.comments_after(issue, last_action_id))
    if not new_comments:
        return None
    state.set(
        "last_action_comment_id",
        max(reply_comment.id for reply_comment in new_comments),
    )
    return new_comments


def _build_first_round_question_prompt(
    spec: _config_models.RepoSpec, issue: Issue,
) -> str:
    """Assemble the prompt an agent with no cached context needs: the issue
    body and title plus the trusted conversation so far."""
    return _conversation_prompts._build_question_prompt(
        spec, issue, _prompt_context._recent_comments_text(issue),
        config.default_repo_specs(),
    )


def _build_question_resume_prompt(
    spec: _config_models.RepoSpec,
    issue: Issue,
    new_comments: list,
    question_session_id: str | None,
) -> str:
    """Assemble the resume prompt for a human reply.

    When we have a live session to resume, the brief follow-up prompt is
    enough -- the agent already has the issue body / title / prior
    conversation cached in its session state. Without a session id (the prior
    tick's CLI hiccup left `question_session_id` empty), `_run_agent_tracked`
    starts a fresh agent that has no cached context, so a followup-only prompt
    would arrive without an issue body, title, or prior conversation and the
    agent would have nothing to answer against. Switch to the full question
    prompt in that case so the recovery spawn sees the same context a
    first-tick run would, with the human's reply visible in the conversation
    block via `_recent_comments_text`.
    """
    if question_session_id is None:
        return _build_first_round_question_prompt(spec, issue)
    return _conversation_prompts._build_question_followup_prompt(new_comments)
