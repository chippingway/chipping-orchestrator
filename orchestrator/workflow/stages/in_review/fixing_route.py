# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What in_review hands the fixing stage, and why none of it is a watermark.

The batch that triggered the route is written down as bookmarks -- per surface
a max id AND the full id list -- because the fixing handler re-reads those same
comments to build its dev-resume prompt. Advancing the watermarks here instead
would consume the feedback that caused the route and leave the dev with
nothing to answer. The id lists exist because the max id alone stops being
enough once the in_review watermarks do move past the batch: a later rescan
can no longer reach the batch's lower members, and
`_reconstruct_pending_fix_batch` prefers the lists for exactly that reason.

The relabel is deliberately not debounced. The dev is no longer spawned from
this stage at all, so the wait belongs to the fixing handler's own spawn, and
flipping immediately is what surfaces the transition to the operator.

The hash refresh is the subtle half. `user_content_hash` covers title, body,
and every human issue-thread comment, so any issue-thread comment in this
batch has already moved it; leaving the stale hash behind would have the drift
route resume the dev and bounce to `validating` the moment a human relabels
back to `in_review`, undoing the route this owner just took.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    content_hash as _content_hash,
    usage as _usage,
)
from orchestrator.workflow.stages.in_review import models as _models
from orchestrator.workflow.state import WorkflowLabel


def _record_pending_fix_bookmarks(
    state: PinnedState,
    issue_space_new: list,
    review_space_new: list,
    review_summary_new: list,
) -> None:
    """Bookmark the fresh-feedback batch for the fixing handler: per surface,
    the max id (the existing pinned-state contract and the conservative
    reconstruction bound for issues parked before the id lists existed) plus the
    full id list, so a later fixing tick reconstructs the EXACT triggering batch
    even after the in_review watermarks advance past it -- the max id alone
    loses the batch's lower members once a rescan can no longer reach them.
    `_reconstruct_pending_fix_batch` prefers the id lists. Each list is already
    sorted ascending by id (sorted at scan time).

    These are bookmarks, not watermarks: they are deliberately NOT bumped past
    the batch, because the fixing handler re-reads these same comments to build
    its dev-resume prompt and consuming them now would lose the triggering
    feedback.
    """
    for max_key, ids_key, batch in (
        ("pending_fix_issue_max_id", "pending_fix_issue_ids", issue_space_new),
        ("pending_fix_review_max_id", "pending_fix_review_ids", review_space_new),
        (
            "pending_fix_review_summary_max_id",
            "pending_fix_review_summary_ids",
            review_summary_new,
        ),
    ):
        if batch:
            state.set(max_key, max(feedback.id for feedback in batch))
            state.set(ids_key, [feedback.id for feedback in batch])


def _route_feedback_to_fixing(
    ctx: _models._InReviewContext,
    issue_space_new: list,
    review_space_new: list,
    review_summary_new: list,
) -> None:
    """Hand fresh PR feedback off to the `fixing` stage instead of silently
    waiting through the debounce window or spawning the dev agent here.
    Recording the per-namespace ids in pinned state (see
    `_record_pending_fix_bookmarks`) gives the fixing handler a bookmark of what
    triggered the route so it can resume the dev session, push a fix, and flip
    back to `validating` -- all without `_handle_in_review` keeping the
    comment-debounce / dev-resume machinery in its own body.

    Deliberately NOT honoring the debounce window before the flip: with the
    route to `fixing`, the dev is no longer spawned from this handler at all --
    the fixing stage owns debouncing before its own spawn, so flipping
    immediately is the right contract (the `fixing` label surfaces the
    transition to the operator straight away, and any concurrent additional
    comments are seen by the fixing handler on its next tick).

    Refresh `user_content_hash` so the user-content drift detection does NOT
    fire on the next tick for the same comment changes just consumed via the
    fixing route: the hash covers title + body + human issue-thread comments, so
    any issue-thread comment in `issue_space_new` shifts it; leaving the old
    hash would have the drift path resume the dev and bounce to `validating` the
    moment a human relabels the issue back to `in_review`, undoing the route.
    """
    state = ctx.state
    state.set("pending_fix_at", _usage._now_iso())
    _record_pending_fix_bookmarks(
        state, issue_space_new, review_space_new, review_summary_new,
    )
    state.set(
        "user_content_hash",
        _content_hash._compute_user_content_hash(ctx.issue, _comments._orchestrator_ids(state)),
    )
    # If we were parked awaiting human, the comment that triggered this route is
    # the human signal -- clear the park flags so the fixing handler is not
    # greeted with stale awaiting_human state.
    state.set("awaiting_human", False)
    state.set("park_reason", None)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.FIXING)
    ctx.gh.write_pinned_state(ctx.issue, state)
