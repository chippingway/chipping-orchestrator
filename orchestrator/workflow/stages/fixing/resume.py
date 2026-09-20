# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The dev run, and everything a finished run leaves behind.

The run refreshes `user_content_hash` on BOTH outcomes, because the dev saw
the quoted comments either way: leaving the baseline behind would let the next
handler that checks for a body edit read the comments it just consumed as fresh
drift and resume a second time on input already handled.

Three refusals sit between the finished run and any disposition, and all bail
WITHOUT writing pinned state so the whole tick is re-decidable next time: a
launch nothing invoked, a shutdown kill, and an operator pausing mid-run. None
of them delivered the batch, so none of them may settle it -- and a shutdown
kill must cover the new-commit case too: falling through would consume the
feedback while the commit sits unpushed, and the next tick would see nothing to
do and bounce a PR head that is missing the fix. Leaving it on disk is what
lets a later clean run republish it through the stranded-fix tail.

Past those three the prompt reached an agent, whatever it came back with, so
the batch is SETTLED there -- once, ahead of every disposition below it. The
readers it settles are the surfaces it was read from (`feedback.py`), and the
moment is what makes it durable: the size gate's own write and a park's own
write both land inside the disposition, so a settlement taken afterwards would
be lost to a crash in exactly the window a hold's relabel opens.

Then the disposition. The ACK fast path is in_review-route only -- the
validating reviewer asked for a concrete change, so an ACK there is not an
answer -- and it stands down on a stranded commit, because the ack vouches for
the feedback and not for what the PR head actually carries. A pushed fix drops
the bookmarks, updates `review_round` per the route, and flips straight to
`validating`. Docs do not run on this exit: the single docs pass belongs to the
final-docs handoff after reviewer approval.
"""
from __future__ import annotations

from orchestrator.git.verification import probes as _verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation, naming as _naming, paths as _worktree_paths
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    conversation_prompts as _conversation_prompts,
    guards as _guards,
    messages as _messages,
    usage as _usage,
)
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    feedback as _feedback,
    models as _models,
    reporting as _reporting,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
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
    return _late_gate_models._Spends(fields=(
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
        _content_hash._compute_user_content_hash(
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
    run: _models._FixingResumeRun,
    *,
    routed: bool,
    reporting: bool,
) -> bool:
    """In_review-route ACK fast path. Returns True (and relabels to
    `in_review`) when the dev's no-commit reply carried an explicit
    `ACK: <reason>` marker vouching that the PR feedback needs no actionable
    change; False to fall through to `_handle_dev_fix_result`.

    Three shapes never reach the marker. The validating CHANGES_REQUESTED
    route (`routed` false) is excluded because that reviewer asked for a
    concrete change, so an ACK there is not an answer. A run that finished on
    a report outcome is excluded because its road is the publication, not a
    relabel to `in_review`. And a run that timed out or moved HEAD is not a
    no-commit reply at all.

    A vague "continue" / "ok" nudge should not strand a complete, mergeable PR
    in `fixing`, so an ack returns to `in_review` (re-arming the ready-ping)
    instead of parking.

    The fast path stands down on the stranded-fix shape: the ack vouches for
    the *feedback*, not for the publish state, so when the clean HEAD is
    strictly ahead of the remote PR branch (a fix a prior parked run committed
    but never pushed -- e.g. a dirty-park whose stray files were later cleaned
    up) relabeling to `in_review` here would clear the bookmarks and present a
    PR head that is still missing the committed fix.
    Falling through lets `_handle_dev_fix_result` publish the stranded HEAD
    through its normal push tail and the pushed-fix exit route the freshened
    head back to the reviewer. The stranded check is skipped when `after_sha`
    is unreadable (mirrors `_handle_dev_fix_result`'s own gate -- no pushing
    blind off a worktree whose HEAD we could not read).

    The consumed batch is recorded by the caller ahead of this call, on the ack
    and the fall-through alike: the reading that says the feedback needs no
    change is the same reading that says a developer read it.
    """
    if not routed or reporting or run.dev_result.timed_out:
        return False
    if run.after_sha and run.after_sha != run.before_sha:
        return False
    ack_reason = _messages._drift_ack_reason(run.dev_result.last_message or "")
    if not ack_reason or (
        run.after_sha and _stranded._stranded_fix_unpushed(
            ctx.spec, run.worktree, ctx.state, ctx.issue,
        )
    ):
        return False
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


def _records_what_was_consumed(
    ctx: _models._FixingContext,
    run: _models._FixingResumeRun,
    feedback: _models._FixingFeedback,
    owed,
    *,
    reporting: bool,
) -> bool:
    """Record what this round consumed, on the road its outcome belongs to.

    True is a tick this call ended -- a report this build cannot record, which
    parks with the commit still in the worktree and nothing published.

    A run that finished on a report outcome owes a publication this tick
    cannot guarantee, so its consumed pairs and its route bookkeeping ride the
    record of that report (`reporting.py`) and are closed by the write that
    completes the transaction. Every other outcome writes no report, so it
    closes its own -- directly and before the disposition, since the size
    gate's own durable write and a park's both land inside that disposition
    and a settlement taken afterwards would be lost to a crash in the window a
    hold's relabel opens.

    Only ids this prompt carried move either way. A human comment that landed
    AFTER `feedback` was built was never quoted in the dev's prompt, and
    swallowing it would drop real feedback on both outcomes: the next
    in_review tick would miss it on a pushed fix, and the next fixing tick's
    `awaiting_human and not new_feedback` gate would drop it on a park. The
    orchestrator's own park comment needs no bump to avoid replay -- the next
    tick's rescan filters by both recorded id and body marker.
    """
    if not reporting:
        _feedback._settle_consumed_feedback(ctx.state, feedback)
        return False
    return _reporting._recording_stops_the_tick(ctx, run, feedback, owed)


def _delivered_nothing(
    ctx: _models._FixingContext, run: _models._FixingResumeRun,
) -> bool:
    """The three finished runs that put this batch in front of nobody.

    A shutdown kill has no trustworthy result and its partial last message is
    no ACK and no question; a launch the run circuit turned away invoked no
    process at all; and a live pause is an operator stopping the tick before
    anything is persisted. Each bails WITHOUT writing pinned state, so the
    whole tick stays re-decidable: no reader moves, no bookmark is cleared,
    `awaiting_human` is untouched, and the next tick re-discovers the same
    comments and re-feeds them to a fresh session.

    The kill MUST cover the new-commit case too. Falling through would consume
    the feedback while the commit sits unpushed -- `_handle_dev_fix_result`
    refuses to publish an interrupted run -- and the next tick would see
    nothing to do and bounce a PR head that is missing the fix. Left on disk,
    a later clean run republishes it through the stranded-fix tail.
    """
    if run.dev_result.interrupted:
        return True
    if _guards._ignore_if_never_invoked(ctx.issue, run.dev_result):
        return True
    return run.paused


def _resume_fixing_and_dispatch_result(
    ctx: _models._FixingContext,
    feedback: _models._FixingFeedback,
    replay_batch,
) -> None:
    """Resume the locked dev session over the unread feedback (or a preserved
    `/orchestrator continue` batch), then dispatch the result: the in_review-
    route ACK fast path, the pushed-fix bounce back to `validating`, or a park
    via `_handle_dev_fix_result`.

    Runs after the quiet window has elapsed. Owns the resume, the three
    refusals that count no delivery at all, the record of the batch that WAS
    delivered -- direct, or onto the report transaction that will close it --
    and the route round bookkeeping.
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
    run = _run_fixing_resume(ctx, _conversation_prompts._build_pr_comment_followup(
        feedback.all_items if replay_batch is None else replay_batch,
    ))

    # Nothing below may run for a batch no agent read (`_delivered_nothing`),
    # and none of it persists: the awaiting_human reset and the hash refresh
    # staged earlier this tick are dropped with the write we skip.
    if _delivered_nothing(ctx, run):
        return

    # What this route owes for the candidate, frozen BEFORE anything is
    # written: the bookmarks the consumed batch clears and the round the fix
    # lands on. Read once, so a second reading taken after the write that
    # already applied it cannot count the same round twice.
    owed = _spends_fix_round(ctx.state, pending_fix_at_was_set)

    # The prompt reached an agent, so the batch it quoted is delivered
    # whatever the run came back with -- a fix, a timeout, an empty message, a
    # question. Which WRITE records that is the fork below, and a report this
    # build cannot record ends the tick where the commit is still unpublished.
    reporting = _reporting._reports(run)
    if _records_what_was_consumed(
        ctx, run, feedback, owed, reporting=reporting,
    ):
        return

    # ACK fast path: the dev made no commit but explicitly signaled via the
    # `ACK: <reason>` marker that the PR feedback carries no actionable
    # change. A reply that falls short of it goes to `_handle_dev_fix_result`,
    # which parks for the human unless its stranded-fix check publishes a
    # committed-but-unpushed fix instead (`validating/stranded.py`'s probe).
    if _fixing_ack_fast_path(
        ctx, run, routed=pending_fix_at_was_set, reporting=reporting,
    ):
        return

    # The gate is handed what it may close on this caller's behalf, and on the
    # reporting road that is NOTHING: the transaction recorded above is
    # carrying the same pairs, and a hold that closed them there would drop
    # the bookmarks a publication still owed is the replay source for.
    pushed = _dev_fix._handle_dev_fix_result(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, run.worktree, run.dev_result,
        run.before_sha, after_sha=run.after_sha,
        spends=_late_gate_models._SPENDS_NOTHING if reporting else owed,
    )

    if not pushed:
        # A hold has already spent this route's round durably, from inside the
        # gate's own write: what is left here is the caller's ordinary write.
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return

    if reporting and _reporting._holds_an_unpublished_report(ctx, run):
        # The code is out and the report it is about is not. The transaction
        # still carries the consumed batch and this route's bookkeeping, so
        # neither is applied here and the label stays put: the reconciliation
        # ahead of a later handler finishes the publication and settles both.
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return

    # The bookmarks this route consumed and the round it lands on, in the
    # values frozen before the push. The gate has already written them beside
    # the receipt, so this is what covers the one push it could not: a commit
    # nothing could name never reaches that write, and a settled report closed
    # them in the write that finished its publication. Re-applying a value
    # already written is a no-op rather than a second count. We flip DIRECTLY
    # to `validating` so the reviewer re-evaluates the new head next tick. Docs
    # do not run on this exit -- the single docs pass is deferred to the
    # final-docs handoff after reviewer approval, so running the docs stage
    # against an unapproved diff here would just push a no-op and waste a tick.
    _late_gate_models._spend(ctx.state, owed)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
