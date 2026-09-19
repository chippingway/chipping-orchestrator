# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two ways a dev session is handed new text, and the call shape they keep.

`_resume_dev_with_text` is the resume every stage that owns a dev session goes
through -- implementing, validating, documenting, in_review, fixing, and
resolving_conflict -- so its signature is a contract several callers already
wrote against: positional `state` and `followup_text`, an optional `stage`
override, and keyword options. It is bound through an explicit `inspect`
signature rather than named parameters so that shape is enforced in one place
and a mistyped option raises instead of being ignored.

`_resume_developer_on_human_reply` is the narrower one: it is what implementing
and validating park against, and both of them resume from ONE frozen batch --
`resume_batch` beside this, which reads the thread once and produces the
quoted replies and the delivery record together. The prompt is built from that
record, so what the developer was handed and what the issue may mark answered
cannot disagree.

What it settles, it settles AFTER the run and only for an outcome that counts
the batch as delivered: a never-invoked, shutdown-killed, or live-paused run
consumes nothing, since the developer never read the batch. Nothing is lost by
waiting, because every caller that returns on a pause or an interruption
returns without writing pinned state, so a bump taken ahead of the run would
be dropped by that return anyway.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.stages.implementing import (
    execution as _execution,
    resume_batch as _resume_batch,
    resume_request as _resume_request,
)

_DEV_RESUME_SIGNATURE = inspect.Signature((
    inspect.Parameter("gh", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("spec", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("issue", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("resume_args", inspect.Parameter.VAR_POSITIONAL),
    inspect.Parameter(
        "stage",
        inspect.Parameter.KEYWORD_ONLY,
        default=None,
    ),
    inspect.Parameter("option_fields", inspect.Parameter.VAR_KEYWORD),
))


def _resume_dev_with_text(
    *args: Any,
    **kwargs: Any,
) -> tuple[Path, AgentResult, bool]:
    """Resume the dev's locked-backend session with the given prompt text.

    `stage` overrides the recorded stage for every audit / analytics /
    trajectory record this run emits. It defaults to the label read off
    `issue`, which is correct whenever the caller fetched the issue fresh this
    tick or relabelled it through `set_workflow_label`. The CHANGES_REQUESTED
    fix path passes it explicitly (`fixing`): it relabels validating -> fixing
    and then resumes, and naming the stage keeps the developer run off the
    reviewer's stage whichever `Issue` object reaches the resume -- one the
    relabel did not go through would still report `validating`.

    The backend is locked to whatever wrote `dev_session_id` (or the legacy
    `codex_session_id`) for this issue -- resuming across backends would need
    an inter-backend session bridge that does not exist. Clears the
    `awaiting_human` flag because the caller is reacting to a fresh human
    signal (issue or PR comment) by spawning the agent.

    After `_SILENT_PARKS_BEFORE_FRESH_SESSION` consecutive `agent_silent`
    parks on the current `dev_session_id`, the resume drops the session id
    and starts a fresh spawn instead. Sessions killed mid-stream (e.g. by a
    Claude rate limit) consistently return empty results on every subsequent
    resume; without this fallback every human "retry" comment burns another
    fresh-spawn retry slot on the same poisoned session.

    Proactive rotation: each resume increments a per-session `dev_resume_count`
    and, once it reaches `config.DEV_SESSION_MAX_RESUMES` (when that knob is
    > 0), the session is retired and the spawn goes fresh. `--resume` replays
    the entire accumulated transcript every time, so a session resumed many
    times creeps toward the model context window; rotating proactively rebuilds
    a small prompt from durable state (issue body + recent comments + the
    committed branch) and caps that creep before it overflows. Every fresh
    spawn -- whether triggered by rotation, the silent-park fallback, or
    poisoned-session recovery -- is prefixed with a re-grounding preamble
    (`_build_fresh_respawn_preamble`) because the prior session's in-memory
    reasoning is gone and only its committed work survives on the branch.

    A Claude resume that comes back with `No conversation found with session
    ID` (or a sibling marker), or with a `Prompt is too long` context-window
    overflow, is treated as the same poisoned-session condition but
    recognized immediately: the pinned session id is cleared and the call is
    retried once as a fresh spawn in the same worktree, so a Claude session
    whose transcript was GC'd or grew past the context window doesn't park
    (`agent_silent` for two ticks, or `awaiting_human` forever) before
    recovering.

    Returns `(worktree, result, paused)`. `paused` is the live-pause decision
    -- True only when `pause_guard` is set AND a hard-skip control label
    (`paused` / `backlog`) was applied to a freshly fetched issue while an agent
    run was in flight. `pause_guard` is opt-in (default False): every
    developer-resume caller -- implementing, validating, documenting, in_review,
    fixing, and resolving_conflict -- passes it True and honors the flag. The
    check runs after BOTH agent runs -- the initial resume/spawn AND the
    poisoned-session fresh retry -- because each has its own live-pause window:
    the first fires before the retry spawns a second agent, and the second
    before the retry's result is persisted. When it fires the helper stops
    before the session id is persisted and before `awaiting_human` is cleared,
    and the caller must honor the returned flag by stopping too -- the decision
    is propagated, not re-fetched, so there is no window where the caller reads
    the label differently than the helper did.
    """
    bound_fields = _DEV_RESUME_SIGNATURE.bind(*args, **kwargs)
    bound_fields.apply_defaults()
    request = _resume_request._DevResumeRequest(
        gh=bound_fields.arguments["gh"],
        spec=bound_fields.arguments["spec"],
        issue=bound_fields.arguments["issue"],
        resume_args=bound_fields.arguments["resume_args"],
        option_fields=bound_fields.arguments["option_fields"],
        stage=bound_fields.arguments["stage"],
    )
    return _execution._DevResumeContext.build(request).execute()


_resume_dev_with_text.__signature__ = _DEV_RESUME_SIGNATURE


def _resume_developer_on_human_reply(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue,
    batch: _resume_batch._ReplyBatch,
    *,
    pause_guard: bool = False,
) -> tuple[Path, AgentResult, bool] | None:
    """Resume the developer's agent session with new issue-level comments.

    Returns (worktree, agent_result, paused) on resume, or None when there is
    nothing this road may resume on -- no fresh reply, or a batch a command
    road owns -- in which case the caller returns without writing state.
    `paused` is forwarded from `_resume_dev_with_text` and is only ever True
    when `pause_guard` is set; both callers (implementing and validating) pass
    it True and honor the flag.

    Used by `implementing` and `validating` -- both deliberately watch only
    the issue's comment thread, not the PR's. The `in_review` handler watches
    PR comments too via `_resume_dev_with_text` directly. Which is why the
    settlement advances the issue watermark alone: a PR comment below the
    reply consumed here was never in this prompt.

    `batch` is the caller's own frozen read, carrying the pinned state that
    read was bounded by: `validating` hands over the very batch its
    park-reason decisions were made from. What is IN it is `resume_batch`'s to
    decide; this owner honors `reserved` by resuming nothing and consuming
    nothing, since the park its run takes would otherwise stamp the thread
    read past the command a road owns.

    `last_action_comment_id` is settled once the run is back, and only for an
    outcome that counts the batch as delivered. Without it a successful resume
    leaves the watermark at the prior park id, and the validating -> in_review
    handoff replays the consumed reply as fresh PR feedback; with it taken on a
    refused launch, a shutdown kill, or a live pause, the reply is marked
    answered by a run that never read it. A timeout or an empty result did
    reach the agent, so the batch is consumed and the failure is surfaced
    through the timeout / dirty / question parks instead.
    """
    if batch.reserved or not batch.comments:
        return None
    resumed = _resume_dev_with_text(
        gh,
        spec,
        issue,
        batch.state,
        batch.followup,
        pause_guard=pause_guard,
        thread_text=batch.thread_text,
    )
    if _resume_batch._counts_as_delivered(resumed[1], resumed[2]):
        batch.settle()
    return resumed
