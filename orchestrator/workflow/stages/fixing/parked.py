# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a tick that arrived `awaiting_human` is allowed to do about it.

Four answers, and the order they are asked in is what keeps them from
overlapping. A park filed by the base-sync retry loop is refused first and
silently: the operator's new comment there is the "retry the rebase" signal
that loop owns, and consuming it as PR feedback would resume the dev on a
prompt with nothing to do with the outstanding fix. `/orchestrator continue`
comes next because it is explicit -- an operator naming the retry beats any
inference made below it, and it is honored on BOTH routes so a session-failure
park never resumes on the bare command text.

The silent recovery is third and is the narrowest of the four. It fires on the
validating route, because that is the route whose transient park (`push_failed`
/ `agent_timeout`) landed under `fixing` without any human involvement -- the
CHANGES_REQUESTED branch relabels before it spawns the dev -- and so is the one
that can clear without a human comment. Running it on the in_review route would
ordinarily advance the PR-feedback watermarks past a human comment on a
timed-out resume and mis-account `review_round`, which that route resets rather
than bumps; `pending_fix_at` is the discriminator.

One shape of that route is the exception, and it is one where neither objection
holds: a `push_failed` park with a report still OWED. Both groups are frozen on
that report's record -- the readers are the settlement's to move and the round
is the settlement's to spend -- so the retry is handed nothing to count, and the
batch that report answers reads as unread for exactly as long as the publication
is missing, so the default below would hold the issue on a park nothing clears.
The retry that lands publishes the report on the push it made.

It is silent only while it is failing: the park that filed it mentioned a human,
so the tick that finally clears it says so once, in the same words the
validating route uses.

Everything else stays parked until a human replies. That default is the HITL
contract, not a gap: an agent with a real question and an agent reporting
nothing to change both surface as the same park, so auto-routing either would
answer for the human.

What counts as a reply is the one reading the readers cannot give on their own.
While a report is OWED they are held back until its publication lands, so the
batch that report was written over reads as unread for as long as the push or
the post keeps failing -- and a park cleared over it resumes a developer on the
prompt the outstanding report already answers, on every poll, with nobody having
written anything. The record's own frozen pairs say which batch that is, and a
rescan with nothing above them is no fresh reply here.
"""
from __future__ import annotations

from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.workflow.engine import (
    comments as _comments,
    messages as _messages,
    report_delivery as _report_delivery,
)
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    continue_command as _continue_command,
    drift as _drift,
    feedback as _feedback,
    models as _models,
    report_recovery as _report_recovery,
    reporting as _reporting,
    state as _state,
)
from orchestrator.workflow.stages.implementing import (
    late_publication_state as _late_publication_state,
)
from orchestrator.workflow.stages.validating import recovery as _validating_recovery, state as _validating_state
from orchestrator.workflow.state import WorkflowLabel

# The decision every road here but an accepted replay comes back with: this
# tick is fully handled and the caller returns at once.
_HANDLED = _models._ParkedFixingDecision(stop=True)

# The two silent-recovery answers that end the tick where they are found,
# grouped because what they owe the issue is identical: nothing. One is the
# size gate having taken the candidate, the other the reading of the branch
# having withheld the clear, and neither may fall through to the drift reroute.
_ENDS_THE_TICK_AS_FOUND = frozenset((
    _validating_state._OUTCOME_HELD, _validating_state._OUTCOME_UNSETTLED,
))


def _dispatch_continue_command(
    ctx: _models._FixingContext, feedback: _models._FixingFeedback,
) -> _models._ParkedFixingDecision | None:
    """Apply a `/orchestrator continue` command to a parked tick.

    Returns a `_ParkedFixingDecision` for every road a resolved command takes:
    a refused content-free continue stops the tick, and an accepted replay and
    a PASSTHROUGH both clear the park and hand the resume the batch it may
    quote. ``None`` is the command this owner did not resolve at all.

    The passthrough is the command arriving WITH something to act on where no
    preserved batch could be rebuilt, and what it hands over is that reading
    minus the command itself. The prompt renders whatever it is given as pull
    request feedback to implement, so the bare line would be handed to a
    developer as work -- and the operator wrote it to the orchestrator. It
    costs nothing to drop: what the resume SETTLES is the batch it was handed
    joined with the whole fresh rescan, so the command is consumed exactly as
    the refusal road consumes one and does not re-fire next tick.

    An owed report is what makes that road ordinary rather than rare. The
    readers behind such a report are held until its publication lands, so the
    batch it was written over still reads as unread beside the command -- and
    the stay-parked default behind this one would refuse the operator's retry
    as "nothing new" on every poll.

    The park flags come down with the decision, since the caller's own clear
    sits on the road this return skips, and the session is left ALONE: the
    replay above drops a poisoned one because its park was a session failure,
    while a park that reached here is waiting on an answer rather than on a
    session that died.
    """
    action, replay_items = _continue_command._handle_continue_command(ctx, feedback)
    if action == "refuse":
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return _HANDLED
    if action == "passthrough":
        replay_items = _continue_command._carried_fresh_feedback(feedback)
    elif action != "replay":
        return None
    ctx.state.set(_state._AWAITING_HUMAN, False)
    ctx.state.set(_state._PARK_REASON, None)
    return _models._ParkedFixingDecision(stop=False, replay_batch=replay_items)


def _dispatch_validating_recovery(
    ctx: _models._FixingContext,
    feedback: _models._FixingFeedback,
    park_reason,
    *,
    answered: bool,
) -> _models._ParkedFixingDecision | None:
    """Attempt silent recovery of a validating-route transient park.

    Returns a stop-decision when this branch owns the tick (a stuck transient
    rerouted to `resolving_conflict` on drift, a park the branch reading
    withheld the clear from, or a resolved transient flipped back to
    `validating`, which also posts the one follow-up comment retiring the
    mention the park was filed with), or ``None`` to fall through to the
    stay-parked / clear-park default.

    Only `stuck` reaches the drift reroute, and the narrowness is the contract
    the retry answers in: a condition that has not resolved may really be a
    base advance nobody synced, while an `unsettled` answer is the reading of
    the branch itself refusing. Rerouted on that one, the park would come down
    and the checkout be published by a road that stages no report debt for the
    head it leaves -- which is the one thing the reading was withheld to stop.

    `answered` says the rescan found nothing this issue has not already been
    handed -- a report it OWES was written over that very batch, and the
    readers are held back until the publication lands -- so it counts as no
    fresh comment at all here, exactly as an empty rescan does.

    Only fires when the park reason can resolve without a human comment AND
    the park is one this road may answer (`_recovers_without_a_human`).
    """
    owes = _report_delivery.owes_a_report(ctx.state)
    if (
        (feedback.all_items and not answered)
        or park_reason not in _validating_state._VALIDATING_TRANSIENT_PARK_REASONS
        or not _recovers_without_a_human(ctx.state, park_reason, owes=owes)
    ):
        return None

    recovery = _validating_recovery._try_recover_validating_transient_park(
        ctx.gh, ctx.spec, ctx.issue, ctx.state,
    )
    if recovery in _ENDS_THE_TICK_AS_FOUND:
        # `held` is the size gate having taken the candidate this retry was
        # about: it has already parked the issue or handed it to the
        # adjudication and written its own state, so a clear here would
        # announce a recovery that did not happen and a relabel would move a
        # label the gate has just set. `unsettled` is the reading of the BRANCH
        # having withheld the clear -- nothing could place the checkout against
        # its pull request, or a drift park stands over a commit the pull
        # request has not got -- so the park stays exactly as it was filed, and
        # the notice that filed it says what a second one would. Neither may
        # reach the drift reroute below: the first would step on the state the
        # gate just wrote, the second would hand `resolving_conflict` a
        # checkout it publishes with no report debt staged for it.
        return _HANDLED
    if recovery == _validating_state._OUTCOME_STUCK:
        # The transient condition has not resolved on its own (e.g.
        # `push_failed` keeps failing). When the worktree has drifted from
        # the PR head in the meantime, hand the reconciliation to
        # `resolving_conflict` rather than sit parked forever -- the per-tick
        # base sync deliberately stands down on every `awaiting_human` park,
        # so nobody else will sync this worktree. Limiting the drift route to
        # this branch keeps the HITL contract intact: question / dirty /
        # silent / in_review-route transient parks fall through to the bare
        # stay-parked return below and keep waiting for a human comment.
        _drift._reconcile_parked_fixing(ctx)
        return _HANDLED

    # Conditions resolved (either no fix landed or a deferred push finished).
    # Post the follow-up BEFORE the clear, while `park_reason` still says what
    # healed, so the operator the park mentioned reads that the system took
    # care of it instead of having to diff remote SHAs to find out.
    followup = _validating_recovery._recovery_followup_comment(
        ctx.gh, ctx.issue, ctx.state, park_reason, recovery,
    )
    if followup is not None:
        _comments._post_issue_comment(ctx.gh, ctx.issue, ctx.state, followup)

    # The park's own condition has cleared, so the flags come down either way
    # -- in memory here, because this tick's own write is what carries them.
    # The window past the receipt that push already wrote is the hand-back's
    # to close: it retires the same park off the record, so a tick dying
    # before the publication cannot be relabelled over one.
    ctx.state.set(_state._AWAITING_HUMAN, False)
    ctx.state.set(_state._PARK_REASON, None)
    if owes:
        return _settles_the_recovered_report(ctx, recovery)

    # Flip back to `validating` so the reviewer re-evaluates the current head
    # next tick. The helper has already bumped `review_round` when a fix landed
    # (push_failed, or agent_timeout that finished its push). Clear the
    # pending_fix_* bookmarks defensively: with no report owed this branch only
    # fires when `pending_fix_at` was already None, so the clear is a no-op in
    # normal flow, but a stale bookmark from an earlier route would otherwise
    # mis-flag the next reviewer round.
    _bookmarks._clear_pending_fix_bookmarks(ctx.state)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    return _HANDLED


def _recovers_without_a_human(state, park_reason, *, owes: bool) -> bool:
    """Whether this park is one the silent recovery may answer at all.

    The validating route always is, and that is what this road was built for:
    `_handle_validating`'s CHANGES_REQUESTED branch flips to `fixing` BEFORE
    it spawns the dev, so a transient park lands under `fixing` rather than
    `validating` and nothing else would ever clear a condition that produces
    no human comment. `pending_fix_at` is the discriminator -- set by the
    in_review route, unset by the validating one.

    The in_review route is ordinarily excluded, for two reasons of its own: it
    advances the PR-feedback watermarks past a human comment even on a
    timed-out resume, and the shared helper counts a `review_round` on its
    `pushed` outcome, which that route RESETS rather than bumps -- so a
    deferred push would consume feedback without a fix and mis-account the
    round.

    A failed push with a report still OWED is the one shape where neither of
    those is true, and where staying out costs more than coming in. Both
    groups are frozen on the report's own record: the readers are the
    settlement's to move, the round is the settlement's to spend, and the
    retry below is handed nothing to count. And the batch that report answers
    reads as unread for exactly as long as the publication is missing, so the
    default behind this holds the issue on a park nothing can clear -- no
    later push is ever attempted, and the only ways out are a human comment or
    an `/orchestrator continue`, both of which pay a second developer to
    answer a batch the first one already answered.
    """
    if state.get(_state._PENDING_FIX_AT) is None:
        return True
    return owes and park_reason == _validating_state._REASON_PUSH_FAILED


def _settles_the_recovered_report(
    ctx: _models._FixingContext, recovery: str,
) -> _models._ParkedFixingDecision:
    """Publish the report the recovered push was the publication for.

    The park is cleared by the caller and NOTHING else here is: the bookmarks
    and the round ride the report's own record, and the write that completes
    the publication is what applies them. Spent or dropped by this road
    instead, a post GitHub refuses would leave the round counted and the
    replay source gone for a report no reviewer has.

    Only a push THIS retry landed is published against, read off the receipt
    that push has just written. The receipt is persistent, so on any other
    outcome it names an older round's commit -- and a report bound to that one
    describes work the developer never did. Every other outcome leaves the
    report owed for the road that can prove a commit, which is the recovery
    ahead of the next handler once the branch and the pull request agree.

    The relabel is the settlement's to authorize, and it is asked for through
    the same correlation a mark found already raised goes through: a delivery
    is claimed by one key whoever wrote it, so the record that settles here
    may belong to a route this stage never ran.

    That hand-back retires the same park off the record it settles from, which
    is what makes the caller's in-memory clear enough: the push landed durably
    a step ahead of the publication, so a tick dying between the two leaves the
    park standing -- and the road that publishes next brings it down rather
    than relabelling over it.
    """
    published = (
        _late_publication_state._published_commit(ctx.state)
        if recovery == _validating_state._OUTCOME_PUSHED
        else ""
    )
    if _reporting._holds_an_unpublished_report(ctx, published).owed:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return _HANDLED
    _report_recovery._finishes_a_settled_round(ctx)
    return _HANDLED


def _retries_an_unproved_branch(
    ctx: _models._FixingContext,
    feedback: _models._FixingFeedback,
    park_reason,
    *,
    answered: bool,
) -> _models._ParkedFixingDecision | None:
    """Let a quiet poll take again the branch reading a bounce could not.

    The one park on this stage that is waiting for a READING rather than for a
    person. The no-feedback bounce files it when nothing could place the
    checkout against its pull request -- a status that did not read, a fetch
    that did not return, a divergence git would not count -- and every one of
    those is a condition the next poll may simply find gone. Held by the
    stay-parked default behind this, the issue would sit on a network blip
    until somebody replied, with no later tick ever fetching again.

    So the road falls through WITHOUT clearing anything, and the bounce behind
    it is the single reader: it takes the reading again, publishes whatever
    that reading places, and retires this park in the write that relabels. A
    reading that refuses again holds silently -- the park is already standing
    and says exactly what a second notice would.

    Only on a quiet tick. A reply is the human road this park also offers, and
    the default below clears the flags and resumes the developer on their
    words; `answered` is the reading the readers cannot give for themselves, so
    a batch an owed report already covers counts as quiet here exactly as an
    empty one does.
    """
    if park_reason != _state._REASON_UNPROVED_BRANCH:
        return None
    if feedback.all_items and not answered:
        return None
    return _models._ParkedFixingDecision(stop=False)


def _dispatch_parked_fixing(
    ctx: _models._FixingContext, feedback: _models._FixingFeedback,
) -> _models._ParkedFixingDecision:
    """Reconcile a `fixing` tick that arrived with `awaiting_human` set.

    Returns a decision object. ``stop=True`` means the tick is fully handled
    and the caller must return immediately (auto-rebase park, a refused
    `/orchestrator continue`, a silent validating-route recovery, a park the
    branch reading behind that recovery withheld the clear from, a
    worktree-drift reroute, or a stay-parked-until-fresh-reply). ``stop=False``
    sends the caller on; `replay_batch` is
    the batch an accepted `/orchestrator continue` hands that resume -- the
    preserved feedback where one could be rebuilt, the fresh reading minus the
    command where none could -- and ``None`` on a plain human reply.

    Every road but one clears the park on its way out. The exception is the
    quiet re-read of a branch the bounce could not place: that park is waiting
    on a reading rather than on a person, so the flags stay exactly as they are
    and the bounce behind this retires them in the write that relabels -- which
    is what keeps a reading that refuses again from announcing itself twice.
    """
    park_reason = ctx.state.get(_state._PARK_REASON)
    # The refresh-time `_AUTO_REBASE_PARK_REASONS` parks belong to the
    # `_sync_pr_worktree_to_base` retry loop -- the operator's new comment is
    # the "retry the rebase" signal, NOT fresh PR feedback for the dev
    # fix-loop. Stay silent so the refresh keeps ownership of the comment;
    # resuming the dev here would spawn it on a prompt that has nothing to do
    # with the outstanding fix.
    if park_reason in _base_sync_state._AUTO_REBASE_PARK_REASONS:
        return _HANDLED

    # `/orchestrator continue` operator command (exact line, so a comment
    # carrying the command AND real guidance still counts). Handled on BOTH
    # routes so a session-failure park (`agent_silent` / `agent_timeout` /
    # `agent_execution_failed`) never
    # resumes the dev on the bare command text. A "replay" or "refuse"
    # decision owns the tick; a "passthrough" returns None and falls through.
    if _messages._parse_orchestrator_continue(feedback.issue_space):
        decision = _dispatch_continue_command(ctx, feedback)
        if decision is not None:
            return decision

    # What the readers cannot say on their own: a report this issue OWES may
    # have been written over the very batch the rescan just found, because
    # those readers are held back until its publication lands. That is not a
    # fresh reply, and clearing the park over it would resume a developer on
    # the prompt the outstanding report already answers -- every poll, for as
    # long as the push or the post keeps failing, with the human this park
    # mentioned never having said a word.
    answered = _feedback._read_by_an_owed_report(ctx.state, feedback)

    # The silent validating-route recovery, then the one park here that waits
    # on a READING rather than on a person: the branch the no-feedback bounce
    # could not place. A quiet poll falls through to that bounce with the flags
    # untouched, so it re-reads, publishes what the reading places, and retires
    # the park in the write that relabels.
    for claims_the_tick in (
        _dispatch_validating_recovery, _retries_an_unproved_branch,
    ):
        decision = claims_the_tick(
            ctx, feedback, park_reason, answered=answered,
        )
        if decision is not None:
            return decision

    if answered or not feedback.all_items:
        # All other awaiting_human shapes (question parks, dirty worktree
        # parks, silent-crash parks, in_review-route transients) stay parked
        # until a fresh human reply lands. We cannot distinguish "agent has a
        # real question" from "agent reported nothing to change" by inspection
        # -- both surface through `_on_question` with `park_reason=None` -- so
        # auto-routing either would silently bypass the HITL contract. The same
        # applies to a clean in-sync worktree on the in_review route: the dev
        # may have replied with a real question that needs a human to resolve,
        # so the only automatic exit from `fixing` for the in_review route is
        # the ACK fast path in the resume tail (on the same tick the dev
        # explicitly marks its no-commit reply with `ACK:`).
        return _HANDLED

    ctx.state.set(_state._AWAITING_HUMAN, False)
    ctx.state.set(_state._PARK_REASON, None)
    return _models._ParkedFixingDecision(stop=False)
