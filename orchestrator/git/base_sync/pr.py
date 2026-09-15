# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The refresh-time route a PR-having worktree takes back to merge-ready.

This owner holds no git and no GitHub write of its own; what it owns is the
order the four owners below it are called in, and that order is the contract.
Every gate in ``eligibility`` is asked before ``startup`` is allowed to move
HEAD, because each of them is a reason the worktree must be left exactly as
the last tick published it. Crash recovery is settled before a new rebase is
begun, so an anchor an earlier tick pinned is never rewritten out from under
the comparison that would have resolved it. Only then does ``startup`` anchor
and run the rebase, and only a rebase that returns a known pre-rebase SHA
reaches ``publication`` -- the failure paths have already routed themselves to
``conflicts`` or to a park. The legacy keyword signature is bound here too,
because the refresh still passes the pre-context argument list this route
derives its context from.
"""
from __future__ import annotations

import inspect
from typing import Any

from github.PullRequest import PullRequest

from orchestrator.git.base_sync import (
    eligibility,
    publication,
    recovery_holds,
    startup,
)
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRequest,
)
from orchestrator.git.base_sync.state import _PENDING_PUSH_SHA

_SYNC_PR_SIGNATURE = inspect.Signature((
    inspect.Parameter("gh", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("spec", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("issue", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("state", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("worktree", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("pr_number", inspect.Parameter.POSITIONAL_OR_KEYWORD),
    inspect.Parameter("behind", inspect.Parameter.POSITIONAL_OR_KEYWORD),
))


def _publish_auto_rebase_from_pr(
    context: _AutoRebaseContext, pr: PullRequest, consumed_comment_id: int | None,
) -> None:
    """Complete the recovery / rebase / publish phase for an opened PR."""
    recovery = eligibility._auto_rebase_recovery_decision(
        context, consumed_comment_id,
    )
    if not recovery.should_continue:
        return
    if not eligibility._normal_auto_rebase_can_start(context):
        return

    before_sha = startup._start_auto_rebase(
        context, pr, recovery.consumed_comment_id,
    )
    if before_sha is None:
        return

    publication._publish_auto_rebase(context, before_sha)


def _sync_pr_worktree_context(context: _AutoRebaseContext) -> None:
    """Run one refresh-time PR synchronization from normalized inputs."""
    if not eligibility._auto_rebase_label_is_eligible(context):
        return

    retry = eligibility._auto_rebase_retry_decision(context)
    if not retry.should_continue:
        _answers_an_anchor_under_a_park(context)
        return
    pr = eligibility._open_auto_rebase_pr(context)
    if pr is None:
        return

    _publish_auto_rebase_from_pr(context, pr, retry.consumed_comment_id)


def _answers_an_anchor_under_a_park(context: _AutoRebaseContext) -> None:
    """Answer an anchor a park stands over, and start nothing else.

    The pull request is asked first, whichever park stands. One that merged or
    closed ends the attempt's whole handoff there, and a park this refresh
    left is owed that as much as a stage's: the anchor holds back the handler
    that finalizes the issue, and a park waiting on a reply nobody needs to
    send would hold it for good.

    Past a pull request that reads open, only a stage's park is owed the
    recovery, with no reply spent. Whatever the recovery hands back, no rebase
    of this tick's follows it: the park is still a stage's, and rebasing past
    one is what the retry decision exists to prevent. A park this refresh left
    goes on waiting for its reply.
    """
    if not context.pending_pre_rebase_sha:
        return
    if eligibility._open_auto_rebase_pr(context) is None:
        return
    if eligibility._answers_only_the_anchor(context):
        eligibility._auto_rebase_recovery_decision(context, None)


def _sync_unreadable_pr_worktree(request: _AutoRebaseRequest) -> None:
    """Answer an anchor over a checkout whose lag against base cannot be read.

    Asked on the same gates, in the same order, as the ordinary PR sync -- an
    ineligible label is still the recovery's own ineligible road, a pull
    request that ended or would not read is still answered as it is there
    whichever park stands, a park some stage left is still answered past with
    the recovery alone, and a park this refresh left is still waiting on a
    reply. Only the step past them differs. There is no lag to route on and no head worth comparing, so
    nothing is fetched and nothing is classified: the recovery takes its
    fail-closed abort directly.
    """
    context = request.to_context(_PENDING_PUSH_SHA)
    if not eligibility._auto_rebase_label_is_eligible(context):
        return
    retry = eligibility._auto_rebase_retry_decision(context)
    if eligibility._open_auto_rebase_pr(context) is None:
        return
    if retry.should_continue or eligibility._answers_only_the_anchor(context):
        recovery_holds._answers_an_unreadable_checkout(
            context, retry.consumed_comment_id,
        )


def _sync_pr_worktree_to_base(*args: Any, **kwargs: Any) -> None:
    """Bring a behind-base PR-having issue back to merge-ready.

    On a clean rebase: rebase the worktree onto `origin/<base>`, push
    with `--force-with-lease` pinned to the pre-rebase SHA (so a
    concurrent foreign update on the remote PR branch rejects the
    push instead of being clobbered), reset `review_round` to 0, post
    an informational PR notice, and relabel to `validating` so the
    reviewer re-runs against the rewritten head. Docs do not run on
    this exit -- the single docs pass runs after the next reviewer
    approval via the final-docs handoff to `documenting` in
    `_handle_validating`. This is the only safe pattern for PR-having
    worktrees, since a local-only rebase without a push would diverge
    local HEAD from `pr.head.sha` and break every downstream gate
    that compares the two.

    Only when the rebase actually leaves conflicted files do we
    relabel to `resolving_conflict`: the handler then drives the dev
    agent to resolve the conflict, pushes, and bounces back to
    `validating`. This reserves the `resolving_conflict` label for
    real rebase conflicts (or an operator manual application) and
    keeps the merely-behind-base case off it -- the label no longer
    flips on a clean sibling-PR merge that the orchestrator can
    auto-rebase. `_handle_in_review` is also permanently manual-
    merge-only and just parks awaiting human attention on an
    unmergeable PR.

    Skipped (label stays put, no PR notice, no push) when:

    * The label is not one the refresh drives (only `validating` /
      `documenting` / `in_review` / `fixing`); `resolving_conflict`
      itself is also skipped because the handler runs this tick anyway
      and will do the rebase regardless.

    * `awaiting_human=True`. The orchestrator already parked the issue
      and an attempted auto-rebase here would either re-open work that
      the human is meant to resolve or undermine the
      `MAX_REVIEW_ROUNDS` / `MAX_CONFLICT_ROUNDS` caps that exist
      precisely to require human intervention after repeated failures.

    * The PR is no longer open. A merged PR advances `origin/<base>`,
      so the still-validating / still-in_review / still-fixing
      worktree pointed at the now-stale branch is naturally behind
      base; without this gate the refresh would push, post an
      "auto-rebased" notice, and relabel to `validating` on a PR the
      next handler call would finalize to `done`. Same for closed-
      without-merge if base advanced concurrently (handler would
      finalize to `rejected`). Leave terminal PR state to the
      existing stage logic. A `gh.get_pr` failure is treated as
      "leave it alone" -- the handler can retry on the next tick from
      a stable label rather than racing a half-known PR state from
      refresh.

    The watermark bump in `_handle_in_review`'s analogous unmergeable
    detour is deliberately NOT replicated here. That bump is safe
    in_review-side because `_handle_in_review` has already scanned new
    comments before the relabel (anything past the watermark has been
    consumed by the fix-loop or filtered as orchestrator-authored).
    The refresh-time flow runs BEFORE any handler scans comments, so
    `latest_comment_id` may include unread human "do not merge" /
    fix-request comments; advancing the watermark here would silently
    mark them consumed and later validation / merge would skip them.
    The orchestrator's own PR notice we just posted is filtered out
    via `orchestrator_comment_ids` on the next `_handle_in_review`
    scan, so leaving the watermark alone does not cause the
    orchestrator to "see" its own message as fresh feedback. The
    `pending_fix_*` bookmarks recorded by an `in_review` -> `fixing`
    route are similarly left untouched: the next handler that resumes
    that route still finds them, and a stale bookmark on a now-
    `validating` issue is harmless (the reviewer pass clears it
    naturally when it next bounces to `fixing`).

    Dirty worktrees abort the push: a pre-existing uncommitted edit
    would otherwise be force-pushed alongside the rebase result, and
    the validating reviewer would then vote on a tree that does NOT
    match the PR head. Mirrors `_handle_resolving_conflict`'s refuse-
    to-publish-an-incomplete-branch rule. A push failure (the lease
    rejection most commonly surfaces a diverged or crash-recovery
    branch) leaves the label alone too; the next tick can retry once
    the underlying divergence is reconciled.
    """
    bound_fields = _SYNC_PR_SIGNATURE.bind(*args, **kwargs)
    request = _AutoRebaseRequest(
        *bound_fields.arguments.values(),
    )
    _sync_pr_worktree_context(
        request.to_context(_PENDING_PUSH_SHA),
    )


_sync_pr_worktree_to_base.__signature__ = _SYNC_PR_SIGNATURE
