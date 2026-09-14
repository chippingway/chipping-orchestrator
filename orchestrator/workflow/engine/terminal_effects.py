# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist terminal stamps, labels, usage verdicts, and events before closing and cleanup.

Merged and rejected work retain their effect order and event attribution.
A human-closed issue with an open publication records its end while leaving
that publication available to its own terminal decision.
"""
from __future__ import annotations

import logging

from orchestrator.git.worktrees import naming as _naming, terminal as _worktree_terminal
from orchestrator.github.issues import (
    _ISSUE_STATE_CLOSED,
    _ISSUE_STATE_OPEN,
    _STATE_ATTR,
)
from orchestrator.workflow.engine import (
    issue_usage as _issue_usage,
    terminal_context as _terminal_context,
    terminal_reading as _terminal_reading,
    usage as _usage,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")



def _close_terminal_issue(
    context: _terminal_context._ReviewTerminalContext, error_message: str,
) -> None:
    try:
        context.issue.edit(state=_ISSUE_STATE_CLOSED)
    except Exception:
        log.exception(
            "issue=#%s %s", context.issue.number, error_message,
        )


def _cleanup_review_terminal(context: _terminal_context._ReviewTerminalContext) -> None:
    _worktree_terminal._cleanup_terminal_branch(
        context.gh,
        context.spec,
        context.issue.number,
        branch=_naming._resolve_branch_name(
            context.state, context.spec, context.issue.number,
        ),
    )


def _finalize_merged_pr(
    context: _terminal_context._ReviewTerminalContext,
    *,
    close_error: str,
    close_if_open_only: bool = False,
) -> None:
    context.state.set("merged_at", _usage._now_iso())
    context.gh.set_workflow_label(context.issue, WorkflowLabel.DONE)
    _issue_usage._post_issue_usage_verdict(context.gh, context.issue, context.state)
    context.gh.write_pinned_state(context.issue, context.state)
    context.gh.emit_event(
        "pr_merged",
        issue_number=context.issue.number,
        stage=context.stage,
        pr_number=context.pr_number,
        sha=getattr(context.pr.head, _terminal_reading._HEAD_SHA_ATTR, None) or None,
        merge_method="external",
        review_round=int(context.state.get("review_round") or 0),
        conflict_round=context.conflict_round,
        retry_count=context.state.get("retry_count"),
    )
    if (
        not close_if_open_only
        or getattr(context.issue, _STATE_ATTR, _ISSUE_STATE_OPEN) != _ISSUE_STATE_CLOSED
    ):
        _close_terminal_issue(context, close_error)
    _cleanup_review_terminal(context)


def _finalize_rejected_pr(context: _terminal_context._ReviewTerminalContext) -> None:
    context.state.set("closed_without_merge_at", _usage._now_iso())
    context.gh.set_workflow_label(context.issue, WorkflowLabel.REJECTED)
    _issue_usage._post_issue_usage_verdict(context.gh, context.issue, context.state)
    context.gh.write_pinned_state(context.issue, context.state)
    context.gh.emit_event(
        "pr_closed_without_merge",
        issue_number=context.issue.number,
        stage=context.stage,
        pr_number=context.pr_number,
        sha=getattr(context.pr.head, _terminal_reading._HEAD_SHA_ATTR, None) or None,
        review_round=int(context.state.get("review_round") or 0),
        conflict_round=context.conflict_round,
        retry_count=context.state.get("retry_count"),
    )
    _close_terminal_issue(context, "could not close after reject")
    _cleanup_review_terminal(context)


def _finalize_closed_issue_with_open_pr(context: _terminal_context._ReviewTerminalContext) -> None:
    context.state.set("closed_without_merge_at", _usage._now_iso())
    context.gh.set_workflow_label(context.issue, WorkflowLabel.REJECTED)
    _issue_usage._post_issue_usage_verdict(context.gh, context.issue, context.state)
    context.gh.write_pinned_state(context.issue, context.state)


def _emit_closed_pr_rejection(context: _terminal_context._ReviewTerminalContext) -> None:
    context.gh.emit_event(
        "pr_closed_without_merge",
        issue_number=context.issue.number,
        stage=context.stage,
        pr_number=context.pr_number,
        sha=getattr(context.pr.head, _terminal_reading._HEAD_SHA_ATTR, None) or None,
        review_round=int(context.state.get("review_round") or 0),
        conflict_round=context.state.get("conflict_round"),
        retry_count=context.state.get("retry_count"),
    )
    _cleanup_review_terminal(context)
