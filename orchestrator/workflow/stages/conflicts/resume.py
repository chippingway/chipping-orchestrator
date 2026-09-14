# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three ways a dev session is resumed on a branch mid-rebase.

All three go through one run helper because the session is locked to the
backend that opened it and the agent-action stamp has to move on every resume,
but what they do with the result differs. A body edit resumes on the new body
and consumes the drift comments up front, so its two short-circuits -- a
shutdown interruption and a live pause -- return WITHOUT writing pinned state:
the refreshed hash and the consumed watermark are discarded together, and the
next process re-detects the same edit rather than acting on a run it cannot
trust. A human reply to a park resumes on the reply text and hands the result
to the shared disposition. The third caller is the conflict resolution itself,
which lives beside the rebase that produced the conflicted files.

The reply path is also where `/orchestrator continue` is answered, and the
three-way split matters: a session-failure park retries the dev on a neutral
prompt rather than on the literal command it has no context for, a park that
needs a real answer refuses, and an auto-rebase park is left alone entirely
because the base-sync retry loop -- not this stage -- owns unparking it.
Untrusted authors are dropped before any of that, so an outsider reply neither
steers the dev nor advances the consumed-comment watermark.

Each of the three can end in a commit this stage publishes onto a pull request
the remote already carries, so each goes through the size gate: the fresh
conflict and the reply behind it through the shared conflict disposition, the
body edit through the shared fix publication. All three hand the gate the
round they would have counted, because a held candidate ends the tick on
`workflow:decomposing` and the tail that counts one never runs -- and no later
tick of this stage counts it either, since an authorized settlement publishes the
accepted commit and the resumed tick finds a branch already standing on its
base.
"""
from __future__ import annotations

from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.github.comments import filter_trusted
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _drift,
    guards as _guards,
    messages as _messages,
    prompt_context as _prompt_context,
    prompt_notes as _prompt_notes,
    usage as _usage,
)
from orchestrator.workflow.stages.conflicts import (
    guards as _conflict_guards,
    models as _models,
    outcomes as _outcomes,
    state as _state,
    transitions as _transitions,
)
from orchestrator.workflow.stages.implementing import resume as _dev_resume
from orchestrator.workflow.stages.validating import drift_outcomes as _drift_outcomes

# What a round a body-edit resume finished is recorded as, in the audit event
# and in the receipt a hold leaves for the tick that resumes behind it.
_DRIFT_RESOLVED = "drift_resolved"


def _resume_on_user_content_change(
    ctx: _models._ConflictContext,
    pr_number,
    new_hash: str,
) -> None:
    """Resume the dev session after a human edited the issue body mid-rebase.

    Posts a resuming ack, marks the drift comments consumed, and resumes
    the dev on the updated body+comments. On a pushed fix bumps the
    conflict round and hands to `validating`; on an ack (no commit) stays
    in `resolving_conflict` without parking. The caller returns immediately
    after this helper runs. Persists pinned state on every exit EXCEPT the
    shutdown-sweep-interrupted / live-paused short-circuits, which return
    without writing so the drift stays unconsumed and re-runs next process.

    A body edit resolved into a commit is a content update onto a pull request
    the remote already carries, so it publishes through the shared fix seam
    and its size gate like every other one this stage makes. What that costs
    is a tail this caller may never reach: a held candidate is relabelled to
    the adjudication, and no later `resolving_conflict` tick can count the
    round for it, since the settlement publishes the accepted commit itself.
    So the round rides the gate's own durable write, ahead of the relabel,
    under the outcome this resume actually had.
    """
    # The head this resume begins at, read before anything is consumed. It is
    # the head the publication behind it leases its force-push against, and
    # the size gate reads "no head" as a caller that established none and pins
    # the push to whatever the pull request is standing on once the agent
    # returns -- so a commit somebody landed while it was out becomes the
    # lease and is force-overwritten. Refused here rather than after, the
    # refreshed hash and the consumed watermark are never written and the next
    # tick re-detects the same edit.
    wt = _conflict_guards._ensure_conflict_worktree(ctx)
    before_sha = _verification_probes._head_sha(wt)
    if not before_sha:
        _transitions._park_unreadable_head(ctx)
        return
    ctx.state.set("user_content_hash", new_hash)
    _comments._post_pr_comment(
        ctx.gh, int(pr_number), ctx.state,
        ":pencil2: issue body changed; resuming dev session.",
    )
    # Mark issue-thread comments as consumed: the dev sees the full thread via
    # `_recent_comments_text`, and the eventual validating->in_review handoff
    # (after a successful pushed resolution flips back to validating) must not
    # replay them.
    _drift._mark_drift_comments_consumed(ctx.gh, ctx.issue, ctx.state)
    run = _run_conflict_resume(ctx, _body_edit_followup(ctx))
    # Shutdown-sweep interruption: ignore the partial result and return WITHOUT
    # writing pinned state -- the drift bookkeeping (refreshed
    # `user_content_hash`, consumed comments, session mutations) above is
    # discarded so the next process re-detects and re-runs the drift resume.
    # Must precede `_post_user_content_change_result`, which has no interrupted
    # check of its own and would otherwise parse `last_message` / route through
    # `_on_question` before the caller persists those changes.
    if _guards._ignore_if_interrupted(ctx.issue, run.dev_result):
        return
    # Live pause applied mid-run: an operator added `paused` (or `backlog`)
    # while this drift resume was in flight. Same short-circuit as the
    # interrupted branch -- return before `_post_user_content_change_result`,
    # the conflict-round bump, or any relabel / pinned-state write, so the
    # drift stays unconsumed and the committed work stays on the branch until
    # the label is removed.
    if run.paused:
        return
    # Read once and handed on, because the head this resume produced is what
    # three separate steps have to agree about: the commit the shared fix
    # publication measures and pushes, the receipt a hold leaves for the tick
    # that resumes behind it, and the SHA the round below is recorded under.
    # Re-read at each, a checkout something moved mid-tick makes them three
    # different commits.
    after_sha = _verification_probes._head_sha(run.worktree)
    outcome = _drift_outcomes._post_user_content_change_result(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, run.worktree,
        run.dev_result, before_sha,
        after_sha=after_sha,
        # The round this resume earns, handed to the gate for the exit where
        # the tail below never runs: an oversized resolution is held, the
        # issue is relabelled to the adjudication, and the resumed tick reads
        # the published commit as a branch already standing on its base --
        # the no-op flip, which resolves nothing and stamps no
        # `last_conflict_resolved_at`.
        spends=_transitions._settles_the_held_round(
            _DRIFT_RESOLVED, after_sha,
        ),
    )
    if outcome == "pushed":
        # Pushed branch diff -> hand straight back to validating; the single
        # docs pass runs after final reviewer approval.
        _transitions._hand_resolved_round_to_validating(
            ctx, int(ctx.state.get(_state._CONFLICT_ROUND) or 0), pr_number,
            outcome=_DRIFT_RESOLVED,
            sha=after_sha,
        )
        return
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _body_edit_followup(ctx: _models._ConflictContext) -> str:
    """The prompt a body edit resumes the dev on.

    The edited body and the thread around it together, because what the dev
    has to decide is whether the resolution it is in the middle of still
    applies -- and a comment answering the edit is as much of that question as
    the edit itself.
    """
    return _drift._build_user_content_change_prompt(
        ctx.issue, _prompt_context._recent_comments_text(ctx.issue),
    )


def _resume_awaiting_human(
    ctx: _models._ConflictContext, conflict_round: int, pr,
) -> None:
    """Resume a parked rebase on a fresh human reply.

    Collects comments past `last_action_comment_id`, resumes the dev with
    their text, and funnels the result through
    `_post_conflict_resolution_result`. Returns without writing pinned
    state when no reply has arrived yet or a live pause landed mid-run; on
    a real reply the shared funnel owns the push / relabel / state write.

    The lease is the head the pull request is standing on BEFORE the session
    resumes, read off the object this tick fetched. It is not `before_sha`:
    a parked worktree may be mid-rebase or ahead of its publication, so the
    local head is no claim about the remote. And it may not be left for the
    size gate to read afterwards either -- the agent is out for minutes, so
    whatever landed on that pull request meanwhile would become the head the
    gate freezes and the lease this force-push replaces, which is the one
    move a lease exists to refuse.
    """
    followup = _awaiting_human_followup(ctx)
    if followup is None:
        return
    wt = _conflict_guards._ensure_conflict_worktree(ctx)
    before_sha = _verification_probes._head_sha(wt)
    entered_head = pr.head.sha
    run = _run_conflict_resume(ctx, followup)
    # Live pause applied mid-run: honor the helper's decision and return
    # before `_post_conflict_resolution_result` (which parses the result,
    # pushes, relabels, and writes pinned state). The in-progress rebase stays
    # on the branch until the label is removed.
    if run.paused:
        return
    _outcomes._post_conflict_resolution_result(
        ctx, run, before_sha, conflict_round,
        force_with_lease=entered_head or None,
    )


def _awaiting_human_followup(ctx: _models._ConflictContext) -> str | None:
    """Build the dev-resume prompt for a parked rebase from the trusted human
    reply, or return ``None`` when the tick is handled without a resume.

    Returns ``None`` when no trusted reply has arrived yet (no state write) or
    the `/orchestrator continue` command is refused (park written). Otherwise
    advances the consumed-comment watermark and returns the retry prompt or the
    joined reply text.
    """
    last_action_id = ctx.state.get("last_action_comment_id")
    # Drop untrusted authors up front (mirrors `_resume_developer_on_human_reply`):
    # with `ALLOWED_ISSUE_AUTHORS` set an outsider reply on a parked rebase must
    # not steer the developer NOR advance the consumed watermark. Only trusted
    # comments are consumed, so an outsider reply trailing a trusted one is left
    # unconsumed; an all-untrusted batch is treated as "no human reply yet".
    new_comments = filter_trusted(ctx.gh.comments_after(ctx.issue, last_action_id))
    if not new_comments:
        return None  # no human reply yet
    # `/orchestrator continue` on a parked rebase, BEFORE the generic comment
    # resume. A session-failure park (`agent_silent` / `agent_timeout`) retries
    # the dev intentionally on a neutral prompt -- NOT the literal command,
    # which the dev has no context for -- while a park needing a real answer
    # refuses. Auto-rebase parks belong to the refresh retry-unpark, so leave
    # those (and command-plus-guidance / normal replies) to the resume below.
    park_reason = ctx.state.get("park_reason")
    continue_action = (
        "passthrough" if park_reason in _base_sync_state._AUTO_REBASE_PARK_REASONS
        else _messages._continue_command_action(new_comments, park_reason)
    )
    if continue_action == "refuse":
        _messages._refuse_parked_continue(ctx.gh, ctx.issue, ctx.state)
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return None
    ctx.state.set(
        "last_action_comment_id", max(comment.id for comment in new_comments),
    )
    if continue_action == "retry":
        return f"{_prompt_notes._CONTINUE_RETRY_PROMPT}\n\n{_prompt_notes._FOREGROUND_ONLY_NOTE}"
    joined = "\n\n".join(
        _prompt_context._quote_comment_line(comment)
        for comment in new_comments
        if comment.body
    )
    return f"{joined}\n\n{_prompt_notes._FOREGROUND_ONLY_NOTE}"


def _run_conflict_resume(
    ctx: _models._ConflictContext, followup: str,
) -> _models._ConflictResumeRun:
    """Resume the locked dev session over `followup` and stamp the agent
    action time. Shared by the drift, awaiting-human, and fresh-conflict
    resume paths."""
    wt, conflict_result, paused = _dev_resume._resume_dev_with_text(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, followup, pause_guard=True,
    )
    ctx.state.set("last_agent_action_at", _usage._now_iso())
    return _models._ConflictResumeRun(
        worktree=wt, dev_result=conflict_result, paused=paused,
    )
