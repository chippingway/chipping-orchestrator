# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The last answer a tick can reach: whether to tell a human the PR is ready.

The orchestrator never merges from here and never routes a conflict from here.
An unmergeable PR -- branch protection, a real conflict, a base that moved --
parks awaiting a human, because every automatic answer to it would be a guess
about what the human wants merged.

A mergeable PR earns one ping per head SHA, and each of the four gates in
front of that ping protects the same claim. The ping says "ready for
review/merge", so it may only fire for a head this orchestrator reviewed and
documented (the final-docs marker) or that GitHub itself carries an APPROVED
review for, and never over a standing CHANGES_REQUESTED veto. `ready_ping_sha`
keys the de-duplication on the head that was pinged, so a new commit re-pings
and a repeated tick on the same head stays silent. The last gate is the
subject the approval covered, read again at the ping itself: the requests the
gate makes before it are time in which another road can settle a later report,
a human can edit that report or the issue, or a push can move the head the
ping names -- and another road can point the issue at another pull request
than the one the ping would name. The ping's own writes are held to the
records that subject was read over, the pointer among them, as guarded commits
over a fresh reading, and its publication is `ready_ping`'s: armed before it
is posted, found again on the thread rather than posted twice, and recorded
behind the post. The park the gate takes is held to the report records and
the pointer too, since it writes the state in hand.

Both writes this stage makes to a thread are bounded by the same fact: the
feedback scan that decided this tick ran several GitHub round-trips ago, and a
human may have written since. So the unmergeable park is a BOUNDED one -- it
records the thread read only as far as the ledger can vouch for, never at the
id of the notice it just posted, which would sit above their reply and take it
with it. And the ping, which is no park at all, ratchets nothing: it is
filtered by the id ledger and its hidden marker on the next read, so no mark
has to move for it, and a mark that did move would be moving over exactly that
unread reply.
"""
from __future__ import annotations

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.in_review import (
    models as _models,
    ready_ping as _ready_ping,
    watermarks as _watermarks,
)
from orchestrator.workflow.stages.validating import (
    review_comment as _review_comment,
    review_coverage as _review_coverage,
)


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
        # The mergeability request is time another road can settle a later
        # report in, or point the issue at another pull request, and the park
        # below writes the state in hand whole: over a comment that moved, it
        # would put the replaced report or pointer back.
        if not _review_comment._records_in_hand(
            ctx.gh, ctx.issue, ctx.state, "park its pull request as unmergeable",
        ):
            return
        # Bounded, because this refusal is not decided between two adjacent
        # steps: the feedback scan that let the tick get here ran several
        # GitHub round-trips ago, and a reply written since is numbered below
        # the notice this park posts. Stamped at that notice id, the reply
        # would be under BOTH cursors the next scan reads -- the delivery
        # cursor this park set and the issue-side watermark carried over it --
        # and no later poll could go back for it.
        _guards._park_awaiting_human(
            ctx.gh, ctx.issue, ctx.state,
            f"{config.HITL_MENTIONS} PR #{pr_number} is not mergeable "
            "(branch protection, conflicts, or out-of-date base); "
            "manual merge needed.",
            reason="unmergeable",
            bounded=True,
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
    # Deliberately NOT calling `_bump_in_review_watermarks` here. The ping is
    # not a park: it leaves `awaiting_human` false and owes the thread no
    # "everything below here is read" claim. It IS an issue comment, and its
    # settlement records it in `orchestrator_comment_ids`, so the next tick's
    # id-set filter drops it without any watermark having to move -- as the
    # hidden marker does for one whose record never landed. Moving one would
    # only risk crossing a human comment that landed between the earlier
    # feedback scan and this point -- the next tick's `comments_after` would
    # skip it and the dev would never see the feedback.
    if ctx.state.get("ready_ping_sha") != head_sha:
        _pings_ready(ctx, head_sha)


def _pings_ready(ctx: _models._InReviewContext, head_sha: str) -> None:
    """Ping a human that `head_sha` is ready, while the approval still covers it.

    A ping an earlier tick armed over the head is looked for on the thread
    first, and settled where it landed (`ready_ping.recovers`): that is a
    record of what was already said, and posts nothing. Anything else is a
    new post, asked of the approval again first: unread or refused, nobody is
    pinged and nothing is written, and the next tick's hand-back, drift check,
    or ping over the new head answers it.
    """
    if _ready_ping.recovers(ctx, head_sha) or not _still_ready(ctx, head_sha):
        return
    _ready_ping.publishes(ctx, head_sha)


def _still_ready(ctx: _models._InReviewContext, head_sha: str) -> bool:
    """Whether everything the ping claims still stands, read at the ping itself.

    The hand-back ahead of the feedback scan asked the approval too, but the
    mergeability and review requests since then are round-trips in which
    another road can settle a later report or point the issue at another pull
    request, a human can edit or delete the report or edit the issue, or a
    push can move the pull request off the head those requests approved -- and
    the ping is the one claim here that what stands was reviewed. So the
    approval has to cover the evidence it was proved over, where it was
    proved over any -- its records and its artifact -- the report as it reads
    at its location, the requirements over the issue read afresh, and
    `head_sha` over the pull request read afresh
    (`review_coverage._approval_holds`). The pinned comment is held to the
    report, evidence, approval, and pull-request records in hand by the
    ping's own guarded writes, each over a fresh reading
    (`ready_ping._DECIDED_ON`): the evidence and report reads are requests long
    enough for another road to record a later verification revision, and a
    write over it would put the older revision floor back.
    """
    return bool(_review_coverage._approval_holds(ctx.gh, ctx.issue, ctx.state, head_sha))
