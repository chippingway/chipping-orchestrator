# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Complete ordinary crash recovery or park its checkout and push failures.

The recovery coordinator supplies the verified comparison and preserves the
order of its decisions. Replay-specific refusal outcomes live with their
checkout, publication, and transfer owners; recovery notices own the messages
posted by a successful finish.
"""
from __future__ import annotations

from orchestrator.config import settings as config
from orchestrator.git.base_sync import persistence, recovery_notices as _recovery_notices, snapshot
from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
    _AutoRebaseRecoverySnapshot,
)
from orchestrator.git.base_sync.state import (
    _REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    log,
)


def _finalize_already_published_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Finalize state after confirming that the interrupted push landed."""
    return persistence._finalize_recovered_rebase(
        context,
        local_head=recovery_snapshot.local_head,
        method="crash_recovery_relabel_only",
        notice=_recovery_notices._already_published_recovery_notice(
            context, recovery_snapshot.local_head,
        ),
    )


def _reject_unknown_recovery_comparison(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Park when unequal heads cannot be classified as ahead or behind."""
    log.warning(
        "issue=#%d auto-rebase recovery: local HEAD (`%s`) differs "
        "from remote PR head (`%s`) but the divergence probe "
        "returned `(0, 0)`; aborting recovery and parking awaiting "
        "human",
        context.issue.number,
        recovery_snapshot.local_head[:8],
        recovery_snapshot.remote_head[:8],
    )
    local_short = recovery_snapshot.local_head[:8]
    remote_short = recovery_snapshot.remote_head[:8]
    return snapshot._abort_recovery_unverified(
        context,
        f"local HEAD `{local_short}` differs from remote "
        f"PR head `{remote_short}` but "
        "the divergence probe returned `(0, 0)`, which means the "
        "remote-tracking ref we just fetched could not be read or "
        "compared against -- the path the recovery would take next "
        "cannot be determined safely.",
    )


def _park_diverged_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Restore the anchor instead of overwriting an out-of-band PR update."""
    spec = context.spec
    local_short = recovery_snapshot.local_head[:8]
    pre_rebase_short = _recovery_notices._short(context.pending_pre_rebase_sha)
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: local worktree "
            f"(`{local_short}`) is {recovery_snapshot.ahead} ahead "
            f"and {recovery_snapshot.behind} behind remote "
            f"`{spec.remote_name}/{recovery_snapshot.branch}` -- the "
            "remote PR branch was updated out-of-band during the "
            "interrupted auto rebase. HEAD has been reset to the pre-"
            f"rebase SHA `{pre_rebase_short}`. "
            "Investigate the remote PR head and reply on this issue "
            "with anything once the divergence is reconciled."
        ),
        reason=_REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    )
    return True


def _park_dirty_recovery(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
    dirty_files: list[str],
) -> bool:
    """Reset and clean a recovered rebase that carries worktree changes."""
    local_short = recovery_snapshot.local_head[:8]
    pre_rebase_short = _recovery_notices._short(context.pending_pre_rebase_sha)
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: the rebased worktree (recovered "
            f"from a prior tick, HEAD `{local_short}`) "
            f"carries {len(dirty_files)} uncommitted change(s). HEAD "
            "has been reset to the pre-rebase SHA "
            f"`{pre_rebase_short}` and untracked "
            "files cleaned (use `git reflog` if you need the "
            "discarded edits). Investigate, then reply on this issue "
            "with anything to retry."
        ),
        reason="auto_base_rebase_dirty",
        clean=True,
    )
    return True


def _park_failed_recovery_push(
    context: _AutoRebaseRecoveryContext,
    recovery_snapshot: _AutoRebaseRecoverySnapshot,
) -> bool:
    """Restore the anchor after a recovered force-push fails."""
    local_short = recovery_snapshot.local_head[:8]
    pre_rebase_short = _recovery_notices._short(context.pending_pre_rebase_sha)
    persistence._reset_clear_and_park(
        context,
        context.pending_pre_rebase_sha,
        message=(
            f"{config.HITL_MENTIONS} crash recovery for PR "
            f"#{context.pr_number}: `--force-with-lease` push of the "
            f"recovered rebase (`{local_short}`, lease "
            f"against `{pre_rebase_short}`) failed. "
            "HEAD has been reset to the pre-rebase SHA. Most likely "
            "the remote PR branch was updated out-of-band; investigate "
            "and reply on this issue with anything to retry."
        ),
        reason=_REASON_AUTO_BASE_REBASE_PUSH_FAILED,
    )
    return True
