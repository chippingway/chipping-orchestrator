# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dev run, and everything a finished run leaves behind.

The run refreshes `user_content_hash` on BOTH outcomes, because the dev saw
the quoted comments either way: leaving the baseline behind would let the next
handler that checks for a body edit read the comments it just consumed as fresh
drift and resume a second time on input already handled.

Two refusals sit between the finished run and any disposition, and both bail
WITHOUT writing pinned state so the whole tick is re-decidable next time. A
shutdown kill must cover the new-commit case too: falling through would consume
the feedback while the commit sits unpushed, and the next tick would see
nothing to do and bounce a PR head that is missing the fix. Leaving it on disk
is what lets a later clean run republish it through the stranded-fix tail.

Then the disposition. The ACK fast path is in_review-route only -- the
validating reviewer asked for a concrete change, so an ACK there is not an
answer -- and it stands down on a stranded commit, because the ack vouches for
the feedback and not for what the PR head actually carries. Whatever happens,
the consumed watermarks advance before the pushed / not-pushed split, and a
pushed fix drops the bookmarks, updates `review_round` per the route, and flips
straight to `validating`. Docs do not run on this exit: the single docs pass
belongs to the final-docs handoff after reviewer approval.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.agents import AgentResult
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _engine_drift,
    messages as _messages,
    prompts as _prompts,
    usage as _usage,
)
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    feedback as _feedback,
    models as _models,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_records as _late_records,
    resume as _dev_resume,
)
from orchestrator.workflow.stages.validating import (
    dev_fix as _dev_fix,
    stranded as _stranded,
)
from orchestrator.workflow.state import WorkflowLabel


def _spends_fix_round(state, pending_fix_at_was_set: bool):
    """What a HELD fix closes for this route, handed to the gate up front.

    The gate holding a candidate is not a park: the commit is on the branch,
    the issue is on `workflow:decomposing`, and an authorized settlement
    publishes it from there. So the round IS spent -- the head the reviewer rejected is
    superseded either way -- and the bookkeeping that says so cannot wait for
    a later fixing tick. The bounce that would otherwise do it applies the
    round only when it pushes a stranded commit itself, and a settled
    adjudication publishes before handing the issue back, so the bounce finds
    nothing ahead and counts nothing.

    Left undone, the in_review route keeps a round count that should have
    reset and the validating route never advances one -- so `MAX_REVIEW_ROUNDS`
    stops meaning what it says on exactly the issues that have been through
    an adjudication.

    Handed to the gate rather than applied on the way out, because the hold
    relabels: a caller that counted afterwards would lose the count to any
    crash in the window between that relabel and its own write, and the
    adjudication would settle onto a stage whose round was never spent. The
    same write that carries the measurement carries this, ahead of the label.

    Only the ROUTED hold spends it. A reading nobody could take also stops the
    tick with a generation on the pinned comment, and THAT one is a park --
    the developer's work is still pending and its round is not spent.
    """
    return _late_records._Spends(fields=(
        *_bookmarks._cleared_pending_fix_bookmarks(),
        (_state._REVIEW_ROUND, _fix_review_round(state, pending_fix_at_was_set)),
    ))


def _fix_review_round(state, pending_fix_at_was_set: bool) -> int:
    """The value `review_round` takes on this route, spent or landed.

      * in_review->fixing (`pending_fix_at` was set): reset to 0. The previous
        reviewer round was APPROVED (the in_review HITL ping is gated on
        approval); the new fix starts a fresh round-count so
        MAX_REVIEW_ROUNDS does not trip prematurely on issues that pass back
        through review after a human PR comment.
      * validating->fixing (a CHANGES_REQUESTED dev fix that parked and was
        finished via a human reply): bump. The previous round was
        CHANGES_REQUESTED, not APPROVED, so we are still in the same review
        cycle and the round counter must advance to keep MAX_REVIEW_ROUNDS
        accounting honest.

    Read ONCE per route, before the push, and carried as a frozen pair from
    there: the bump reads the counter off the pinned comment, so a second
    reading taken after the write that already applied it would count the same
    round twice.
    """
    if pending_fix_at_was_set:
        return 0
    return int(state.get(_state._REVIEW_ROUND) or 0) + 1


def _run_fixing_resume(
    ctx: _models._FixingContext, followup: str,
) -> _models._FixingResumeRun:
    """Ensure the worktree, resume the locked dev session over `followup`,
    refresh the user-content drift hash, and read HEAD before/after.

    The hash refresh includes any human issue-thread comments we just fed to
    the dev via `followup`. Without it, the next tick that runs
    `_handle_validating` (or any other handler that calls
    `_detect_user_content_change`) would see those consumed comments as fresh
    user-content drift and resume the dev a second time on input it has already
    handled. Mirrors the hash refresh `_handle_in_review` does at the moment it
    routes to `fixing`. Refresh on BOTH success and failure paths: the dev saw
    the comments via the prompt either way, so the baseline must move with the
    consumption regardless of whether the agent pushed a fix this tick.

    HEAD is read only when the run did not time out -- the timeout branch of
    `_handle_dev_fix_result` returns before it would use `after_sha`, and
    reading here would burn an extra `_head_sha` the timeout path never did.
    """
    wt = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    if not wt.exists():
        wt = _worktree_creation._ensure_worktree(
            ctx.spec, ctx.issue.number,
            branch=_naming._resolve_branch_name(
                ctx.state, ctx.spec, ctx.issue.number,
            ),
        )
    before_sha = _verification_probes._head_sha(wt)
    wt, dev_result, paused = _dev_resume._resume_dev_with_text(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, followup, pause_guard=True,
    )
    ctx.state.set("last_agent_action_at", _usage._now_iso())
    ctx.state.set(
        "user_content_hash",
        _engine_drift._compute_user_content_hash(
            ctx.issue, _comments._orchestrator_ids(ctx.state),
        ),
    )
    after_sha = (
        None if dev_result.timed_out else _verification_probes._head_sha(wt)
    )
    return _models._FixingResumeRun(
        worktree=wt,
        dev_result=dev_result,
        paused=paused,
        before_sha=before_sha,
        after_sha=after_sha,
    )


def _fixing_ack_fast_path(
    ctx: _models._FixingContext,
    wt: Path,
    feedback: _models._FixingFeedback,
    dev_result: AgentResult,
    after_sha: str | None,
) -> bool:
    """In_review-route ACK fast path. Returns True (and relabels to
    `in_review`) when the dev's no-commit reply carried an explicit
    `ACK: <reason>` marker vouching that the PR feedback needs no actionable
    change; False to fall through to `_handle_dev_fix_result`.

    A vague "continue" / "ok" nudge should not strand a complete, mergeable PR
    in `fixing`, so an ack returns to `in_review` (re-arming the ready-ping)
    instead of parking.

    The fast path stands down on the stranded-fix shape: the ack vouches for
    the *feedback*, not for the publish state, so when the clean HEAD is
    strictly ahead of the remote PR branch (a fix a prior parked run committed
    but never pushed -- e.g. a dirty-park whose stray files were later cleaned
    up) relabeling to `in_review` here would clear the bookmarks, advance the
    watermarks, and present a PR head that is still missing the committed fix.
    Falling through lets `_handle_dev_fix_result` publish the stranded HEAD
    through its normal push tail and the pushed-fix exit route the freshened
    head back to the reviewer. The stranded check is skipped when `after_sha`
    is unreadable (mirrors `_handle_dev_fix_result`'s own gate -- no pushing
    blind off a worktree whose HEAD we could not read).
    """
    ack_reason = _messages._drift_ack_reason(dev_result.last_message or "")
    if not ack_reason or (
        after_sha and _stranded._stranded_fix_unpushed(
            ctx.spec, wt, ctx.state, ctx.issue,
        )
    ):
        return False
    _feedback._advance_consumed_watermarks(ctx.state, feedback)
    _bookmarks._clear_pending_fix_bookmarks(ctx.state)
    quoted = _messages._as_blockquote(ack_reason)
    _comments._post_issue_comment(
        ctx.gh, ctx.issue, ctx.state,
        ":speech_balloon: dev session reports the PR feedback needs "
        f"no change:\n\n{quoted}\n\nReturning to `in_review`.",
    )
    # The session is alive and producing a coherent ack, so reset the
    # silent-park streak (mirrors the drift-ack handling).
    ctx.state.set("silent_park_count", 0)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.IN_REVIEW)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    return True


def _resume_fixing_and_dispatch_result(
    ctx: _models._FixingContext,
    feedback: _models._FixingFeedback,
    replay_batch,
) -> None:
    """Resume the locked dev session over the unread feedback (or a preserved
    `/orchestrator continue` batch), then dispatch the result: the in_review-
    route ACK fast path, the pushed-fix bounce back to `validating`, or a park
    via `_handle_dev_fix_result`.

    Runs after the quiet window has elapsed. Owns the resume, the interrupted /
    live-paused guards, the consumed-watermark advance, and the route round
    bookkeeping.
    """
    # Capture the route discriminator BEFORE the bookmark-clear branches below.
    # `pending_fix_at` is untouched between the tick's capture point and here
    # (no reachable path clears it in between), and the pushed-fix tail clears
    # the bookmarks only after this read.
    pending_fix_at_was_set = ctx.state.get(_state._PENDING_FIX_AT) is not None

    # On an accepted `/orchestrator continue`, resume on the PRESERVED batch
    # (plus any new feedback that came with the command), not the command
    # text -- the whole point of the command is to not lose the review
    # feedback the parked session never addressed.
    followup = _prompts._build_pr_comment_followup(
        feedback.all_items if replay_batch is None else replay_batch
    )
    run = _run_fixing_resume(ctx, followup)

    # A shutdown-killed (interrupted) resume is ignored entirely: its partial
    # last_message is not a real ACK or question, and `_handle_dev_fix_result`
    # refuses to publish an interrupted run regardless of HEAD. Bail WITHOUT
    # persisting state -- the ACK fast path, the consumed-watermark advance,
    # and the write below never run, and the awaiting_human reset / hash
    # refresh staged earlier this tick are dropped because we skip
    # `write_pinned_state`. The next tick re-discovers the same comments
    # (watermarks unmoved, bookmarks intact, awaiting_human unchanged) and
    # re-feeds them to a fresh dev session. This MUST cover the new-commit
    # case too: a kill that had advanced HEAD would otherwise fall through to
    # `_handle_dev_fix_result` (returns False, no push) and the watermark
    # advance below would consume the feedback while the local commit sits
    # unpushed -- the next tick would then see no feedback and bounce a PR
    # head that is missing the fix. Leaving the commit on disk lets a later
    # clean run republish it via the stranded-fix tail.
    if run.dev_result.interrupted:
        return

    # Live pause applied while the agent ran: an operator added `paused` (or
    # `backlog`) mid-run. Honor the decision `_resume_dev_with_text` already
    # made (propagated, not re-fetched) and stop before the ACK fast path, the
    # stranded-fix publish, `_handle_dev_fix_result`, the watermark advance, or
    # any relabel / pinned-state write. The committed work stays on the branch,
    # so once the label is removed the normal recovered / stranded-fix path
    # republishes it.
    if run.paused:
        return

    # ACK fast path (in_review route only): the dev made no commit but
    # explicitly signaled via the `ACK: <reason>` marker that the PR feedback
    # carries no actionable change. The validating CHANGES_REQUESTED route
    # (`pending_fix_at` unset) is excluded -- the reviewer DID request a
    # concrete change, so an ACK there falls through to `_handle_dev_fix_result`,
    # which parks for the human unless its stranded-fix check publishes a
    # committed-but-unpushed fix instead (`validating/stranded.py`'s probe).
    if (
        pending_fix_at_was_set
        and not run.dev_result.timed_out
        and (not run.after_sha or run.after_sha == run.before_sha)
        and _fixing_ack_fast_path(
            ctx, run.worktree, feedback, run.dev_result, run.after_sha,
        )
    ):
        return

    # What this route owes for the candidate, computed BEFORE the push and
    # handed to the gate: a hold closes it in the write that carries the
    # measurement, ahead of the relabel it makes, and a landed push closes it
    # in the write that carries the receipt. Either way the same frozen pairs
    # are what the tail below re-applies, so the two cannot disagree -- and
    # re-applying a value already written is a no-op rather than a second
    # count, which recomputing the round from the pinned comment would be.
    owed = _spends_fix_round(ctx.state, pending_fix_at_was_set)
    pushed = _dev_fix._handle_dev_fix_result(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, run.worktree, run.dev_result,
        run.before_sha, after_sha=run.after_sha, spends=owed,
    )

    # Advance the three in_review watermarks ONLY to the max id actually fed to
    # the dev on each surface (ratcheted against the current watermark).
    # Deliberately tighter than `_bump_in_review_watermarks`, which also pulls
    # in `gh.latest_comment_id(issue)`: a human issue-thread comment that
    # landed AFTER `feedback` was built but BEFORE this write was never quoted
    # in the dev's `_build_pr_comment_followup` prompt, so silently moving the
    # watermark past it would swallow real feedback.
    #
    # This applies to BOTH paths:
    #
    #   * On a pushed fix, the next in_review tick (after `validating`
    #     completes) must rediscover the concurrent comment as fresh PR
    #     feedback.
    #
    #   * On park/failure (timeout / dirty / push fail / no-commit), the next
    #     fixing tick must also rediscover it -- otherwise the
    #     `awaiting_human and not new_feedback` gate fires and the concurrent
    #     human comment is silently dropped, breaking the "comments arriving
    #     while already labeled `fixing`" contract on every failure mode.
    #
    # The orchestrator's own park comment posted by `_park_awaiting_human`
    # (issue id-space, body carries `_ORCH_COMMENT_MARKER` and its id is
    # recorded in `orchestrator_comment_ids`) does NOT need a watermark bump to
    # avoid replay: the next tick's rescan filters by both id and body marker,
    # so the park comment is dropped even when the watermark sits below it.
    _feedback._advance_consumed_watermarks(ctx.state, feedback)

    if not pushed:
        # A hold has already spent this route's round durably, from inside the
        # gate's own write: what is left here is the caller's ordinary write.
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return

    # The bookmarks this route consumed and the round it lands on, in the
    # values frozen before the push. The gate has already written them beside
    # the receipt, so this is what covers the one push it could not: a commit
    # nothing could name never reaches that write. We flip DIRECTLY to
    # `validating` so the reviewer re-evaluates the new head next tick. Docs do
    # not run on this exit -- the single docs pass is deferred to the final-docs
    # handoff after reviewer approval, so running the docs stage against an
    # unapproved diff here would just push a no-op and waste a tick.
    _late_records._spend(ctx.state, owed)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
