# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A body edit during the final-docs hop, and the unwind it forces.

The reviewer approved the OLD requirements, so a docs pass started after the
edit would document a body the reviewer never saw. The stage does not try to
absorb that: it drops the stale approval, hands the worktree to `drift_reset`,
and routes the issue back to `validating` for a re-review. No docs agent runs
-- a commit on top of a dead approval would only have to be re-reviewed
alongside whatever the new body changes.

Two orderings carry the whole contract. `review_round` is cleared BEFORE any
fallible git step, because drift invalidates the approval whether or not the
on-disk reset succeeds -- an operator unpark after a failed fetch must not be
able to ride the stale round counter into a handoff that skips the re-review.
And `docs_drift_unwind_pending` is seeded at the same moment and cleared only on
the relabel, so a reconcile that parked is re-entered on the next tick instead
of falling through to the normal flow and advancing to `in_review` against the
old body. That re-entry is why a pending unwind with nothing fresh to act on
returns silently: only a trusted reply is the "retry it" signal, and without
that guard the same park comment would repost on every poll.

What this road does NOT record is the conversation. No developer is invoked
here -- the unwind is a relabel and a worktree reset -- so there is nothing to
say a human's words were delivered, and a watermark moved on the way past
would settle them for a label change. They stay unread for the reviewer the
relabel hands the issue to, and for the fix round behind it. That holds on the
failure road too, where the git step parks: the shared park stamps the thread
read as far as the notice it posted, so the park helper puts the delivery
cursor back and keeps that notice as the unwind's own boundary -- inside the
one write the park makes, since a correction a crash can land between is a
correction that strands the input. The requirements hash is the exception, and
it is not about the conversation: it says this stage has already rerouted for
this edit, which is what keeps the next poll from announcing it again.
"""
from __future__ import annotations

from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.github.comments import filter_trusted
from orchestrator.workflow.engine import (
    comments as _comments,
    drift as _engine_drift,
)
from orchestrator.workflow.stages.documenting import (
    drift_reset as _drift_reset,
    models as _models,
    parks as _parks,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel


def _announce_documenting_drift(
    ctx: _models._DocumentingContext, new_hash: str,
) -> None:
    """Record the new body hash and post the re-route notice.

    The hash is the whole of what this road records, and it records it for
    itself: it says this stage has already rerouted for this edit, so a second
    poll does not announce the same one again. Nothing about the CONVERSATION
    is recorded, because nothing here delivers it -- no agent runs on this
    road at all. The comments that moved the hash are read by the reviewer the
    relabel below hands the issue to, and a watermark advanced here would have
    marked them answered by a label change.
    """
    ctx.state.set("user_content_hash", new_hash)
    _comments._post_issue_comment(
        ctx.gh, ctx.issue, ctx.state,
        ":pencil2: issue body changed; routing back to "
        f"`{WorkflowLabel.VALIDATING}` so the reviewer re-evaluates the "
        "updated requirements.",
    )


def _begin_documenting_drift_unwind(ctx: _models._DocumentingContext) -> None:
    """Seed the drift-unwind sentinel and drop the stale approval.

    Set `docs_drift_unwind_pending` so an operator unpark or a later human
    comment (without a fresh drift) re-enters the drift block on the next tick
    and retries the reconcile + relabel; the marker is cleared ONLY on the
    success path that relabels to `validating`. Without it, an operator unpark
    on a failed reconcile would fall through to the normal flow and advance to
    `in_review` against the OLD body, skipping the required `validating`
    re-review.

    Clear `review_round` BEFORE any fallible cleanup (fetch / reset): drift
    means the prior reviewer approval is stale regardless of whether the
    on-disk reset succeeds, so the round counter must drop now -- an operator
    unpark or manual relabel after a fetch failure must not be able to ride
    the stale approval into a final-docs handoff that skips the re-review.
    """
    state = ctx.state
    state.set(_state._UNWIND_PENDING, True)
    state.set(_state._AWAITING_HUMAN, False)
    state.set(_state._PARK_REASON, None)
    state.set("review_round", 0)


def _reconcile_documenting_drift(ctx: _models._DocumentingContext) -> bool:
    """Docs drift detection + unwind back to `validating`.

    User-content drift: a human edited the issue title/body while the
    final-docs hop was in flight. The reviewer approved the OLD
    requirements, so the docs pass would be running against a body the
    reviewer never saw. Reset `review_round=0`, post the notice, refresh the
    baseline hash, reconcile the worktree, and relabel to `validating` so the
    reviewer re-evaluates the updated body on the next tick. Do NOT spawn the
    docs agent: the prior approval is gone and a docs commit on top would just
    need to be re-reviewed alongside any impl change -- and because no agent
    runs, no feedback watermark moves either.

    Returns True when the drift path fully handled this tick (the silent
    fast-path, a reconcile park, or the relabel to `validating`); False
    when there is no drift and the normal docs flow should continue.
    """
    new_hash = _engine_drift._detect_user_content_change(
        ctx.gh, ctx.issue, ctx.state,
    )
    fresh_drift = new_hash is not None
    pending_unwind = bool(ctx.state.get(_state._UNWIND_PENDING))
    if pending_unwind and not fresh_drift and _waits_on_a_reply(ctx):
        return True
    if not (fresh_drift or pending_unwind):
        return False

    if fresh_drift:
        _announce_documenting_drift(ctx, new_hash)
    _begin_documenting_drift_unwind(ctx)
    return _unwinds_the_worktree(ctx)


def _waits_on_a_reply(ctx: _models._DocumentingContext) -> bool:
    """Whether a half-finished unwind has heard nothing worth retrying for.

    A prior tick's unwind couldn't finish -- the worktree reconcile failed and
    parked -- and nothing fresh has happened: stay silent so the parked state
    survives operator inspection without re-posting the same park comment
    every tick. Only a trusted reply is the "retry the unwind" signal; with
    `ALLOWED_ISSUE_AUTHORS` set an outsider comment must not fall through to
    the reconcile-retry.

    The boundary that silence is kept behind is the unwind's OWN rather than
    the delivery cursor (`parks._asked_since`): this road delivers nobody's
    words to anybody, so the comment that moved the requirements reads as
    unanswered for as long as it is unread, and a gate measuring against the
    cursor would find it every poll and retry the reconcile every poll.
    """
    if not ctx.state.get(_state._AWAITING_HUMAN):
        return False
    return not filter_trusted(
        ctx.gh.comments_after(ctx.issue, _parks._asked_since(ctx.state)),
    )


def _unwinds_the_worktree(ctx: _models._DocumentingContext) -> bool:
    """Put the checkout back on the PR head and relabel, or hold for a human.

    Always True: both roads out of here finish the tick. The park a git step
    that cannot be proved takes holds the delivery cursor back inside its own
    write (`parks._holds_the_delivery_cursor`), because nothing here delivered
    anything to anybody.
    """
    wt = _worktree_paths._worktree_path(ctx.spec, ctx.issue.number)
    if wt.exists() and not _drift_reset._reset_documenting_drift_worktree(ctx, wt):
        return True
    # Reconcile succeeded (or the worktree didn't exist): the drift unwind is
    # complete, clear the sentinel and the boundary its silence was kept
    # behind, and relabel.
    ctx.state.set(_state._UNWIND_PENDING, False)
    ctx.state.set(_state._UNWIND_ASKED_AT, None)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
    return True
