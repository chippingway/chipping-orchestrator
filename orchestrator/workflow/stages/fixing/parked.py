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

The silent recovery is third and is the narrowest of the four. It only fires
on the validating route, because that is the route whose transient park
(`push_failed` / `agent_timeout`) landed under `fixing` without any human
involvement -- the CHANGES_REQUESTED branch relabels before it spawns the dev
-- and so is the only one that can clear without a human comment. Running it
on the in_review route would advance the PR-feedback watermarks past a human
comment on a timed-out resume and mis-account `review_round`, which that route
resets rather than bumps. `pending_fix_at` is the discriminator. It is silent
only while it is failing: the park that filed it mentioned a human, so the tick
that finally clears it says so once, in the same words the validating route
uses.

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
from orchestrator.workflow.engine import comments as _comments, messages as _messages
from orchestrator.workflow.stages.fixing import (
    bookmarks as _bookmarks,
    continue_command as _continue_command,
    drift as _drift,
    feedback as _feedback,
    models as _models,
    state as _state,
)
from orchestrator.workflow.stages.validating import recovery as _validating_recovery, state as _validating_state
from orchestrator.workflow.state import WorkflowLabel


def _dispatch_continue_command(
    ctx: _models._FixingContext, feedback: _models._FixingFeedback,
) -> _models._ParkedFixingDecision | None:
    """Apply a `/orchestrator continue` command to a parked tick.

    Returns a `_ParkedFixingDecision` when the command was resolved (a refused
    content-free continue -> `stop=True`; an accepted replay -> `stop=False`
    with the preserved batch), or ``None`` for the "passthrough" case (the
    command arrived WITH genuine guidance on a park with no replayable batch),
    where the caller falls through to the validating-recovery / normal-resume
    path so that guidance drives the dev.
    """
    action, replay_items = _continue_command._handle_continue_command(ctx, feedback)
    if action == "refuse":
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return _models._ParkedFixingDecision(stop=True)
    if action == "replay":
        return _models._ParkedFixingDecision(stop=False, replay_batch=replay_items)
    return None


def _dispatch_validating_recovery(
    ctx: _models._FixingContext,
    feedback: _models._FixingFeedback,
    park_reason,
    *,
    answered: bool,
) -> _models._ParkedFixingDecision | None:
    """Attempt silent recovery of a validating-route transient park.

    Returns a stop-decision when this branch owns the tick (a stuck transient
    rerouted to `resolving_conflict` on drift, or a resolved transient flipped
    back to `validating`, which also posts the one follow-up comment retiring
    the mention the park was filed with), or ``None`` to fall through to the
    stay-parked / clear-park default.

    `answered` says the rescan found nothing this issue has not already been
    handed -- a report it OWES was written over that very batch, and the
    readers are held back until the publication lands -- so it counts as no
    fresh comment at all here, exactly as an empty rescan does.

    Only fires when the park reason can resolve without a human comment AND the
    issue arrived via the validating route (CHANGES_REQUESTED dev fix). The
    `_handle_validating` CHANGES_REQUESTED branch flips to `fixing` BEFORE
    spawning the dev, so a transient park (`push_failed` / `agent_timeout`)
    lands under `fixing` instead of `validating`; without this branch the issue
    would sit forever awaiting a human comment the underlying condition does
    not produce. Recovery must NOT run on the in_review route: that route
    advances the PR-feedback watermarks past the human comment even on a
    timed-out resume, and the shared helper bumps `review_round` on its
    `pushed` outcome, which the in_review route resets to 0 -- so a deferred
    push there would consume feedback without a fix and mis-account the round.
    The route discriminator is `pending_fix_at` (set by the in_review route,
    unset by the validating route).
    """
    validating_routed = ctx.state.get(_state._PENDING_FIX_AT) is None
    if (
        (feedback.all_items and not answered)
        or park_reason not in _validating_state._VALIDATING_TRANSIENT_PARK_REASONS
        or not validating_routed
    ):
        return None

    recovery = _validating_recovery._try_recover_validating_transient_park(
        ctx.gh, ctx.spec, ctx.issue, ctx.state,
    )
    if recovery == _validating_state._OUTCOME_HELD:
        # The size gate took the candidate this retry was about. It has
        # already parked the issue or handed it to the adjudication and
        # written its own state, so the drift reroute below is not this
        # tick's to take and the bounce is not this tick's to make.
        return _models._ParkedFixingDecision(stop=True)
    if recovery == "stuck":
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
        return _models._ParkedFixingDecision(stop=True)

    # Conditions resolved (either no fix landed or a deferred push finished).
    # Post the follow-up BEFORE the clear, while `park_reason` still says what
    # healed, so the operator the park mentioned reads that the system took
    # care of it instead of having to diff remote SHAs to find out.
    followup = _validating_recovery._recovery_followup_comment(
        ctx.gh, ctx.issue, ctx.state, park_reason, recovery,
    )
    if followup is not None:
        _comments._post_issue_comment(ctx.gh, ctx.issue, ctx.state, followup)

    # Clear the park flags and flip back to `validating` so the reviewer
    # re-evaluates the current head next tick. The helper has already bumped
    # `review_round` when a fix landed (push_failed, or agent_timeout that
    # finished its push). Clear the pending_fix_* bookmarks defensively: this
    # branch ONLY fires when `pending_fix_at` was already None, so the clear is
    # a no-op in normal flow, but a stale bookmark from an earlier route would
    # otherwise mis-flag the next reviewer round.
    ctx.state.set(_state._AWAITING_HUMAN, False)
    ctx.state.set(_state._PARK_REASON, None)
    _bookmarks._clear_pending_fix_bookmarks(ctx.state)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    return _models._ParkedFixingDecision(stop=True)


def _dispatch_parked_fixing(
    ctx: _models._FixingContext, feedback: _models._FixingFeedback,
) -> _models._ParkedFixingDecision:
    """Reconcile a `fixing` tick that arrived with `awaiting_human` set.

    Returns a decision object. ``stop=True`` means the tick is fully handled
    and the caller must return immediately (auto-rebase park, a refused
    `/orchestrator continue`, a silent validating-route recovery, a
    worktree-drift reroute, or a stay-parked-until-fresh-reply). ``stop=False``
    clears the park and the caller proceeds to the resume; `replay_batch` is
    the preserved feedback batch when an accepted `/orchestrator continue`
    replays it, otherwise ``None``.
    """
    park_reason = ctx.state.get(_state._PARK_REASON)
    # The refresh-time `_AUTO_REBASE_PARK_REASONS` parks belong to the
    # `_sync_pr_worktree_to_base` retry loop -- the operator's new comment is
    # the "retry the rebase" signal, NOT fresh PR feedback for the dev
    # fix-loop. Stay silent so the refresh keeps ownership of the comment;
    # resuming the dev here would spawn it on a prompt that has nothing to do
    # with the outstanding fix.
    if park_reason in _base_sync_state._AUTO_REBASE_PARK_REASONS:
        return _models._ParkedFixingDecision(stop=True)

    # `/orchestrator continue` operator command (exact line, so a comment
    # carrying the command AND real guidance still counts). Handled on BOTH
    # routes so a session-failure park (`agent_silent` / `agent_timeout`) never
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

    recovery = _dispatch_validating_recovery(
        ctx, feedback, park_reason, answered=answered,
    )
    if recovery is not None:
        return recovery

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
        return _models._ParkedFixingDecision(stop=True)

    ctx.state.set(_state._AWAITING_HUMAN, False)
    ctx.state.set(_state._PARK_REASON, None)
    return _models._ParkedFixingDecision(stop=False)
