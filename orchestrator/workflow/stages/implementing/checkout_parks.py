# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publication refusals for dirty or unreadable implementation checkouts.

A commit may publish only from a tree proved clean. The park retains the
agent's message, records its reason and event, and advances only over the
owned notices that the shared watermark reader can prove.

Both refusals report the tree they were taken on, never what the run said about
it: a typed reason for which half failed, the count of paths git named where
there is one, and the bounded correlation `park_correlation` builds from the
route the caller named and the identifiers pinned state already holds.
"""
from __future__ import annotations

from typing import Any

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.git.verification.status import _WorktreeStatus
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    comments as _comments,
    guards as _guards,
    park_watermarks as _park_watermarks,
)
from orchestrator.workflow.stages.implementing import (
    park_correlation as _park_correlation,
    session_read as _session_read,
    state as _state,
)
from orchestrator.workflow.state import stage_name


def _on_unpublishable_tree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    parked: _guards._ParkedRun,
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
        _on_dirty_worktree(gh, issue, state, parked, list(tree.paths))
        return
    _on_unreadable_worktree(gh, issue, state, parked)


def _on_dirty_worktree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    parked: _guards._ParkedRun,
    dirty: list[str],
) -> None:
    """Park instead of pushing when the agent left uncommitted changes.

    Pushing here would publish a branch that omits the dirty files, so the PR
    would not match what the agent actually produced. We surface the situation
    to the human and resume the codex session on their reply, identical to the
    question path.

    The record counts the paths and names none of them: a count says how much
    is loose, which is what an operator counting these refusals needs, while
    the paths themselves are repository content and belong in the notice on
    the thread rather than in two durable sinks.
    """
    _park_unpushable_tree(
        gh, issue, state,
        _dirty_worktree_message(parked.agent_result, dirty),
        _checkout_park_fields(
            state, parked, "dirty_worktree", dirty_files=len(dirty),
        ),
    )


def _on_unreadable_worktree(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    parked: _guards._ParkedRun,
) -> None:
    """Park instead of pushing when the tree could not be read at all.

    An unreadable tree is not a clean one. `git status` failing -- or an index
    entry git has been told to stop comparing, which makes the rest of what it
    reports unusable -- establishes nothing about what the checkout carries,
    and a push that went ahead on it would publish a branch nobody proved
    matches the work. So it is refused exactly as named dirty files are, and
    the comment says which of the two happened, since what an operator has to
    fix is a repository rather than a file list.

    No `dirty_files` rides on this one, for the same reason the comment is
    worded differently: a count of zero here would report a reading that never
    happened as a tree proved to be carrying nothing.
    """
    _park_unpushable_tree(
        gh, issue, state,
        _unreadable_worktree_message(parked.agent_result),
        _checkout_park_fields(state, parked, "unreadable_worktree"),
    )


def _checkout_park_fields(
    state: PinnedState,
    parked: _guards._ParkedRun,
    reason: str,
    **extra: Any,
) -> dict[str, Any]:
    """The typed reason for a checkout refusal, and the payload beside it.

    `timed_out` is reported here and not on the question park because a run
    the timeout killed still reaches this seam: the disposition publishes a
    commit such a run managed to make, and the tree it is read on is refused
    from here. Every road into the question park has answered the timeout
    above it, so the field would be a constant there.
    """
    return {
        "reason": reason,
        **_park_correlation._correlated_fields(
            state, parked, timed_out=parked.agent_result.timed_out, **extra,
        ),
    }


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
    _park_watermarks._stamp_read_this_far(gh, issue, state, said_before)
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
