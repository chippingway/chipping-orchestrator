# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What this stage has already looked at, and how far it may say so.

Two writers move `pr_last_comment_id` and neither may cross a comment nobody
has read. The bump carries the mark over what a tick just wrote: a park posts
an issue comment, so without moving past it the next tick reads the
orchestrator's own HITL message as fresh human feedback and routes the issue
to `fixing` against it. The initialization decides where a mark nothing set
begins: an issue a human relabeled into `in_review`, or one an approval handed
here without the snapshot its seed is read off, carries it unset, and
scanning from `None` would treat the whole history, pickup greeting included,
as feedback.

What both refuse is a tip. The two IssueComment surfaces share an id space
(`surfaces.py`), so a human PR comment that landed while an agent was out is
numbered below the notice posted after it: a mark carried to the newest
comment takes that PR comment with it, and no later poll can go back for it.
So each walks forward -- the bump from the mark already persisted, the
initialization from the beginning -- and stops at the first comment nothing
vouches for: ours by the id ledger or the hidden marker, inside the stretch
of the issue thread a developer prompt was handed (`engine/thread_delivery`),
a control the run-limit hold has answered, or, for the bump, named by the
frozen record this tick's own prompt was built from. The bump asks
`_nobody_is_owed`; the initialization asks the
approval handoff's own walk (`validating/watermarks.py`), which applies the
same rules with no record of this tick's. The record is asked rather than the
read behind it, because a bounded excerpt delivers less than it read and the
context it cut is precisely what the walk has to stop below. And neither
crosses anything numbered above what its own two reads prove complete: the
thread is read first, so a reply landing there before the pull request is
read is in neither read, beneath whatever the second one carried.

Both are deliberately narrow. The bump only moves the issue-side watermark,
because the inline-review and review-summary surfaces are consumed by the
`fixing` handler rather than here, and moving them would hide feedback this
stage never read. The initialization persists 0 on those two rather than
leaving them unset, because the orchestrator posts on neither and no record
of ours says a developer read either, so there is no leading run of ours to
walk and nothing it could cross that is not somebody's review.

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
    prompt_delivery as _delivery,
    run_grant_request as _run_grant_request,
    thread_delivery as _thread_delivery,
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

# What a surface with no leading run of our own posts is initialized at: scan
# it from the beginning, and let the scan's own filters decide what is
# feedback.
_UNREAD_FROM_THE_BEGINNING = 0

# The two surfaces the orchestrator never posts on, so neither carries
# anything an initialization could advance past without crossing somebody's
# review.
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
    it would skip it for good. So is anything beneath a comment numbered
    above what the walk's reads prove complete (`answered.known_through`): a
    comment landing on the thread read first, after that read, sits below it
    unseen, so it is never crossed whatever it is.
    """
    if answered.known_through is None or comment.id > answered.known_through:
        return False
    if _validating_watermarks._is_orchestrator_comment(comment, answered.ours):
        return True
    if comment.id in answered.delivered:
        return True
    if on_the_thread and answered.consumed.covers(comment.id):
        return True
    return _run_grant_request._is_bare_command(comment)


def _delivered_here(
    delivered: _delivery.PromptDeliverySnapshot | None,
) -> set:
    """The ids one frozen prompt record leaves no reader owed.

    Its DELIVERED half is what a developer read. Its FILTERED half is what no
    reader will ever be handed -- an untrusted author, a body carrying our
    marker that the id ledger cannot vouch for -- so a walk crossing one skips
    nothing, while leaving it unaccounted for would stop that walk on a
    comment nobody is ever going to answer.

    What the excerpt bound OMITTED is in neither half, which is exactly what
    holds the walk below it: that context reached no agent, so the scan that
    owns the surface still has to deliver it.
    """
    if delivered is None:
        return set()
    return {
        entry.id for entry in delivered.entries
        if entry.is_delivered or entry.is_filtered
    }


def _bump_in_review_watermarks(
    ctx: _models._InReviewContext,
    *,
    delivered: _delivery.PromptDeliverySnapshot | None = None,
) -> bool:
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
    through comments `_nobody_is_owed` vouches for -- ours, named by the
    frozen record a prompt this tick delivered was built from (`delivered`),
    or inside the stretch of the issue thread a developer prompt was handed
    -- stopping at the first it cannot. That stretch is read as a per-surface
    fact rather than maxed into this field: a PR comment numbered below it was
    in nobody's prompt. Nor does it cross anything above what its two reads
    prove complete: the issue thread is read first, and a comment landing
    there after that read sits unseen below anything newer on the pull
    request.

    `delivered` is the record itself rather than a list of comments, because
    the record is the only thing that knows which of them REACHED the agent: a
    bounded excerpt drops its head, and a walk handed the whole read would
    cross the very context the bound cut. A tick with no delivery -- a run
    nobody read the prompt through -- hands over None and the walk crosses
    only our own posts.

    A thread this call cannot re-read leaves the watermark exactly where it
    was, because the caller asks this AFTER its notice is posted and BEFORE
    the write that records the park: raising here would strand a notice with
    nothing durable behind it and have the next poll say it again. It answers
    False there, and True where the walk read both surfaces, so a caller with
    nothing posted yet may hold its tick rather than write past a carry that
    never ran.

    Only the issue-side watermark moves. The inline-review and review-summary
    watermarks belong to the `fixing` handler, which advances them when it
    consumes that feedback; in_review never consumes review-surface comments
    itself (it routes them to `fixing`), so there is nothing to carry past on
    those surfaces.
    """
    watermark = ctx.state.get(_state._PR_LAST_COMMENT_ID)
    if not isinstance(watermark, int):
        watermark = None
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
        return False
    answered = _models._AnsweredIssueSpace(
        ours=set(_comments._orchestrator_ids(ctx.state)),
        consumed=_thread_delivery.DeliveredThread.read(ctx.state),
        delivered=_delivered_here(delivered),
    ).read_through(above, watermark)
    for comment, on_the_thread in above:
        if not _nobody_is_owed(comment, on_the_thread, answered):
            break
        watermark = comment.id
    if watermark is not None:
        ctx.state.set(_state._PR_LAST_COMMENT_ID, watermark)
    return True


def _initialize_unset_watermarks(
    gh: GitHubClient, issue: Issue, pr, state: PinnedState,
) -> None:
    """Initialize every in_review watermark this issue carries unset, and
    record them in pinned state before the scan reads past them.

    Two current roads reach the stage without them: a human relabeling an
    issue into `in_review` from a stage that never seeds them, and an
    approval whose snapshot of the pull request or its threads would not
    answer, which hands the issue on with each watermark exactly as
    persisted, an unset one included (`validating/handoff.py`). Scanning the
    issue side from `None` would treat the orchestrator's own pickup /
    PR-opened / approval messages as fresh PR feedback once the debounce
    expires and route the issue to `fixing` over its own posts.

    The issue side is initialized from recorded delivery alone, by the very
    walk validating's approval handoff seeds from, so the two writers of this
    field cannot disagree: past the orchestrator's own comments, the
    issue-thread comments the delivered stretch covers (`thread_delivery`) --
    never one a bounded prompt left out, nor anything at all where no floor
    is recorded -- and bare run-grant controls, stopping at the first comment
    on EITHER surface that nothing vouches for. A walk that crosses nothing
    answers 0 -- a scan from the beginning -- since a watermark crossing a
    human comment skips it for good while one left low costs a re-read the
    scan filters.

    The two review surfaces are initialized at 0 outright. The orchestrator
    never posts an inline review comment or a review summary, and an unset
    mark there records no developer reading anything on it, so there is
    nothing a walk could advance past WITHOUT crossing a human's review --
    and a PR carrying review feedback no developer was ever shown routes it
    to `fixing`. 0 is persisted rather than left unset so the surface reads
    as initialized, which is what keeps the scan that follows from being an
    initialization decision on every poll.

    A watermark already set is left exactly as it is, whatever its value. A
    thread that will not answer raises out of here before anything is staged
    or written, which holds the tick: no scan, drift check, or ready ping runs
    over a watermark nobody could initialize, and the next tick asks again.
    """
    initialized = _initialize_issue_side(gh, issue, pr, state)
    for review_surface in _REVIEW_SURFACE_KEYS:
        if state.get(review_surface) is None:
            state.set(review_surface, _UNREAD_FROM_THE_BEGINNING)
            initialized = True
    if initialized:
        gh.write_pinned_state(issue, state)


def _initialize_issue_side(
    gh: GitHubClient, issue: Issue, pr, state: PinnedState,
) -> bool:
    """Initialize `pr_last_comment_id` where it is unset, and say whether it was.

    Reuses `_latest_pr_comment_ids` -- validating's own approval-handoff walk
    -- rather than restating its rules here, so a change to what counts as
    delivered lands on both writers at once. `_ratchet_watermark` turns a
    walk that crossed nothing into 0.
    """
    if state.get(_state._PR_LAST_COMMENT_ID) is not None:
        return False
    walked, _ = _validating_watermarks._latest_pr_comment_ids(
        gh, issue, pr, state,
    )
    state.set(
        _state._PR_LAST_COMMENT_ID,
        _validating_watermarks._ratchet_watermark(None, walked),
    )
    return True
