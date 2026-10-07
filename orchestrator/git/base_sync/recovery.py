# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Resume an interrupted auto-rebase in the recovery context its record is read into.

Every road that answers an anchor an earlier tick pinned is handed the same
context: the refresh's own inputs, the anchor, and the record the attempt left
of its replay -- read off the pinned comment here, since that record is what
every classification on those roads turns on. The workflow's recovery
coordinator (`workflow/engine/rewrite_recovery.py`) resumes a pushed branch's
attempt in it, and `eligibility` resumes the one a label the refresh no longer
drives leaves behind.
"""
from __future__ import annotations

from orchestrator.git.base_sync import attempt_records as _attempt_records
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
)


def _recovery_context(
    context: _AutoRebaseContext, consumed_comment_id: int | None = None,
) -> _AutoRebaseRecoveryContext:
    """`context`'s pinned attempt, resumed with the record it left and the reply it re-entered on.

    `consumed_comment_id` is the trusted human reply that released a park this
    refresh left, where one did: a finish spends it, and a road that parks
    again leaves it for the next.
    """
    return _AutoRebaseRecoveryContext(
        gh=context.gh,
        spec=context.spec,
        issue=context.issue,
        state=context.state,
        worktree=context.worktree,
        pr_number=context.pr_number,
        label=context.label,
        pending_pre_rebase_sha=str(context.pending_pre_rebase_sha),
        pending_rewrite=_attempt_records._pending_rewrite(context.state),
        behind=context.behind,
        unparking_consumed_max=consumed_comment_id,
    )
