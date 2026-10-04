# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The summary an ordinary split posts on its parent, once for each split attempt.

The summary names every child the split created and the label the parent is
finalized to, and it is posted as the parent is finalized: by the split itself,
or by its recovery where the split stopped short of that -- a crash, or a child
another poller on this host held when the split went to seed it, which leaves
the summary and the finalize to the recovery on purpose.

A recovery cannot tell a split that never got as far as the summary from one
that posted it and died before the label flip, so the summary carries a hidden
receipt naming the parent and the split attempt (`split_receipts` mints it),
and the recovery posts it only where no comment of ours on the thread carries
that receipt. A split an older binary made names no attempt, and its recovery
finalizes without a summary, since no receipt could say one is already there.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github import comments as _github_comments
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.decomposition import state as _state
from orchestrator.workflow.state import WorkflowLabel

_RECEIPT = "<!--orchestrator-split-summary:issue={issue}:attempt={attempt}-->"


def announced(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    created: list[tuple[int, str]],
    attempt: str,
) -> WorkflowLabel:
    """Post the summary of the children `created` names, and answer the label the parent is finalized to.

    `created` is each child's number and title, in creation order. The umbrella
    flag is read off `state`, where the split persisted it ahead of the first
    child. Only the in-memory record takes the comment's id; the caller's
    finalize writes it.
    """
    final_label = _final_label(state)
    announcement = _announcement(created, final_label)
    if attempt:
        announcement = f"{announcement}\n\n{_RECEIPT.format(issue=issue.number, attempt=attempt)}"
    _comments._post_issue_comment(gh, issue, state, announcement)
    return final_label


def recovered(
    gh: GitHubClient, issue: Issue, state: PinnedState, children: list,
) -> WorkflowLabel:
    """Post the summary a recovered split still owes, and answer the label the parent is finalized to.

    Owed unless the thread already carries this attempt's receipt on a comment
    of ours: a recovery that posted it and failed before the finalize landed
    is retried by the next tick, which must not post it twice. Each child's
    title is read off the child, which the split created with the slice's own.
    """
    attempt = str(state.get(_state._SPLIT_ATTEMPT) or "")
    if not attempt or _github_comments.carries_own_marker(
        gh.comments_after(issue, None),
        _RECEIPT.format(issue=issue.number, attempt=attempt),
        bot_login=getattr(gh, "_bot_login", None),
    ):
        return _final_label(state)
    return announced(gh, issue, state, [_titled(gh, number) for number in children], attempt)


def _titled(gh: GitHubClient, child_number) -> tuple[int, str]:
    """One recorded child's number and the title it was created with."""
    return int(child_number), gh.get_issue(int(child_number)).title


def _announcement(created: list[tuple[int, str]], final_label: WorkflowLabel) -> str:
    """The summary's visible text: the count, the parent's new role, and each child."""
    listed = "\n".join(f"- #{number}: {title}" for number, title in created)
    count = f":bookmark_tabs: decomposer split this into {len(created)} child issue(s)"
    if final_label == WorkflowLabel.UMBRELLA:
        return (
            f"{count}; marking parent as `{final_label}` (no implementation of "
            f"its own; will auto-resolve once every child resolves):\n\n{listed}"
        )
    return f"{count}:\n\n{listed}"


def _final_label(state: PinnedState) -> WorkflowLabel:
    """The label the manifest asked the parent to wait on its children under.

    `umbrella` is persisted beside the expected count, ahead of the first
    child, so a recovery finalizes to what the manifest asked for: a parent
    with no implementation of its own that resumed as `blocked` would re-enter
    implementation once every child resolved.
    """
    return WorkflowLabel.UMBRELLA if state.get(_state._UMBRELLA) else WorkflowLabel.BLOCKED
