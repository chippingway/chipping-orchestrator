# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The last answer a tick can reach: whether to tell a human the PR is ready.

The orchestrator never merges from here and never routes a conflict from here.
An unmergeable PR -- branch protection, a real conflict, a base that moved --
parks awaiting a human, because every automatic answer to it would be a guess
about what the human wants merged.

A mergeable PR earns one ping per head SHA, and each of the three gates in
front of that ping protects the same claim. The ping says "ready for
review/merge", so it may only fire for a head this orchestrator reviewed and
documented (the final-docs marker) or that GitHub itself carries an APPROVED
review for, and never over a standing CHANGES_REQUESTED veto. `ready_ping_sha`
keys the de-duplication on the head that was pinged, so a new commit re-pings
and a repeated tick on the same head stays silent.

The ping deliberately does not ratchet the watermark, unlike every park here.
The ratchet reads `latest_comment_id`, which can already include a human
comment that landed between the feedback scan above and this point; moving the
watermark past it would make the next tick skip feedback nobody read. The ping
itself is filtered by the id ledger instead, which needs no watermark to move.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments, guards as _guards
from orchestrator.workflow.stages.in_review import models as _models, watermarks as _watermarks


def _final_docs_handoff_completed_for_head(
    state: PinnedState, head_sha: str,
) -> bool:
    """True when the reviewer-approved final-docs handoff covers `head_sha`."""
    if not head_sha:
        return False
    return (
        state.get("docs_checked_sha") == head_sha
        and state.get("docs_verdict") in ("updated", "no_change")
    )


def _head_is_approved(ctx: _models._InReviewContext, head_sha: str) -> bool:
    """True when `head_sha` earned the reviewer-approved final-docs handoff or
    carries a real GitHub APPROVED review.

    The final-docs pass records the exact head it checked after reviewer
    approval; if a later push changes the PR head, the docs marker no longer
    matches and the issue must bounce back through validating/documenting before
    it can ping again. A real GitHub APPROVED review on the current head is the
    fallback for manually-driven review flows -- probed only when the final-docs
    marker did not already qualify the head, to avoid a redundant API call.
    """
    if _final_docs_handoff_completed_for_head(ctx.state, head_sha):
        return True
    return ctx.gh.pr_is_approved(ctx.pr, head_sha=head_sha)


def _handle_mergeable_gate(ctx: _models._InReviewContext) -> None:
    """Manual-merge-only mergeability gate. An unmergeable PR parks awaiting
    human regardless of approval state -- the orchestrator never routes from
    here to `resolving_conflict` and never calls `gh.merge_pr`. A mergeable PR
    earns a one-shot HITL ping per head SHA when either the agent-approved
    final-docs handoff covers that head OR GitHub carries a real APPROVED
    review on that head, and no standing CHANGES_REQUESTED veto exists.
    """
    pr = ctx.pr
    pr_number = ctx.pr_number
    mergeable = ctx.gh.pr_is_mergeable(pr)
    if mergeable is None:
        return  # GitHub still computing; try next tick
    if not mergeable:
        _guards._park_awaiting_human(
            ctx.gh, ctx.issue, ctx.state,
            f"{config.HITL_MENTIONS} PR #{pr_number} is not mergeable "
            "(branch protection, conflicts, or out-of-date base); "
            "manual merge needed.",
            reason="unmergeable",
        )
        ctx.state.set("park_reason", "unmergeable")
        _watermarks._bump_in_review_watermarks(ctx)
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    # mergeable: humans drive the merge. The ping advertises the PR as "ready
    # for review/merge", so it must only fire for a head the orchestrator has
    # reviewer-approved and documented (or one a human/bot formally approved in
    # GitHub) AND carrying no standing human veto; otherwise we would invite a
    # manual merge over a stale or rejected commit.
    head_sha = pr.head.sha
    if ctx.gh.pr_has_changes_requested(pr, head_sha=head_sha):
        return
    if not _head_is_approved(ctx, head_sha):
        return
    # Ping HITL handles once per head SHA so the human knows the PR is ready.
    # De-duplication is keyed on `ready_ping_sha` (the head we pinged for); a
    # new commit pushed onto the branch shifts pr.head.sha and re-pings, while
    # repeated ticks on the same head stay silent. Deliberately do NOT set
    # `awaiting_human` -- the handler must still react to PR comments / external
    # merge / a later unmergeable transition.
    #
    # Deliberately NOT calling `_bump_in_review_watermarks` here: that helper
    # reads `gh.latest_comment_id(issue)`, which could include a human
    # issue/PR-conversation comment that landed between the earlier comment scan
    # and this point. Bumping the watermark past an unobserved human comment
    # would silently swallow it -- the next tick's `comments_after` would skip
    # it and the dev would never see the feedback. The ping is recorded in
    # `orchestrator_comment_ids` by `_post_issue_comment`, so the next tick's
    # id-set filter excludes it without needing the watermark to move; a
    # concurrent human comment naturally surfaces below the unchanged watermark.
    if ctx.state.get("ready_ping_sha") != head_sha:
        _comments._post_issue_comment(
            ctx.gh, ctx.issue, ctx.state,
            f":bell: {config.HITL_MENTIONS} PR #{pr_number} is ready "
            "for review/merge.",
        )
        ctx.state.set("ready_ping_sha", head_sha)
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
