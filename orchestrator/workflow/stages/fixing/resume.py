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
the batch it quoted is DELIVERED -- and which write records that forks on the
run's report outcome. A run that wrote no report settles its own readers right
there, ahead of every disposition below it, because nothing else is going to:
the size gate's own write and a park's own write both land inside the
disposition, so a settlement taken afterwards would be lost to a crash in
exactly the window a hold's relabel opens. A run that DID write one settles
nothing here at all -- both groups ride the record of that report, and the
write that completes the publication is what applies them, so a report no
reviewer ever receives cannot leave the feedback behind it recorded as
answered.

What the batch is, on a `/orchestrator continue`, is the replay JOINED with
the fresh rescan. The prompt quotes the replay alone -- the bare command is a
control and must never be what the dev is asked to implement -- while the
settlement covers both, each item against the reader of the surface it was
posted on (`feedback.py`). That is what advances the issue-action boundary
over a replayed issue-thread reply instead of leaving it for the stage a
relabel hands the issue to.

Then the disposition. A reply that reached for the report contract and MISSED
is held ahead of all of it, because neither half of such a message may be acted
on. The ACK fast path is in_review-route only -- the validating reviewer asked
for a concrete change, so an ACK there is not an answer -- it stands down on a
stranded commit, because the ack vouches for the feedback and not for what the
PR head actually carries, and it stands down on an issue that OWES a report,
which is a debt read off the record rather than off this run. A pushed fix
drops the bookmarks, updates `review_round` per the route, and flips straight to
`validating`; where a report is owed, the publication comes first and holds
every one of those until it lands. Docs do not run on this exit: the single docs
pass belongs to the final-docs handoff after reviewer approval.
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
    report_delivery as _report_delivery,
    report_outcomes as _report_outcomes,
    usage as _usage,
)
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    feedback as _feedback,
    models as _models,
    report_recovery as _report_recovery,
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

    What `review_round` becomes is the route's own answer, read ONCE here and
    carried as a frozen pair from there. The in_review route (`pending_fix_at`
    set) RESETS it: the reviewer round before it was APPROVED -- that stage's
    HITL ping is gated on approval -- so the new fix starts a fresh count and
    `MAX_REVIEW_ROUNDS` does not trip early on an issue passing back through
    review after a human PR comment. The validating route BUMPS it: the round
    before it was CHANGES_REQUESTED, so this is the same review cycle and the
    counter has to advance to keep that cap honest. The bump reads the counter
    off the pinned comment, which is why a second reading taken after the write
    that already applied it would count the same round twice.
    """
    return _late_gate_models._Spends(fields=(
        *_bookmarks._cleared_pending_fix_bookmarks(),
        (
            _state._REVIEW_ROUND,
            0 if pending_fix_at_was_set
            else int(state.get(_state._REVIEW_ROUND) or 0) + 1,
        ),
    ))


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
    change, so an ACK there is not an answer. A run that timed out or moved
    HEAD is not a no-commit reply at all -- and neither is one whose HEAD this
    tick could not READ. An `ACK:` asserts that nothing changed and nothing
    needed to, which is a claim about the branch, and an unread head is no
    evidence about the branch at all: a probe that failed answers the same
    empty string for a checkout that committed and one that did not. Taken on
    it, the round clears the bookmarks, advances the readers and hands the pull
    request back as needing nothing, while any commit that run made sits in the
    worktree with no report owed for it and no road left that asks for one.
    Declined, the disposition behind this refuses to publish off a head it
    could not read either, and parks for a human -- which is the right answer
    for a tick that cannot say what its own developer did.

    An issue that OWES a report is excluded too, and the debt is read HERE off
    the record rather than handed in by a caller reading this run: a round that
    reported has the publication ahead of it rather than a relabel, and one
    that did not can still be standing on a report an earlier tick could not
    deliver -- returning the pull request to review there would present it as
    needing nothing while the report it owes is still on the pinned comment and
    nothing has gone out. A reply that reached for the contract and MISSED
    never gets this far: its caller holds it for a human first, since an `ACK:`
    written beside a report is the commonest way to miss and this path would
    read exactly that half of it.

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
    the reviewer. That probe is reached only on a head that READ, since an
    unread one has already declined above.

    The consumed batch is recorded by the caller ahead of this call, on the ack
    and the fall-through alike: the reading that says the feedback needs no
    change is the same reading that says a developer read it.
    """
    if not routed or run.dev_result.timed_out:
        return False
    if _report_delivery.owes_a_report(ctx.state):
        return False
    if not run.after_sha or run.after_sha != run.before_sha:
        return False
    ack_reason = _messages._drift_ack_reason(run.dev_result.last_message or "")
    if not ack_reason or _stranded._stranded_fix_unpushed(
        ctx.spec, run.worktree, ctx.state, ctx.issue,
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


def _records_the_report_it_owes(
    ctx: _models._FixingContext,
    run: _models._FixingResumeRun,
    feedback: _models._FixingFeedback,
    owed,
) -> bool:
    """Hold this round to the report contract, and record the report it wrote.

    True is a tick this call ended: a run that COMMITTED and handed over no
    report, one that did not finish at all, and a report this build cannot
    record. All three park with the commit still in the worktree and nothing
    published, because the reviewer at the end of any of them would be handed
    an implementation nobody described and no session left to ask.

    Which runs are held to the contract is the caller's road rather than this
    workflow's: a run that committed owes the report of what it committed,
    whatever the branch was already carrying, while a run that committed
    NOTHING owes one only where it wrote one. A commit an EARLIER run stranded
    is a different question asked of a different run, so a reply that brought
    no report is the ordinary question its own road reads it as, and the debt
    that earlier run left is what holds the reviewer off the head this
    publishes.

    What a recorded report carries is the pairs this round CONSUMED, frozen
    before anything applies them -- the record has to name what was consumed
    rather than what is left to consume, since derived after a settlement they
    are empty and the recovery replaying this record would have nothing to put
    the feedback beyond. A run that reported nothing has settled its own
    readers ahead of this call, so it hands over none: there is no transaction
    to carry them, only the park that ends the road.
    """
    if not run.reported and (
        not run.after_sha or run.after_sha == run.before_sha
    ):
        return False
    consumed = ()
    if run.reported:
        consumed = _feedback._consumed_delivery(
            ctx.state, feedback,
        ).consumed_pairs(ctx.state)
    return _reporting._recording_stops_the_tick(ctx, run, consumed, owed)


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
    publish an interrupted run -- and the next tick would see nothing to do and
    bounce a PR head that is missing the fix. Left on disk, a later clean run
    republishes it through the stranded-fix tail.
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
    route ACK fast path, the `validating` relabel a pushed fix or a published
    report earns, or a park.

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

    # What this route owes for the candidate, frozen BEFORE anything is
    # written: the bookmarks the consumed batch clears and the round the fix
    # lands on. Read once, so a second reading taken after the write that
    # already applied it cannot count the same round twice.
    owed = _spends_fix_round(ctx.state, pending_fix_at_was_set)

    # The prompt reached an agent, so the batch it quoted is delivered whatever
    # the run came back with -- a fix, a timeout, an empty message, a question,
    # an `ACK:`. A run that wrote NO report records that right here, because
    # nothing else is going to: the size gate's own write and a park's own
    # write both land inside the disposition, so a settlement taken afterwards
    # would be lost to a crash in exactly the window a hold's relabel opens.
    # Only ids this prompt carried move: a human comment that landed after
    # `feedback` was built was never quoted, so swallowing it would drop real
    # feedback on the pushed path (the next in_review tick would miss it) and
    # on the park path (the next fixing tick's `awaiting_human and not
    # new_feedback` gate would drop it). A run that DID write one records
    # nothing here at all -- both groups ride that report's record, and the
    # write completing the publication is what applies them.
    if not run.reported:
        _feedback._settle_consumed_feedback(ctx.state, delivered)

    # The two replies this round may act on no half of, held ahead of every
    # road below. A message that reached for the report contract and MISSED is
    # one: the `ACK:` half would return the pull request to review as needing
    # no change, and a commit beside it would be pushed and relabelled with no
    # report on the pull request at all. A round that COMMITTED over a report
    # an earlier tick recorded is the other: that report describes the branch
    # before this commit, so every road that publishes afterwards would bind
    # it to work it never saw. Both park after the settlement above, so the
    # notice is never left standing over feedback that still reads as unread.
    if _reporting._holds_for_a_human(ctx, run):
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return

    # The report contract itself, which this round answers before anything of
    # it may go out: the report of a commit this run made is recorded ahead of
    # the size gate, and a run that committed with none parks instead.
    if _records_the_report_it_owes(ctx, run, delivered, owed):
        return

    # ACK fast path (in_review route only): the dev made no commit but
    # explicitly signaled via the `ACK: <reason>` marker that the PR feedback
    # carries no actionable change. Any other unmarked no-commit reply falls
    # through to the disposition, which parks for the human unless its
    # stranded-fix check publishes a committed-but-unpushed fix instead
    # (`validating/stranded.py`'s probe).
    if _fixing_ack_fast_path(ctx, run, routed=pending_fix_at_was_set):
        return

    _disposes(ctx, run, owed)


def _disposes(
    ctx: _models._FixingContext, run: _models._FixingResumeRun, owed,
) -> None:
    """Publish what this run left, and close the round on what was published.

    Three roads out. A round whose whole answer is its report publishes that
    and nothing else. A round that pushed code closes on the report where the
    ISSUE owes one -- its own, or one an earlier tick recorded and a crash left
    unbound, since this push is the publication that report was waiting for --
    and on the frozen pairs where none is owed. And a round that published
    nothing closes nothing: a non-reporting run already settled its own readers
    ahead of this call, and a reporting one is still carrying both groups on
    its record for the write that completes the publication. The bounce that
    republishes that commit is what binds it; settled here instead, the
    feedback would read as answered for a report no reviewer has.

    A round that committed over a report an EARLIER tick recorded never gets
    here at all: its caller holds it for a human first, because the record it
    would be published against describes the branch before that commit.
    """
    # Asked of the RECORD rather than of this run, and past whatever this tick
    # has just written to it: a debt an earlier tick left is this round's to
    # honour too, and a round that has just recorded its own report owes one
    # from this line onwards.
    owes = _report_delivery.owes_a_report(ctx.state)

    # A round whose whole answer IS the report never reaches the publication
    # tail: there is no commit to push, and the prompt asked for exactly that
    # -- an item wanting report content only is answered in the report, with no
    # commit for it.
    #
    # What it is bound to is the head the reading PROVED -- the checkout's own,
    # which that reading held against a pull request it re-read -- never the
    # copy the preflight fetched. The two can disagree in either direction: a
    # remote that moved AWAY from the round's head refuses the reading
    # outright, and one that moved ONTO it passes while the stale copy still
    # names the commit it moved off. Bound to that copy, the report would be
    # published and recorded against a commit the pull request has left, and
    # the reviewer handed a head nothing describes.
    #
    # A reading this tick could not TAKE is neither road: a pull request it
    # could not fetch, a head the checkout would not name, a tree status that
    # established nothing. The report is valid and the branch is wherever it
    # was, so everything is HELD where it stands -- nothing published, nothing
    # parked, the record exactly as this tick wrote it -- and the recovery
    # ahead of a later handler publishes it on the first tick that can read
    # them. Sent down the no-commit road instead, a round that reported earns
    # a park saying its developer asked a question, and the tick that finally
    # publishes hands the issue to review under a park no settlement owns and
    # no reviewer runs behind.
    placed = _reporting._is_report_only(ctx, run) if run.reported else False
    if placed is None:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    if placed:
        _reporting._finishes_a_reported_round(ctx, owed, run.after_sha or "")
        return

    # A round that REPORTED and whose own checkout refuses for good ends here
    # instead, under the terminal park that report owns (`report_recovery`).
    # The two refusals behind that answer -- a worktree gone, a tree proved
    # dirty -- are the same ones the recovery declines on, and no later poll
    # takes either back: whether the round committed or not, nothing on this
    # host is going to publish that report until a human acts.
    #
    # Left to the road below it takes a checkout park of the road's own and
    # keeps the record, and the tick after it is the recovery -- which finds
    # the identical refusal, releases the report and posts a SECOND notice for
    # one condition, with the pairs that round consumed unapplied in between.
    # A terminal road owes them in its own durable write, so the park that
    # ends this one applies them and the reply it asks for resumes a developer
    # over what has actually gone unanswered.
    if run.reported and _report_recovery._releases_an_unpublishable_report(
        ctx, run.worktree,
    ):
        return

    # The gate is handed NOTHING to close while a report stands: the record is
    # carrying this route's bookkeeping, and a receipt write that closed it
    # here would drop the batch an outstanding publication replays from.
    pushed = _dev_fix._handle_dev_fix_result(
        ctx.gh, ctx.spec, ctx.issue, ctx.state, run.worktree, run.dev_result,
        run.before_sha, after_sha=run.after_sha,
        spends=_late_gate_models._SPENDS_NOTHING if owes else owed,
    )

    if not pushed:
        # A hold has already spent this route's round durably, from inside the
        # gate's own write; what is left here is the caller's ordinary write.
        # It carries the consumption a NON-reporting run settled ahead of all
        # of it, and nothing at all for a reporting one -- that round's pairs
        # are on its record, for the write that finally publishes the report.
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return

    if owes:
        # The report rides the commit this push landed -- the one this run
        # wrote, or the one an earlier tick recorded and this push has just
        # given a publication to.
        _reporting._finishes_a_reported_round(ctx, owed, run.after_sha or "")
        return

    # The bookmarks this route consumed and the round it lands on, in the
    # values frozen before the push. The gate has already written them beside
    # the receipt, so this is what covers the one push it could not: a commit
    # nothing could name never reaches that write. Re-applying a value already
    # written is a no-op rather than a second count. We flip DIRECTLY to
    # `validating` so the reviewer re-evaluates the new head next tick. Docs do
    # not run on this exit -- the single docs pass is deferred to the
    # final-docs handoff after reviewer approval, so running the docs stage
    # against an unapproved diff here would just push a no-op and waste a tick.
    _late_gate_models._spend(ctx.state, owed)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
