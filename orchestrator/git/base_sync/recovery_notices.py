# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Deliver a recovered rebase notice and its audit event.

Persistence coordinates their order with the durable announcement checkpoint
and subsequent routing. A comment failure is reported without preventing the
recovered publication from being recorded.
"""
from __future__ import annotations

from orchestrator.git.base_sync.models import (
    _AutoRebaseRecoveryContext,
)
from orchestrator.git.base_sync.state import (
    log,
)
from orchestrator.workflow.state import stage_name


def _post_recovered_rebase_notice(
    context: _AutoRebaseRecoveryContext, notice: str,
) -> None:
    """Post the recovery notice without blocking state finalization."""
    # Lazy import: the comment owner sits in the workflow layer above this
    # package, so binding it at module load would make every git-side
    # import pay for the GitHub client and prompt state it pulls in.
    from orchestrator.workflow.engine import comments as _comments
    try:
        _comments._post_pr_comment(
            context.gh, context.pr_number, context.state, notice,
        )
    except Exception:  # noqa: BLE001 - the PR notice is best effort at the GitHub boundary
        log.exception(
            "issue=#%s could not post auto-rebase recovery notice to "
            "PR #%s", context.issue.number, context.pr_number,
        )


def _emit_recovered_rebase_event(
    context: _AutoRebaseRecoveryContext,
    local_head: str,
    method: str,
) -> None:
    """Emit the stable audit shape for a recovered auto-rebase."""
    context.gh.emit_event(
        "base_rebased",
        issue_number=context.issue.number,
        stage=stage_name(context.label),
        pr_number=context.pr_number,
        sha=local_head,
        method=method,
        review_round=0,
        retry_count=context.state.get("retry_count"),
    )
