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
from orchestrator.workflow.state import WorkflowLabel, stage_name


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

# How much of an object id a human reads in a park message: enough to name the
# commit in a thread, and short enough to stay readable in a sentence.
_SHORT_SHA = 8


def _short(sha: str) -> str:
    """One commit as an operator reads it in a park message or a log line."""
    return (sha or "")[:_SHORT_SHA]


def _already_published_recovery_notice(
    context: _AutoRebaseRecoveryContext,
    local_head: str,
) -> str:
    """Format the notice for a recovery push that landed before restart."""
    short_head = local_head[:8]
    notice = (
        f":mag: Recovered an interrupted auto-rebase for PR "
        f"#{context.pr_number}; the new head `{short_head}` was "
        "already published before the orchestrator restart."
    )
    if context.behind == 0:
        return (
            notice
            + f" Routing `{context.label}` -> `{WorkflowLabel.VALIDATING}`"
            " so the reviewer re-runs against the rewritten branch."
        )
    return (
        notice
        + f" Base advanced again by {context.behind} commit(s)"
        " since the interrupted rebase; rebasing once more before "
        f"routing to `{WorkflowLabel.VALIDATING}`."
    )


def _pushed_recovery_notice(
    context: _AutoRebaseRecoveryContext,
    local_head: str,
) -> str:
    """Format the notice for a recovery push reissued this tick."""
    short_head = local_head[:8]
    notice = (
        f":mag: Recovered an interrupted auto-rebase for PR "
        f"#{context.pr_number}; pushed the recovered head "
        f"`{short_head}`."
    )
    if context.behind == 0:
        return (
            f"{notice} Routing `{context.label}` -> "
            f"`{WorkflowLabel.VALIDATING}`."
        )
    return (
        notice
        + f" Base advanced again by {context.behind} commit(s) "
        "since the interrupted rebase; rebasing once more before "
        f"routing to `{WorkflowLabel.VALIDATING}`."
    )
