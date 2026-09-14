# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publication refusals for dirty or unreadable implementation checkouts.

A commit may publish only from a tree proved clean. The park retains the
agent's message, records its reason and event, and advances only over the
owned notices that the shared watermark reader can prove.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import settings as config
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import comments as _comments
from orchestrator.workflow.stages.implementing import (
    park_watermarks as _park_watermarks,
    session_read as _session_read,
    state as _state,
)
from orchestrator.workflow.state import stage_name


def _on_unpublishable_tree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
    tree: _WorktreeStatus,
) -> None:
    """Park a tree a push may not be taken from, by which half of it failed.

    One seam for the one question a publication has to answer -- is this tree
    provably carrying nothing loose -- because the two ways it can answer no
    are a refusal either way and only the operator's next move differs. Paths
    git named are files to commit or clear; a reading that never happened is a
    repository to look at, and it must not be reported as the empty list it
    literally is.
    """
    if tree.paths:
        _on_dirty_worktree(gh, issue, state, agent_result, list(tree.paths))
        return
    _on_unreadable_worktree(gh, issue, state, agent_result)


def _on_dirty_worktree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
    dirty: list[str],
) -> None:
    """Park instead of pushing when the agent left uncommitted changes.

    Pushing here would publish a branch that omits the dirty files, so the PR
    would not match what the agent actually produced. We surface the situation
    to the human and resume the codex session on their reply, identical to the
    question path.
    """
    _park_unpushable_tree(
        gh, issue, state, _dirty_worktree_message(agent_result, dirty),
        {"reason": "dirty_worktree", "dirty_files": len(dirty)},
    )


def _on_unreadable_worktree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    agent_result: AgentResult,
) -> None:
    """Park instead of pushing when the tree could not be read at all.

    An unreadable tree is not a clean one. `git status` failing -- or an index
    entry git has been told to stop comparing, which makes the rest of what it
    reports unusable -- establishes nothing about what the checkout carries,
    and a push that went ahead on it would publish a branch nobody proved
    matches the work. So it is refused exactly as named dirty files are, and
    the comment says which of the two happened, since what an operator has to
    fix is a repository rather than a file list.
    """
    _park_unpushable_tree(
        gh, issue, state, _unreadable_worktree_message(agent_result),
        {"reason": "unreadable_worktree"},
    )


def _park_unpushable_tree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    message: str,
    reported: dict,
) -> None:
    """Post the refusal, hold the issue, and report it under its own reason."""
    said_before = _comments._orchestrator_ids(state)
    _comments._post_issue_comment(gh, issue, state, message)
    state.set(_state._AWAITING_HUMAN, True)
    # Mirror `_on_question`: this needs human input, so stale transient state
    # must not auto-recover over it.
    state.set(_state._PARK_REASON, None)
    state.set(_state._SILENT_PARK_COUNT, 0)
    read_to = _park_watermarks._read_this_far(gh, issue, state, said_before)
    if read_to is not None:
        state.set(_state._LAST_ACTION_COMMENT_ID, read_to)
    gh.emit_event(
        "park_awaiting_human",
        issue_number=issue.number,
        stage=stage_name(gh.workflow_label(issue)),
        **reported,
    )


def _unreadable_worktree_message(agent_result: AgentResult) -> str:
    last_msg = agent_result.last_message.strip()
    tail = ""
    if last_msg:
        quoted = _session_read._as_blockquote(last_msg)
        tail = f"\n\n_Last agent message:_\n\n{quoted}"
    return (
        f"{config.HITL_MENTIONS} agent committed but this worktree's state "
        "could not be read (`git status` failed, or an index entry is marked "
        "`assume-unchanged`/`skip-worktree`); refusing to push a branch "
        "nothing here can prove matches the work. Clear what is blocking the "
        f"read, then reply and the orchestrator will resume the session.{tail}"
    )


def _dirty_worktree_message(
    agent_result: AgentResult, dirty: list[str],
) -> str:
    shown = dirty[:10]
    files_md = "\n".join(f"- `{file_path}`" for file_path in shown)
    if len(dirty) > len(shown):
        elided = len(dirty) - len(shown)
        files_md = f"{files_md}\n- … ({elided} more)"
    last_msg = agent_result.last_message.strip()
    tail = ""
    if last_msg:
        tail = f"\n\n_Last agent message:_\n\n{_session_read._as_blockquote(last_msg)}"
    return (
        f"{config.HITL_MENTIONS} agent committed but left {len(dirty)} "
        f"uncommitted change(s); refusing to push an incomplete branch. "
        f"Reply with guidance and the orchestrator will resume the session.\n\n"
        f"{files_md}{tail}"
    )
