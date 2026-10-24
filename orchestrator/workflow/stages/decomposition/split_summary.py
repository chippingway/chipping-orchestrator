# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The summary an ordinary split posts on its parent as it finalizes, once per split attempt.

Posted by the split, or by its recovery where the split stopped short -- a
crash, a child another poller on this host held, or one whose pinned record
admission refused. It ends on a hidden
receipt naming the parent and the attempt, which a recovery posts behind only
where no comment of ours carries it: a post GitHub refused is posted again,
and one that landed ahead of a label write that did not is not posted twice.
A split recorded without `split_attempt` names no receipt to look for, and
gets none.

Beside the children it quotes the decomposer's rationale off the parent's
record rather than off the manifest in hand: the split writes it there ahead
of its first child, and the record is the one thing a split and its recovery
both hold -- the manifest is not kept and the decomposer is never asked
again -- so the two publish the same words. A record holding nothing a reader
can use, as an older binary or a hand edit may leave it, is said to have
none.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.github import comments as _github_comments
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.decomposition import (
    late_notice_fences as _notice_fences,
    state as _state,
)
from orchestrator.workflow.state import WorkflowLabel

_RECEIPT = "<!--orchestrator-split-summary:issue={issue}:attempt={attempt}-->"

# The decomposer's account of the split, named as its own and quoted after the
# children it explains. It is agent prose on a markdown thread, so it is fenced
# (`late_notice_fences`): a fence line of its own would otherwise close the
# block around it, and an HTML-comment opener outside one would hide the rest
# of it from the page.
_RECORDED_RATIONALE = "Decomposer rationale:\n\n{quoted}"

# What the summary says where the record holds no rationale a reader can use.
# Said rather than left out, so a human can tell a split nobody explained from
# a summary that dropped its explanation.
_UNRECORDED_RATIONALE = "Decomposer rationale was not recorded."


def announced(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    created: list[tuple[int, str]],
    attempt: str,
) -> WorkflowLabel:
    """Post the summary of the children `created` (number, title) names, and answer the parent's final label."""
    final_label = _final_label(state)
    announcement = _announcement(created, final_label, _state._recorded_split_rationale(state))
    if attempt:
        announcement = f"{announcement}\n\n{_RECEIPT.format(issue=issue.number, attempt=attempt)}"
    _comments._post_issue_comment(gh, issue, state, announcement)
    return final_label


def recovered(
    gh: GitHubClient, issue: Issue, state: PinnedState, children: list,
) -> WorkflowLabel:
    """Post the summary a recovered split still owes -- none where ours carries the receipt -- and answer the label."""
    attempt = str(state.get(_state._SPLIT_ATTEMPT) or "")
    # The pinned comment is named by identity: the marker test would also
    # hide a summary listing a child whose title quotes the state marker.
    if not attempt or _github_comments.carries_own_marker(
        gh.comments_after(issue, None, state_comment_id=state.comment_id),
        _RECEIPT.format(issue=issue.number, attempt=attempt),
        bot_login=getattr(gh, "_bot_login", None),
    ):
        return _final_label(state)
    return announced(gh, issue, state, [_titled(gh, number) for number in children], attempt)


def _titled(gh: GitHubClient, child_number) -> tuple[int, str]:
    """One recorded child's number and its title as GitHub reads it now."""
    return int(child_number), gh.get_issue(int(child_number)).title


def _announcement(
    created: list[tuple[int, str]], final_label: WorkflowLabel, rationale: str | None,
) -> str:
    """The summary's visible text: the count, the parent's new role, each child, and the decomposer's rationale."""
    listed = "\n".join(f"- #{number}: {title}" for number, title in created)
    count = f":bookmark_tabs: decomposer split this into {len(created)} child issue(s)"
    explained = _explained(rationale)
    if final_label == WorkflowLabel.UMBRELLA:
        return (
            f"{count}; marking parent as `{final_label}` (no implementation of "
            f"its own; will auto-resolve once every child resolves):\n\n{listed}\n\n{explained}"
        )
    return f"{count}:\n\n{listed}\n\n{explained}"


def _explained(rationale: str | None) -> str:
    """The recorded rationale fenced as the decomposer's own, or the sentence saying there is none.

    Fenced whole and never cut: the record reads back no longer than the
    bound a late record keeps a rationale at, so the fenced quote sits far
    inside one comment whatever fence lines it carries.
    """
    if rationale is None:
        return _UNRECORDED_RATIONALE
    return _RECORDED_RATIONALE.format(quoted=_notice_fences._quoted_block(rationale))


def _final_label(state: PinnedState) -> WorkflowLabel:
    """The label the manifest asked the parent to wait on its children under.

    `umbrella` is persisted ahead of the first child, so a recovery finalizes
    to it too: an umbrella resumed as `blocked` would re-enter implementation
    once every child resolved.
    """
    return WorkflowLabel.UMBRELLA if state.get(_state._UMBRELLA) else WorkflowLabel.BLOCKED
