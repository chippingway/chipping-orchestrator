# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What has to be settled before a docs agent may spawn.

Three of these end the tick outright. A PR merged, one closed without a
merge, or an issue closed out of band means the docs pass would run against
work that has already landed or been turned down, so all three are read before
anything spends tokens. The two pull-request endings come off ONE guarded
reading -- `done` for the merge, `rejected` for the close -- because two
fetches are two moments, and because a closed PR leaves the ISSUE open, so
nothing else here would see it. A
`documenting` label with no pinned `pr_number` has nothing to anchor on. And a
content-free `/orchestrator continue` has to be classified here, ahead of the
drift and resume paths, because documenting keeps no preserved feedback batch
to replay: a bare continue either retries a session failure by rerunning the
whole documentation prompt or it needs a human's actual words, and only the
second one is refused.

The fourth is the quiet one: an already-parked issue with no new trusted reply
returns before the fetch and ahead/behind probe, so a transient park does not
re-post its comment on every poll and an outsider's comment cannot wake a docs
pass an allowlist was meant to keep them out of.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.base_sync import state as _base_sync_state
from orchestrator.github.client import GitHubClient
from orchestrator.github.comments import filter_trusted
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    messages as _messages,
    terminals as _terminals,
)
from orchestrator.workflow.stages.documenting import (
    parks as _parks,
    state as _state,
)


def _finalize_documenting_terminal(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Terminal issue/PR short-circuits before the docs pass runs.

    Both PR endings come off ONE reading. External merge: if the PR was
    merged before the docs pass ran, finalize to `done` rather than
    fetching the branch and running the documenting agent against an
    already-landed PR. Closed PR: one somebody closed without merging
    leaves the ISSUE open, so the counterpart below never sees it -- flip
    to `rejected` rather than running the docs agent against rejected
    work and pushing onto a pull request that is gone. Closed-issue
    counterpart: the
    closed-`documenting` sweep yields issues a human closed without a
    merged PR -- flip to `rejected` so the docs agent does not run
    against a closed issue.

    Returns True when the issue was routed to a terminal state and the
    caller must return.
    """
    if _terminals._pr_terminal_stops_the_tick(gh, spec, issue, state):
        return True
    return _terminals._finalize_if_issue_closed(gh, spec, issue, state)


def _documenting_parked_no_input(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Already-parked, no-new-input fast path.

    When `awaiting_human` is set and no human comment has arrived since
    the park (and drift did not clear the flag), there is nothing to act
    on. Skip the fetch + ahead/behind check entirely so a transient
    failure mode (fetch_failed / diverged_branch) does NOT re-post its
    park comment every tick -- non-recoverable parks (agent_question /
    dirty_worktree / agent_silent) likewise stay silent until a human
    reply. Validating uses the same shape via its transient-park recovery
    branch; documenting has no transient recovery yet, so the early
    return alone is enough.

    Returns True when the issue is parked with nothing to act on (the
    caller must return), False to proceed with the normal docs flow.
    """
    if not state.get(_state._AWAITING_HUMAN):
        return False
    # The refresh-time `_AUTO_REBASE_PARK_REASONS` parks belong to the
    # `_sync_pr_worktree_to_base` retry loop -- the operator's new comment
    # is the "retry the rebase" signal, NOT a documenting-stage trigger.
    # Stay silent so the refresh keeps ownership of the comment.
    if state.get(_state._PARK_REASON) in _base_sync_state._AUTO_REBASE_PARK_REASONS:
        return True
    last_action_id = state.get(_state._LAST_ACTION_COMMENT_ID)
    # Only a trusted reply wakes a parked docs pass: with `ALLOWED_ISSUE_AUTHORS`
    # set an outsider comment must read as silence so the park survives instead
    # of falling through to the docs resume in `_run_documenting_dev`.
    return not filter_trusted(gh.comments_after(issue, last_action_id))


def _refuse_parked_continue_command(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> bool:
    """Refuse a content-free `/orchestrator continue` on a `documenting` park
    that needs real human guidance, BEFORE the drift / resume paths.

    Documenting has no preserved feedback batch to replay, so a bare continue
    resolves to just two shapes: a retryable session-failure park
    (`agent_silent` / `agent_timeout` / `agent_execution_failed`) whose
    awaiting-human resume reruns the FULL documentation prompt, and a park
    that needs a real answer. A bare continue no longer shifts `user_content_hash`, so `_reconcile_documenting_drift`
    stays silent and the retry falls through to `_run_documenting_dev`'s resume
    (issue #729) -- only the refusal needs interception here.

    The batch is cut from what the park ASKED (`parks._asked_since`), which on
    a drift unwind is the notice it posted rather than the delivery cursor
    that road deliberately holds back. Cut from the cursor, the instruction
    the unwind delivered to nobody would sit in the batch beside the command
    and demote it to guidance -- and the reconcile behind this would run on an
    operator's bare nudge, which is exactly what the refusal exists to stop.

    Returns True when a content-free continue on a non-retryable park was
    refused (command consumed, note posted, state written) and the caller must
    return. Returns False to fall through: not parked, an auto-rebase park (the
    refresh loop owns the nudge), no new comment, no bare continue, a retryable
    park, or a command posted alongside genuine guidance.
    """
    if not state.get(_state._AWAITING_HUMAN):
        return False
    park_reason = state.get(_state._PARK_REASON)
    if park_reason in _base_sync_state._AUTO_REBASE_PARK_REASONS:
        return False
    new_comments = filter_trusted(
        gh.comments_after(issue, _parks._asked_since(state))
    )
    if not new_comments:
        return False
    if _messages._continue_command_action(new_comments, park_reason) != "refuse":
        return False
    delivered_through = state.get(_state._LAST_ACTION_COMMENT_ID)
    _messages._refuse_parked_continue(gh, issue, state, new_comments)
    # A refusal delivers nothing either, so on the unwind road it moves that
    # road's own boundary and leaves the delivery cursor where the park left
    # it. In the write below rather than one of its own: the shared refusal
    # mutates memory and this is the write that makes all of it durable.
    if state.get(_state._UNWIND_PENDING):
        _parks._holds_the_delivery_cursor(state, delivered_through)
    gh.write_pinned_state(issue, state)
    return True


def _documenting_preconditions_handled(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
    pr_number,
) -> bool:
    """Run the pre-context guards; True when the tick is already resolved.

    Covers PR-state terminals, a `documenting` label with no pinned
    `pr_number`, and an operator `/orchestrator continue` refused on a park
    that needs real guidance. A bare continue does not shift
    `user_content_hash`, so the retryable resume later reruns the docs prompt
    without a spurious drift notice. See `_refuse_parked_continue_command`.
    """
    if _finalize_documenting_terminal(gh, spec, issue, state):
        return True
    if pr_number is None:
        _parks._park_documenting_without_pr(gh, issue, state)
        return True
    return _refuse_parked_continue_command(gh, issue, state)
