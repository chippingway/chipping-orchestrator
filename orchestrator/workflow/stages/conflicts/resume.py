# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The three ways a dev session is resumed on a branch mid-rebase.

All three go through one run helper because the session is locked to the
backend that opened it and the agent-action stamp has to move on every resume,
but what they do with the result differs. A body edit resumes on the new body
quoted from one frozen read, and records that read -- the comments and the
requirements revision alike -- only once the run is back and only for an
outcome that reached an agent: its three short-circuits, a launch the run
circuit refused, a shutdown interruption and a live pause, return WITHOUT
writing pinned state, so the next process re-detects the same edit rather than
acting on a run it cannot trust. A human
reply to a park resumes on the reply text and hands the result to the shared
disposition -- or, over a park that left this issue owing a report, to the road
the body edit takes, since that reply is the rest of the body edit's resume.
The third caller is the conflict resolution itself, which lives beside the
rebase that produced the conflicted files.

The reply path is also where `/orchestrator continue` is answered, and the
three-way split matters: a session-failure park retries the dev on a neutral
prompt rather than on the literal command it has no context for, a park that
needs a real answer refuses, and an auto-rebase park is left alone entirely
because the base-sync retry loop -- not this stage -- owns unparking it. The
retry keeps that meaning over a park that left a report owed as well: the
neutral prompt leads the frozen drift prompt, and the command is left out of
everything that read quotes. A reply over such a park is marked read by what
that frozen read delivered rather than ahead of it, and the read quotes every
reply whole, so a reply is never marked read without having been handed over.
Untrusted authors are dropped before any of that, so an outsider reply neither
steers the dev nor advances the consumed-comment watermark.

Each of the three can end in a commit this stage publishes onto a pull request
the remote already carries, so each goes through the size gate: the fresh
conflict and the reply behind it through the shared conflict disposition, the
body edit through the shared fix publication, held on the way to the developer
report contract the review stages' drift resumes are held to
(`resume_reports`). All three hand the gate the
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
    drift_delivery as _drift_delivery,
    guards as _guards,
    messages as _messages,
    prompt_context as _prompt_context,
    prompt_delivery as _delivery,
    prompt_notes as _prompt_notes,
    usage as _usage,
)
from orchestrator.workflow.stages.conflicts import (
    guards as _conflict_guards,
    models as _models,
    outcomes as _outcomes,
    parks as _conflict_parks,
    resume_reports as _resume_reports,
)
from orchestrator.workflow.stages.implementing import (
    resume as _dev_resume,
    resume_batch as _resume_batch,
)


def _resume_on_user_content_change(
    ctx: _models._ConflictContext,
    pr_number,
) -> None:
    """Resume the dev session after a human edited the issue body mid-rebase.

    Posts a resuming ack and resumes the dev on the updated body plus the
    conversation around it, quoted from ONE frozen read of the issue thread.
    On a pushed fix bumps the conflict round and hands to `validating`; on an
    ack or a report with no commit stays in `resolving_conflict` without
    parking. Either way the report the session returned is the one the pull
    request gets: recorded before the push, and bound and settled once this
    stage's own bookkeeping is written (`resume_reports`). The caller
    returns immediately after this helper runs. Persists pinned state on every
    exit EXCEPT the shutdown-sweep-interrupted / live-paused short-circuits,
    which return without writing so the drift stays unconsumed and re-runs next
    process.

    What the edit is recorded as answered by is that frozen record, settled
    once the run is back and only for an outcome that reached an agent. The
    baseline is inside it: read back off the live issue instead, this road
    would mark an edit answered by a prompt nobody read, and the words below
    it delivered by nobody. This surface is the issue thread and nothing else
    -- no PR-conversation comment, inline review comment or review summary
    enters the prompt -- so none of their cursors moves and the round that
    reads them still delivers every one.

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
    # lease and is force-overwritten. Refused here rather than after, no prompt
    # is frozen and nothing is recorded, so the next tick re-detects the same
    # edit.
    wt = _conflict_guards._ensure_conflict_worktree(ctx)
    before_sha = _verification_probes._head_sha(wt)
    if not before_sha:
        _conflict_parks._park_unreadable_head(ctx)
        return
    _comments._post_pr_comment(
        ctx.gh, int(pr_number), ctx.state,
        ":pencil2: issue body changed; resuming dev session.",
    )
    run = _run_drift_resume(ctx)
    # A launch the run circuit turned away: no process read the prompt, so the
    # refusal it recorded where it was decided is the whole of what this tick
    # says. Return before the disposition, which would otherwise park in the
    # name of a run that never started and persist that park over the edit.
    if _guards._ignore_if_never_invoked(ctx.issue, run.dev_result):
        return
    # Shutdown-sweep interruption: ignore the partial result and return WITHOUT
    # writing pinned state -- the frozen record below is never settled and the
    # session mutations above are discarded, so the next process re-detects and
    # re-runs the drift resume.
    # Must precede the settlement below, which would otherwise stage the edit
    # as answered by a run whose output nobody can trust.
    if _guards._ignore_if_interrupted(ctx.issue, run.dev_result):
        return
    # Live pause applied mid-run: an operator added `paused` (or `backlog`)
    # while this drift resume was in flight. Same short-circuit as the
    # interrupted branch -- return before the disposition, the report it would
    # record, the conflict-round bump, or any relabel / pinned-state write, so
    # the drift stays unconsumed and the committed work stays on the branch
    # until the label is removed.
    if run.paused:
        return
    _settles_what_it_delivered(ctx, run)
    # Stamped with the revision this resume's own prompt was cut from -- the
    # baseline the settlement above has just staged -- rather than with
    # whatever the issue says by the time the report reaches the pull request.
    # The head the run began at is the lease: this road runs only over a
    # branch in sync with its remote, so it IS the head the pull request is on.
    _resume_reports._disposes(
        ctx, run, before_sha, run.delivered.requirements_revision, before_sha,
    )


def _run_drift_resume(
    ctx: _models._ConflictContext,
    reply: _models._ParkedReply | None = None,
) -> _models._ConflictResumeRun:
    """Freeze what this edit's resume quotes, and run it on that text.

    One read answers both questions the resume asks the thread -- what the
    developer is handed, and what the issue may mark answered -- so the record
    travels back on the run rather than off a second read behind it.
    The same frozen conversation re-grounds a fresh respawn, where a rotated,
    retired or poisoned session turns this resume into one: read live there it
    would be a second reading, newer than the record this tick settles.

    `reply` is the batch a reply to a report-owed park is resumed on. Every
    reply in it is quoted whole, since what this read delivers is what marks
    them read. A bare `/orchestrator continue` retrying a session failure is
    out of that one read, and the neutral retry prompt leads the edit's own:
    quoted, the command would be the last thing a human said, to a developer
    with no context for it. The report contract and the revision it is
    stamped with are the drift prompt's either way.
    """
    answered = _drift_delivery._drift_resume_prompt(
        ctx.gh, ctx.issue, ctx.state, answering=None if reply is None else reply.retried,
    )
    prompt = (
        f"{_prompt_notes._CONTINUE_RETRY_PROMPT}\n\n{answered.text}"
        if reply is not None and reply.retried else answered.text
    )
    return _run_conflict_resume(
        ctx, prompt,
        thread_text=answered.delivery.rendered_text,
        delivered=answered.delivery,
    )


def _settles_what_it_delivered(
    ctx: _models._ConflictContext, run: _models._ConflictResumeRun,
) -> None:
    """Record the frozen prompt an edit's resume was given as read.

    For every outcome that reached an agent -- the push, the ACK, the timeout
    and question parks -- and for none that did not. The caller returns ahead
    of all three that did not, so what the predicate states here is the
    contract rather than the last line of defence: the record is settled by
    what the RUN came to, not by which guards a road happens to ask first.
    Delivery says the developer was handed those words, never that anything
    about them is resolved.
    """
    if run.delivered is None:
        return
    if _resume_batch._counts_as_delivered(run.dev_result, run.paused):
        run.delivered.settle(ctx.state)


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

    A park that left this issue owing a report -- a body edit's resume that
    committed and wrote none, wrote one no record could carry, or recorded one
    whose push did not land -- is answered as the rest of that resume instead
    (`resume_reports`): the resolution funnel reads no report, so it would push
    the commit undescribed and park the report the reply wrote as a question.
    So it is resumed the way that resume was: on the frozen drift prompt,
    which quotes the issue and its conversation -- the reply among it, and any
    edit made since -- and whose record is what the run's report is stamped
    with and what is settled once the run is back. A rotated or poisoned
    session's fresh spawn is re-grounded with that same frozen conversation,
    so the revision says what the run was given however it was launched. Its
    publication is handed the same lease, which the divergence guard ahead of
    this resume admitted, so a rebase the first run left goes out under the
    reply's report even where the reply commits nothing more. A bare
    `/orchestrator continue` retrying a session failure there is still a
    retry, on the same frozen prompt less the command.

    The resolution road marks the batch read before its run, since it quotes
    every reply in full. The drift road marks the replies read by what its
    frozen read delivered, once the run is back: that read is bounded, and a
    reply cut from it would otherwise be marked read without ever having been
    handed over. A retry's commands are spent ahead of either, as the
    controls they are.
    """
    reply = _awaiting_human_followup(ctx)
    if reply is None:
        return
    owes = _resume_reports._owes_a_report(ctx.state)
    if reply.retried or not owes:
        ctx.state.set("last_action_comment_id", reply.through)
    before_sha = _verification_probes._head_sha(
        _conflict_guards._ensure_conflict_worktree(ctx),
    )
    entered_head = pr.head.sha
    run = _run_drift_resume(ctx, reply) if owes else _run_conflict_resume(ctx, reply.followup)
    # Live pause applied mid-run: honor the helper's decision and return
    # before `_post_conflict_resolution_result` (which parses the result,
    # pushes, relabels, and writes pinned state). The in-progress rebase stays
    # on the branch until the label is removed.
    if run.paused:
        return
    if run.delivered is not None:
        _settles_what_it_delivered(ctx, run)
        _resume_reports._answers_the_reply(ctx, run, before_sha, entered_head or "")
        return
    _outcomes._post_conflict_resolution_result(
        ctx, run, before_sha, conflict_round,
        force_with_lease=entered_head or None,
    )


def _awaiting_human_followup(
    ctx: _models._ConflictContext,
) -> _models._ParkedReply | None:
    """Build the dev-resume prompt for a parked rebase from the trusted human
    reply, or return ``None`` when the tick is handled without a resume.

    Returns ``None`` when no trusted reply has arrived yet (no state write) or
    the `/orchestrator continue` command is refused (park written). Otherwise
    returns the retry prompt, with the commands it consumed, or the joined
    reply text -- with the last comment of the batch, which the caller marks
    read as its road requires.
    """
    last_action_id = ctx.state.get("last_action_comment_id")
    # Drop untrusted authors up front (mirrors `_resume_developer_on_human_reply`):
    # with `ALLOWED_ISSUE_AUTHORS` set an outsider reply on a parked rebase must
    # not steer the developer NOR advance the consumed watermark. Only trusted
    # comments are consumed, so an outsider reply trailing a trusted one is left
    # unconsumed; an all-untrusted batch is treated as "no human reply yet".
    # This orchestrator's own notices come out beside them, by the ledger of ids
    # it recorded posting: a bounded park cannot carry the watermark over a
    # human comment that landed ahead of it, so its notice can stand above the
    # watermark, and read as a reply it would resume the developer with nobody
    # having said anything.
    ours = frozenset(_comments._orchestrator_ids(ctx.state))
    new_comments = [
        comment
        for comment in filter_trusted(ctx.gh.comments_after(ctx.issue, last_action_id))
        if comment.id not in ours
    ]
    if not new_comments:
        return None  # no human reply yet
    # `/orchestrator continue` on a parked rebase, BEFORE the generic comment
    # resume. A session-failure park (`agent_silent` / `agent_timeout` /
    # `agent_execution_failed`) retries
    # the dev intentionally on a neutral prompt -- NOT the literal command,
    # which the dev has no context for -- while a park needing a real answer
    # refuses. Auto-rebase parks belong to the refresh retry-unpark, so leave
    # those (and command-plus-guidance / normal replies) to the resume below.
    continue_action = (
        "passthrough"
        if ctx.state.get("park_reason") in _base_sync_state._AUTO_REBASE_PARK_REASONS
        else _messages._continue_command_action(new_comments, ctx.state.get("park_reason"))
    )
    if continue_action == "refuse":
        _messages._refuse_parked_continue(
            ctx.gh, ctx.issue, ctx.state, new_comments,
        )
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return None
    through = max(comment.id for comment in new_comments)
    if continue_action == "retry":
        return _models._ParkedReply(
            f"{_prompt_notes._CONTINUE_RETRY_PROMPT}\n\n{_prompt_notes._FOREGROUND_ONLY_NOTE}",
            through,
            frozenset(comment.id for comment in new_comments),
        )
    return _models._ParkedReply(_quoted_reply(new_comments), through)


def _quoted_reply(new_comments: list) -> str:
    """The trusted replies as the resume prompt quotes them."""
    joined = "\n\n".join(
        _prompt_context._quote_comment_line(comment)
        for comment in new_comments
        if comment.body
    )
    return f"{joined}\n\n{_prompt_notes._FOREGROUND_ONLY_NOTE}"


def _run_conflict_resume(
    ctx: _models._ConflictContext,
    followup: str,
    *,
    thread_text: str | None = None,
    delivered: _delivery.PromptDeliverySnapshot | None = None,
) -> _models._ConflictResumeRun:
    """Resume the locked dev session over `followup` and stamp the agent
    action time. Shared by the drift, awaiting-human, and fresh-conflict
    resume paths.

    `thread_text` is the frozen conversation a fresh respawn is re-grounded
    with, for the caller that holds one: a rotated, retired or poisoned
    session turns this resume into a spawn, and the preamble that spawn is
    given would otherwise read the thread a second time -- newer than the
    record the caller settles, carrying a comment nothing would record.
    `delivered` is that record itself, carried back on the run for the road
    that settles it.
    """
    wt, conflict_result, paused = _dev_resume._resume_dev_with_text(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, followup, pause_guard=True,
        thread_text=thread_text,
    )
    ctx.state.set("last_agent_action_at", _usage._now_iso())
    return _models._ConflictResumeRun(
        worktree=wt, dev_result=conflict_result, paused=paused,
        delivered=delivered,
    )
