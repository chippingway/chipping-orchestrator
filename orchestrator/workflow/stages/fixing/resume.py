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
the batch it quoted is DELIVERED and is settled right there, ahead of every
disposition below it: the size gate's own write and a park's own write both
land inside the disposition, so a settlement taken afterwards would be lost to
a crash in exactly the window a hold's relabel opens. A run that finished on a
report outcome settles nothing here at all -- that report is a publication
this tick cannot guarantee, and feedback recorded as answered for a report no
reviewer has is the one reading this fork exists to refuse.

What the batch is, on a `/orchestrator continue`, is the replay JOINED with
the fresh rescan. The prompt quotes the replay alone -- the bare command is a
control and must never be what the dev is asked to implement -- while the
settlement covers both, each item against the reader of the surface it was
posted on (`feedback.py`). That is what advances the issue-action boundary
over a replayed issue-thread reply instead of leaving it for the stage a
relabel hands the issue to.

Then the disposition. The ACK fast path is in_review-route only -- the
validating reviewer asked for a concrete change, so an ACK there is not an
answer -- and it stands down on a stranded commit, because the ack vouches for
the feedback and not for what the PR head actually carries, and on any reply
that USED the report contract: one that reported is a handover to a fresh
reviewer rather than a reason to re-arm a ready ping, and one that reached for
the contract and missed -- a report block with an `ACK:` beside it -- is a
broken contract rather than an acknowledgement to act on.

What the disposition holds every round to is `validating/fix_reports`': the
report of a commit is recorded ahead of the size gate, a report with no code in
it is delivered onto the head the pull request is PROVED to be standing on, and
a commit an earlier round stranded still passes that gate. A round that hands
the pull request back -- pushed, or reported -- flips to `validating` and binds
the report behind that label, where the review hold keeps the reviewer off
until it is confirmed. What the handover COSTS is written by whoever confirmed
it: a pushed fix spent its round on a commit the pull request now carries, so
the gate's own receipt write carries the bookmarks and the round, while a
report with no code in it has bought nothing until it lands and leaves both to
the write that settles it. Docs do not run on this exit: the single docs pass
belongs to the final-docs handoff after reviewer approval.

The batch a reporting round delivered rides that report's own record, which is
what closes the fork above: on the road where the report IS the handover -- no
commit, nothing else new on the pull request -- the readers move in the write
that settles the report, so feedback is recorded as answered exactly when the
report answering it lands. The round and the bookmarks ride the record too, for
that same road, which passes no size gate at all. Every other road answered the
feedback in something already there -- a pushed fix in code, a park in a notice
a human is being asked to read -- so the settlement is taken in this caller's
own write, and the record re-applies the same pairs later as a no-op.
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
    report_outcomes as _report_outcomes,
    report_records as _records,
    usage as _usage,
)
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    feedback as _feedback,
    models as _models,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    resume as _dev_resume,
)
from orchestrator.workflow.stages.validating import (
    fix_reports as _fix_reports,
    report_settlement as _report_settlement,
    state as _validating_state,
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
        reported=_report_outcomes._finished_on_a_report(dev_result),
    )


def _fixing_ack_fast_path(
    ctx: _models._FixingContext,
    run: _models._FixingResumeRun,
    *,
    routed: bool,
) -> bool:
    """In_review-route ACK fast path. Returns True (and relabels to
    `in_review`) when the dev's no-commit reply carried an explicit
    `ACK: <reason>` marker vouching that the PR feedback needs no actionable
    change; False to fall through to the report-aware disposition.

    Three shapes never reach the marker. The validating CHANGES_REQUESTED route
    (`routed` false) is excluded because that reviewer asked for a concrete
    change, so an ACK there is not an answer. A run that timed out or
    moved HEAD is not a no-commit reply at all.

    And a reply that USED the report contract is excluded whether it used it
    well or badly, which is the wider reading rather than "finished on a
    report". One that reported is a handover the next reviewer has to read, so
    it takes the fresh-review road the disposition below gives it rather than
    re-arming a ready ping on the approval that report supersedes. One that
    reached for the contract and MISSED -- a report block with an `ACK:` line
    beside it, text after the outcome, a marker that may render as code -- is
    one broken contract rather than two answers, and reading the
    acknowledgement out of it would hand the pull request back to review over
    work whose report nothing carries. Both fall through to the disposition,
    which has a park for a reply it cannot act on; only a reply that never used
    the contract at all is the ordinary acknowledgement this fast path is for.

    A vague "continue" / "ok" nudge should not strand a complete, mergeable PR
    in `fixing`, so an ack returns to `in_review` (re-arming the ready-ping)
    instead of parking.

    The fast path stands down on the stranded-fix shape: the ack vouches for
    the *feedback*, not for the publish state, so when the clean HEAD is
    strictly ahead of the remote PR branch (a fix a prior parked run committed
    but never pushed -- e.g. a dirty-park whose stray files were later cleaned
    up) relabeling to `in_review` here would clear the bookmarks and present a
    PR head that is still missing the committed fix.
    Falling through lets the disposition publish the stranded HEAD through its
    normal push tail and the pushed-fix exit route the freshened head back to
    the reviewer. The stranded check is skipped when `after_sha` is unreadable
    (mirrors the disposition's own gate -- no pushing blind off a worktree
    whose HEAD we could not read).

    The consumed batch is recorded by the caller ahead of this call, on the ack
    and the fall-through alike: the reading that says the feedback needs no
    change is the same reading that says a developer read it.
    """
    if not routed or run.dev_result.timed_out:
        return False
    if _report_outcomes._reached_for_a_report(run.dev_result):
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
    the feedback while the commit sits unpushed -- the disposition refuses to
    publish an interrupted run -- and the next tick would see
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
    replay_batch: _models._FixingFeedback | None,
) -> None:
    """Resume the locked dev session over the unread feedback (or a preserved
    `/orchestrator continue` batch), then dispatch the result: the in_review-
    route ACK fast path, the bounce back to `validating` a pushed fix or a
    delivered report earns, or a park.

    Runs after the quiet window has elapsed. Owns the resume, the three
    refusals that count no delivery at all, the settlement of the batch that
    WAS delivered -- here, or on the record of the report that answers it --
    the route round bookkeeping, and the binding of whatever report the round
    recorded.
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
    #
    # What that round CONSUMED is the replay joined with the whole fresh
    # rescan, and the difference between the two is deliberate: the prompt
    # drops the bare command because the dev must not be told to implement the
    # word "continue", while the settlement has to record it as answered or
    # the retry re-fires on the next poll. Every other item is in both, on the
    # surface it was posted on -- which is what advances the issue-action
    # boundary over a replayed issue-thread reply instead of leaving it for
    # the stage a relabel hands the issue to.
    delivered = (
        feedback if replay_batch is None else replay_batch.merged_with(feedback)
    )
    run = _run_fixing_resume(ctx, _conversation_prompts._build_pr_comment_followup(
        (feedback if replay_batch is None else replay_batch).all_items,
    ))

    # Nothing below may run for a batch no agent read (`_delivered_nothing`),
    # and none of it persists: the awaiting_human reset and the hash refresh
    # staged earlier this tick are dropped with the write we skip.
    if _delivered_nothing(ctx, run):
        return

    # The prompt reached an agent, so the batch it quoted is delivered whatever
    # the run came back with -- a fix, a timeout, an empty message, a question,
    # an `ACK:`. Recorded HERE rather than after the disposition, because the
    # size gate's own durable write and a park's own both land inside that
    # disposition and a settlement taken afterwards would be lost to a crash in
    # the window a hold's relabel opens. Only ids this prompt carried move: a
    # human comment that landed after `feedback` was built was never quoted, so
    # swallowing it would drop real feedback on the pushed path (the next
    # in_review tick would miss it) and on the park path (the next fixing
    # tick's `awaiting_human and not new_feedback` gate would drop it). The
    # orchestrator's own park comment needs no bump to avoid replay -- the next
    # tick's rescan filters by both recorded id and body marker.
    #
    # A run that finished on a report outcome is the one exception, and the
    # reason is the publication it owes: a report this tick cannot guarantee
    # reaches the pull request may not leave the feedback it answers recorded
    # as read. What carries it instead is that report's own record, frozen
    # below, so the readers move in the write that settles it.
    if not run.reported:
        _feedback._settle_consumed_feedback(ctx.state, delivered)

    # ACK fast path (in_review route only): the dev made no commit but
    # explicitly signaled via the `ACK: <reason>` marker that the PR feedback
    # carries no actionable change. Any other unmarked no-commit reply falls
    # through to the disposition, which parks for the human unless its
    # stranded-fix check publishes a committed-but-unpushed fix instead
    # (`validating/stranded.py`'s probe).
    if _fixing_ack_fast_path(ctx, run, routed=pending_fix_at_was_set):
        return

    # What this route owes for the candidate, computed BEFORE the push and
    # handed to the gate: a hold closes it in the write that carries the
    # measurement, ahead of the relabel it makes, and a landed push closes it
    # in the write that carries the receipt. Either way the same frozen pairs
    # are what the tail below re-applies, so the two cannot disagree -- and
    # re-applying a value already written is a no-op rather than a second
    # count, which recomputing the round from the pinned comment would be.
    # A report with no code in it passes no gate at all, so on that road the
    # record and this caller's own write are the only things that carry them.
    owed = _spends_fix_round(ctx.state, pending_fix_at_was_set)
    outcome = _fix_reports._post_requested_fix_result(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, run.worktree, run.dev_result,
        run.before_sha, after_sha=run.after_sha, spends=owed,
        # The road this run came down, which holds it to the report contract:
        # the report of a commit it made is recorded ahead of the gate, and a
        # report with no commit is published onto the head the pull request
        # already carries. The round, the bookmarks and the batch this prompt
        # delivered ride that record, so the write that settles a report no gate
        # ever saw is the write that closes them. The requirements revision is
        # left to the pinned baseline the resume above has just refreshed over
        # the comments it quoted.
        handed=_records.HandedRun(
            WorkflowLabel.FIXING,
            spends=owed.fields,
            watermarks=_feedback._consumed_pairs(ctx.state, delivered),
        ),
    )

    _settles_what_the_report_will_not(ctx, delivered, run, outcome)

    if outcome not in _validating_state._REPORTING_OUTCOMES:
        # A hold has already spent this route's round durably, from inside the
        # gate's own write: what is left here is the caller's ordinary write,
        # carrying whichever settlement this round's road called for.
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return

    # The bookmarks this route consumed and the round its handover lands on, in
    # the values frozen before the push -- and only for the handover a PUSH
    # made. The gate has already written them beside its receipt, so this
    # re-applies the same pair to cover the one push it could not: a commit
    # nothing could name never reached that write. A report with no code in it
    # reached no gate and has bought no handover until it is on the pull
    # request, so nothing of it is written here at all: the pair rides the
    # record, and the write that settles the report is what closes it.
    #
    # We flip DIRECTLY to `validating` either way, and before the binding, so
    # the reviewer re-evaluates the report and requirements being handed on --
    # a reporting round hands over the same head, and an earlier approval is no
    # answer to it. That move is also the only road to confirmation: the review
    # hold there is what binds a delivery and settles it, and it refuses every
    # reviewer while the report is owed. Docs do
    # not run on this exit -- the single docs pass is deferred to the final-docs
    # handoff after reviewer approval, so running the docs stage against an
    # unapproved diff here would just push a no-op and waste a tick.
    if outcome == _validating_state._OUTCOME_PUSHED:
        _late_gate_models._spend(ctx.state, owed)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    # Bound only once the relabel is behind it, so no tick finds a settled
    # report beside a label still claiming the round it closed. A process dying
    # before this line leaves the report owed, which the review hold on
    # `validating` answers on the next tick either way.
    _report_settlement._settles_the_report(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, WorkflowLabel.VALIDATING,
    )


def _settles_what_the_report_will_not(
    ctx: _models._FixingContext,
    delivered: _models._FixingFeedback,
    run: _models._FixingResumeRun,
    outcome: str,
) -> None:
    """Settle a reporting round's batch on every road but the report's own.

    The fork ahead of the disposition withholds the settlement from a run that
    reported, because a report this tick cannot promise may not leave the
    feedback it answers recorded as read. Which road the round took is what
    says whether that is still true once the disposition has answered.

    A reported run whose outcome is `reported` is the ROAD WHERE THE REPORT IS
    THE HANDOVER: nothing but the report reached the pull request, so the
    readers wait for it and move in the write that settles it. Recorded here
    instead, a report that never landed would leave this round's feedback
    claimed as consumed with nothing on the pull request to show for it.

    Every other road answered the feedback in something the pull request or the
    thread already carries. A PUSHED fix answered it in code that is now on the
    pull request, and a PARK answered it with a notice a human is being asked
    to read -- and that park is on `workflow:fixing`, so a batch left unread
    under it is one the next tick reads as fresh feedback and resumes the
    developer over again. Both settle in the caller's write, and the record
    re-applies the same pairs when it settles, which is a no-op.
    """
    if run.reported and outcome != _validating_state._OUTCOME_REPORTED:
        _feedback._settle_consumed_feedback(ctx.state, delivered)
