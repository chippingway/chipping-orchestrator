# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether one refresh-time PR rebase may run at all, asked in order.

The questions between a behind-base PR worktree and a rewrite live together
because the order they are asked in is the safety property. A label the
refresh does not drive is rejected first, but not before a recovery anchor an
earlier tick pinned is settled -- the owner that notices an anchor nobody will
act on again is the one that has to clear it. An operator park is honored
next, and a trusted reply that would release it is only *reported* from here:
the park stays on disk until a rebase is actually attempted, so a later gate
that early-returns cannot consume the operator's comment without acting on it.
A PR that is no longer open, or cannot be read at all, belongs to the stage
handler that finalizes it rather than to the refresh. Only then may crash
recovery claim the tick, and only a clean worktree that is genuinely behind
base earns a rebase of its own.
"""
from __future__ import annotations

from github.PullRequest import PullRequest

from orchestrator.git.base_sync import attempts, recovery
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseDecision,
)
from orchestrator.git.base_sync.state import (
    _AUTO_REBASE_PARK_REASONS,
    _AWAITING_HUMAN,
    _PARK_REASON,
    _PR_REFRESH_DETOUR_LABELS,
    log,
)
from orchestrator.git.verification import probes as verification_probes
from orchestrator.github.comments import filter_trusted


def _auto_rebase_label_is_eligible(context: _AutoRebaseContext) -> bool:
    """Clear stale recovery state and reject labels refresh does not drive."""
    if context.label in _PR_REFRESH_DETOUR_LABELS:
        return True
    if context.pending_pre_rebase_sha:
        recovery._recover_pending_auto_base_rebase(
            context.gh,
            context.spec,
            context.issue,
            context.state,
            context.worktree,
            pr_number=context.pr_number,
            label=context.label,
            pending_pre_rebase_sha=str(context.pending_pre_rebase_sha),
            pending_rewrite=attempts._pending_rewrite(context.state),
        )
    log.debug(
        "issue=#%d behind %s/%s by %d but label=%r; not auto-rebasing",
        context.issue.number,
        context.spec.remote_name,
        context.spec.base_branch,
        context.behind,
        context.label,
    )
    return False


def _auto_rebase_retry_decision(
    context: _AutoRebaseContext,
) -> _AutoRebaseDecision:
    """Keep stage-owned parks intact and recognize a trusted retry reply."""
    if not context.state.get(_AWAITING_HUMAN):
        return _AutoRebaseDecision(should_continue=True)

    park_reason = context.state.get(_PARK_REASON)
    if park_reason not in _AUTO_REBASE_PARK_REASONS:
        log.debug(
            "issue=#%d behind %s/%s by %d but awaiting_human=True "
            "with park_reason=%r; leaving park intact rather than "
            "auto-rebasing",
            context.issue.number,
            context.spec.remote_name,
            context.spec.base_branch,
            context.behind,
            park_reason,
        )
        return _AutoRebaseDecision(should_continue=False)

    last_action_id = context.state.get("last_action_comment_id")
    new_comments = filter_trusted(
        context.gh.comments_after(context.issue, last_action_id)
    )
    if not new_comments:
        log.debug(
            "issue=#%d behind %s/%s by %d, parked on %r with no new "
            "human comment; staying parked",
            context.issue.number,
            context.spec.remote_name,
            context.spec.base_branch,
            context.behind,
            park_reason,
        )
        return _AutoRebaseDecision(should_continue=False)

    consumed_comment_id = max(comment.id for comment in new_comments)
    log.info(
        "issue=#%d parked on %r had a new human comment; will clear "
        "the park if a retry is actually attempted this tick (gates "
        "that early-return preserve the park on disk so the "
        "operator's reply is not silently consumed)",
        context.issue.number,
        park_reason,
    )
    return _AutoRebaseDecision(
        should_continue=True,
        consumed_comment_id=consumed_comment_id,
    )


def _open_auto_rebase_pr(
    context: _AutoRebaseContext,
) -> PullRequest | None:
    """Return the open PR or leave terminal and unreadable PRs untouched."""
    try:
        pr = context.gh.get_pr(context.pr_number)
    except Exception:  # noqa: BLE001 - an unreadable PR is retried on the next tick
        log.debug(
            "issue=#%d could not fetch PR #%d for refresh rebase; "
            "leaving label alone, handler will retry next tick",
            context.issue.number,
            context.pr_number,
        )
        return None

    pr_status = context.gh.pr_state(pr)
    if pr_status == "open":
        return pr
    if context.pending_pre_rebase_sha:
        attempts._clears_the_attempt(context.state)
        context.gh.write_pinned_state(context.issue, context.state)
        log.info(
            "issue=#%d PR #%d is %s and an attempt was still in flight for "
            "it; ending the whole record it left",
            context.issue.number,
            context.pr_number,
            pr_status,
        )
    log.debug(
        "issue=#%d PR #%d is %s; not auto-rebasing (handler will finalize)",
        context.issue.number,
        context.pr_number,
        pr_status,
    )
    return None


def _auto_rebase_recovery_decision(
    context: _AutoRebaseContext,
    consumed_comment_id: int | None,
) -> _AutoRebaseDecision:
    """Run pending crash recovery and retain only an uncommitted retry."""
    if not context.pending_pre_rebase_sha:
        return _AutoRebaseDecision(True, consumed_comment_id)
    if recovery._recover_pending_auto_base_rebase(
        context.gh,
        context.spec,
        context.issue,
        context.state,
        context.worktree,
        pr_number=context.pr_number,
        label=context.label,
        pending_pre_rebase_sha=str(context.pending_pre_rebase_sha),
        pending_rewrite=attempts._pending_rewrite(context.state),
        behind=context.behind,
        unparking_consumed_max=consumed_comment_id,
    ):
        return _AutoRebaseDecision(should_continue=False)
    if not context.state.get(_AWAITING_HUMAN):
        consumed_comment_id = None
    return _AutoRebaseDecision(True, consumed_comment_id)


def _normal_auto_rebase_can_start(context: _AutoRebaseContext) -> bool:
    """Apply the clean-tree probe before deciding whether base is behind."""
    if verification_probes._worktree_dirty_files(context.worktree):
        log.debug(
            "issue=#%d skipping base sync: worktree has uncommitted changes",
            context.issue.number,
        )
        return False
    return context.behind != 0
