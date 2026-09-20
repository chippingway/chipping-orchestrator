# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What this stage has already looked at, and how far it may say so.

Two writers move `pr_last_comment_id` and neither may cross a comment nobody
has read. The bump carries the mark over what a tick just wrote: a park posts
an issue comment, so without moving past it the next tick reads the
orchestrator's own HITL message as fresh human feedback and routes the issue
to `fixing` against it. The seed decides what a first tick is allowed to
forget: an issue that reached `in_review` before the validating handoff seeded
watermarks -- or by a manual relabel -- has none at all, and scanning from
`None` would treat the whole history, pickup greeting included, as feedback.

What both refuse is a tip. The two IssueComment surfaces share an id space
(`surfaces.py`), so a human PR comment that landed while an agent was out is
numbered below the notice posted after it: a mark carried to the newest
comment takes that PR comment with it, and no later poll can go back for it.
So each walks forward from where it is and stops at the first comment
`_nobody_is_owed` cannot vouch for -- ours by the id ledger or the hidden
marker, quoted into this tick's own prompt, already recorded on the issue
thread's delivery cursor, or a control the run-limit hold has answered.

Both are deliberately narrow. The bump only moves the issue-side watermark,
because the inline-review and review-summary surfaces are consumed by the
`fixing` handler rather than here, and moving them would hide feedback this
stage never read. The seed persists 0 on those two rather than leaving them
unset, because the orchestrator posts on neither, so there is no leading run
of ours to walk and nothing a seed could cross that is not somebody's review.

`_comment_created_at` sits with them because the debounce that reads it spans
both surfaces: a PullRequestReview stamps `submitted_at` where an IssueComment
stamps `created_at`, and the fakes can leave either unset.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    run_grant_request as _run_grant_request,
)
from orchestrator.workflow.stages.in_review import (
    models as _models,
    state as _state,
    surfaces as _surfaces,
)
from orchestrator.workflow.stages.validating import (
    watermarks as _validating_watermarks,
)

log = logging.getLogger("orchestrator.workflow")

# What a surface with no leading run of our own posts is seeded at: scan it
# from the beginning, and let the scan's own filters decide what is feedback.
_UNREAD_FROM_THE_BEGINNING = 0

# The two surfaces the orchestrator never posts on, so neither carries
# anything a seed could advance past without crossing somebody's review.
_REVIEW_SURFACE_KEYS = (
    "pr_last_review_comment_id",
    "pr_last_review_summary_id",
)


def _comment_created_at(comment) -> datetime | None:
    """Return a tz-aware UTC datetime for a comment, or None if unavailable.

    Real PyGithub `IssueComment.created_at` is always set, but the fakes used
    in tests can leave it None when the test doesn't care about debounce.
    PullRequestReview surfaces its timestamp as `submitted_at` rather than
    `created_at`, so the in_review debounce reads either. Naive datetimes are
    interpreted as UTC (PyGithub returns naive UTC).
    """
    ca = getattr(comment, "created_at", None)
    if ca is None:
        ca = getattr(comment, "submitted_at", None)
    if ca is None:
        return None
    if ca.tzinfo is None:
        return ca.replace(tzinfo=UTC)
    return ca


def _nobody_is_owed(
    comment, on_the_thread: bool, answered: _models._AnsweredIssueSpace,
) -> bool:
    """Whether one comment above the watermark is something no reader is
    still owed: a post this orchestrator can prove it wrote, a reply already
    quoted into a prompt, or a control the run-limit hold has answered.

    Everything else is human input nobody has read, and a walk that crossed
    it would skip it for good.
    """
    if _validating_watermarks._is_orchestrator_comment(comment, answered.ours):
        return True
    if comment.id in answered.delivered:
        return True
    if (
        on_the_thread
        and answered.consumed is not None
        and comment.id <= answered.consumed
    ):
        return True
    return _run_grant_request._is_bare_command(comment)


def _bump_in_review_watermarks(
    ctx: _models._InReviewContext, *, issue_space_new: list | None = None,
) -> None:
    """Carry the issue-side watermark (`pr_last_comment_id`) over what this
    tick wrote, and stop there.

    A park at in_review posts an issue comment, so without moving the
    watermark past it the next tick reads the orchestrator's own HITL message
    as fresh human feedback and routes the issue to `fixing` against it. What
    the move may NOT do is reach the thread's tip. The tick that parks takes
    minutes, and both surfaces share one id space: a human PR comment that
    landed between the scan and the notice is numbered below the notice, so a
    watermark carried to the tip takes that comment with it and no later poll
    can go back for it.

    So the walk starts at the watermark already persisted and advances only
    through comments `_nobody_is_owed` vouches for -- ours, quoted into this
    tick's prompt (`issue_space_new`), or already recorded on the issue
    thread's own delivery cursor -- stopping at the first it cannot. The
    delivery cursor is read as a per-surface fact rather than maxed into this
    field: a PR comment numbered below it was in nobody's prompt.

    A thread this call cannot re-read leaves the watermark exactly where it
    was, because the caller asks this AFTER its notice is posted and BEFORE
    the write that records the park: raising here would strand a notice with
    nothing durable behind it and have the next poll say it again.

    Only the issue-side watermark moves. The inline-review and review-summary
    watermarks belong to the `fixing` handler, which advances them when it
    consumes that feedback; in_review never consumes review-surface comments
    itself (it routes them to `fixing`), so there is nothing to carry past on
    those surfaces.
    """
    watermark = ctx.state.get(_state._PR_LAST_COMMENT_ID)
    if not isinstance(watermark, int):
        watermark = None
    answered = _models._AnsweredIssueSpace(
        ours=set(_comments._orchestrator_ids(ctx.state)),
        consumed=_surfaces._consumed_issue_thread_id(ctx.state),
        delivered={comment.id for comment in issue_space_new or ()},
    )
    try:
        above = _surfaces._issue_space_above(
            ctx.gh, ctx.issue, ctx.pr, watermark,
        )
    except Exception:
        log.exception(
            "issue=#%s could not be re-read to carry `pr_last_comment_id` "
            "over this tick's own post; leaving it where it was",
            ctx.issue.number,
        )
        return
    for comment, on_the_thread in above:
        if not _nobody_is_owed(comment, on_the_thread, answered):
            break
        watermark = comment.id
    if watermark is not None:
        ctx.state.set(_state._PR_LAST_COMMENT_ID, watermark)


def _seed_legacy_in_review_watermarks(
    gh: GitHubClient, issue: Issue, pr, state: PinnedState,
) -> None:
    """First-tick migration: seed every missing in_review watermark as far as
    it can go without crossing input nobody has read, and record the seed in
    pinned state immediately.

    Issues that reached `in_review` before the validating handoff started
    seeding watermarks (or that were manually relabeled, or whose handoff
    failed to snapshot the PR) sit on `_handle_in_review` with
    `pr_last_comment_id`/`pr_last_review_comment_id`/`pr_last_review_summary_id`
    all unset. Scanning from `None` would treat the orchestrator's own pickup /
    PR-opened / approval messages as fresh PR feedback once the debounce
    expires and route the issue to `fixing` over its own historical messages.

    The issue-side seed answers that with the very walk validating's approval
    handoff seeds from, so the two writers of this field cannot disagree: past
    the leading run of the orchestrator's own comments and the issue-thread ids
    `last_action_comment_id` already records as delivered, stopping at the
    first human comment on EITHER surface that nothing vouches for. An issue
    with no pickup anchor to walk from answers 0 -- refusing to advance is the
    safe direction, since a watermark crossing a human comment skips it for
    good while one left low costs a re-read the scan filters.

    The two review surfaces are seeded at 0 outright. The orchestrator never
    posts an inline review comment or a review summary, so there is no leading
    run of ours to walk and nothing on either surface that a seed could
    advance past WITHOUT crossing a human's review -- and a PR carrying review
    feedback no developer was ever shown is exactly the issue this migration
    runs on. 0 is persisted rather than left unset so the surface reads as
    seeded, which is what keeps the scan that follows from being a migration
    decision on every poll.
    """
    seeded = _seed_issue_side_watermark(gh, issue, pr, state)
    for review_surface in _REVIEW_SURFACE_KEYS:
        if state.get(review_surface) is None:
            state.set(review_surface, _UNREAD_FROM_THE_BEGINNING)
            seeded = True
    if seeded:
        gh.write_pinned_state(issue, state)


def _seed_issue_side_watermark(
    gh: GitHubClient, issue: Issue, pr, state: PinnedState,
) -> bool:
    """Seed `pr_last_comment_id` where it is missing, and say whether it was.

    Reuses `_latest_pr_comment_ids` -- validating's own approval-handoff walk
    -- rather than restating its rules here, so a change to what counts as
    read lands on both writers at once. `_ratchet_watermark` turns a walk that
    would not advance into 0.
    """
    if state.get(_state._PR_LAST_COMMENT_ID) is not None:
        return False
    seeded, _ = _validating_watermarks._latest_pr_comment_ids(
        gh, issue, pr, state,
    )
    state.set(
        _state._PR_LAST_COMMENT_ID,
        _validating_watermarks._ratchet_watermark(None, seeded),
    )
    return True
