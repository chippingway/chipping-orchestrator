# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Route merged, rejected, and human-closed work through its terminal effects.

Fresh pull-request readings determine which ending applies. An unreadable
publication is left for a later tick, and merged work keeps priority over
a closed issue's rejection path.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.issues import (
    _ISSUE_STATE_CLOSED,
    _ISSUE_STATE_OPEN,
    _STATE_ATTR,
)
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    terminal_context as _terminal_context,
    terminal_effects as _terminal_effects,
    terminal_reading as _terminal_reading,
)
from orchestrator.workflow.state import stage_name

log = logging.getLogger("orchestrator.workflow")


def _finalize_if_pr_merged(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Flip the issue to `done` when its linked PR has already merged.

    Mirrors the terminal-merge arc in `_handle_in_review` / `_handle_fixing`
    / `_handle_resolving_conflict` so the same finalize path can fire from
    any stage. Used by the umbrella / blocked aggregation when a child PR was
    merged externally but the child's workflow label was never advanced past
    the in-flight stage -- the umbrella's all-`done` aggregation would
    otherwise wait forever for that stale child. The stages that carry no
    PR-state arc of their own ask `_pr_terminal_stops_the_tick` instead, which
    answers both endings off one reading.

    Returns True when the helper finalized the issue (caller must return
    immediately); False when there is nothing to do (no `pr_number`, PR
    fetch failed, or PR is not merged). The fetch failure stays fail-OPEN
    here: an aggregation held on a child whose remote blinked is one that
    never completes, and the reading costs nothing to take again.
    """
    linked = _terminal_reading._linked_pull_request(
        gh, issue, state, "checking for external merge",
    )
    if not linked.was_read or linked.state != _terminal_reading._MERGED:
        return False
    _terminal_effects._finalize_merged_pr(
        _terminal_context._terminal_context(gh, spec, issue, state, linked.pr),
        close_error="could not close after detecting external merge",
        close_if_open_only=True,
    )
    return True


def _pr_terminal_stops_the_tick(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    linked: _terminal_reading._LinkedPullRequest | None = None,
) -> bool:
    """Both PR terminals off ONE reading, for a stage that carries neither.

    `implementing`, `validating` and `documenting` have no PR-state arc of
    their own -- `_handle_in_review` and `_handle_fixing` have always drained
    both endings inline -- so a pull request a human settled reaches them as an
    ordinary tick. What they do with one is the point: implementing measures
    the committed candidate again and pushes it, opening a second pull request
    since the first is gone, while validating and documenting spawn a reviewer
    or a docs agent against work that has already landed or been turned down.

    Both endings are decided off ONE fetch rather than a helper each, because
    two fetches are two moments: a merge landing between them reads `open` to
    the first and `merged` to the second, which the closed arc is right to
    ignore -- and the stage runs anyway, over a pull request nothing can add
    to. `_finalize_if_issue_closed` behind this drains the third ending, a
    human closing the ISSUE.

    A reading that did not come back falls through, which is the contract the
    merged terminal has always had and the one a request that can fail on any
    poll needs: answered as an ending, every issue whose remote blinked would
    stop advancing, and nothing about a failed read says which ending -- if
    any -- it was hiding. Nothing is written either way, so the next poll asks
    the same question of the same durable state.

    `linked` is for the caller that already took this reading and has already
    ACTED on it -- `implementing`, which has to tell the `discussion` plan
    from a delivery before either terminal may fire. Handed in, the
    classification and the finalize are about one snapshot; taken again here
    they would be two, and a head that moved in between would have one
    pull request classified and another ended.

    Returns True when the issue was finalized and the caller must return.
    False for an issue that records no pull request, one whose pull request is
    open, and one this host could not read.
    """
    if linked is None:
        linked = _terminal_reading._linked_pull_request(
            gh, issue, state, "checking whether it has been merged or closed",
        )
    if not linked.was_read:
        return False
    return _finalized_pr_terminal(
        _terminal_context._terminal_context(gh, spec, issue, state, linked.pr), linked.state,
    )


def _finalized_pr_terminal(
    context: _terminal_context._ReviewTerminalContext, pr_state: str,
) -> bool:
    """Route one proved pull-request state to the terminal it earns.

    Spelled apart from the reading above so the reading stays about the
    request and this stays about the two endings: `done` for a merge, and
    `rejected` for a close nobody merged.
    """
    if pr_state == _terminal_reading._MERGED:
        _terminal_effects._finalize_merged_pr(
            context,
            close_error="could not close after detecting external merge",
            close_if_open_only=True,
        )
        return True
    if pr_state == _ISSUE_STATE_CLOSED:
        _terminal_effects._finalize_rejected_pr(context)
        return True
    return False


def _drain_review_terminal(context: _terminal_context._ReviewTerminalContext) -> bool:
    if context.pr is None:
        return False
    pr_status = context.gh.pr_state(context.pr)
    if pr_status == "merged":
        _terminal_effects._finalize_merged_pr(context, close_error="could not close after merge")
        return True
    if pr_status == _ISSUE_STATE_CLOSED:
        _terminal_effects._finalize_rejected_pr(context)
        return True
    if getattr(context.issue, _STATE_ATTR, _ISSUE_STATE_OPEN) == _ISSUE_STATE_CLOSED:
        _terminal_effects._finalize_closed_issue_with_open_pr(context)
        return True
    return False


def _drain_review_pr_terminals(
    gh: GitHubClient,
    *context_args,
    stage: str,
) -> bool:
    """Drain the three PR/issue terminal arcs shared by `_handle_in_review`,
    `_handle_fixing`, and `_handle_resolving_conflict`.

    Caller passes the already-fetched PR and its own `stage` label. Each
    stage owns its fetch-failure semantics: `in_review` and
    `resolving_conflict` let `gh.get_pr` exceptions propagate to
    `_process_issue`'s catch; `fixing` catches and bails with `pr=None`
    so the rest of its handler can short-circuit. Passing `pr=None` here
    is a no-op (returns False) so fixing's deferral arrives unchanged.

    Three arcs:

      1. `pr_state == "merged"`: stamp `merged_at`, flip to `done`,
         write state, emit `pr_merged` (`merge_method="external"`),
         close the issue if still open, and clean up the branch.
      2. `pr_state == "closed"` (unmerged): stamp
         `closed_without_merge_at`, flip to `rejected`, write state,
         emit `pr_closed_without_merge`, close the issue if still open,
         and clean up the branch.
      3. Issue is closed but PR is still open (the closed-issue sweep
         surfaced a human stop signal): stamp
         `closed_without_merge_at`, flip to `rejected`, write state.
         Deliberately no event emit (the PR is still open and may be
         reopened/salvaged) and no branch cleanup (the operator may
         want the open PR's history).

    Returns True when an arc fired (caller must return immediately).
    Returns False when none fired (caller continues with the same `pr`).
    """
    spec, issue, state, pr = context_args
    return _drain_review_terminal(
        _terminal_context._ReviewTerminalContext(gh, spec, issue, state, pr, stage),
    )


def _finalize_if_issue_closed(
    gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Flip a closed-but-not-merged issue to `rejected`.

    Pairs with `_pr_terminal_stops_the_tick`: that helper drains both
    pull-request endings off one reading, this one drains the closed-issue
    counterpart so closed issues yielded by the `implementing` /
    `documenting` / `validating` sweep entries do NOT spawn the dev / docs /
    reviewer agent, push to the per-issue branch, or post on the now-closed
    issue thread. `_handle_in_review` / `_handle_fixing` carry equivalent
    guards inline via their PR-state arcs; callers in the sweep stages
    invoke this helper right after that one, so a merged or closed PULL
    REQUEST is drained first and only a closed ISSUE lands here.

    Branch cleanup follows the in_review / fixing convention: only when
    the linked PR itself is also closed (a closed PR without merge is
    `pr_closed_without_merge`-emit territory and the branch is dead
    weight). An open PR with a manually-closed issue is left alone so
    the operator can salvage / reopen it; the orchestrator-owned branch
    and worktree stay until the PR closes.

    Returns True when the caller must NOT continue the handler this
    tick: the issue was finalized to `rejected`, OR the issue is closed
    but the linked PR state could not be confirmed yet (deferred to a
    later tick so a transient fetch failure cannot permanently mis-
    label a merged-PR issue, AND so the closed issue is not driven
    through normal dev / docs / reviewer work). Returns False only
    when the issue is still open and the handler should proceed.
    """
    if getattr(issue, _STATE_ATTR, _ISSUE_STATE_OPEN) != _ISSUE_STATE_CLOSED:
        return False
    linked_pr = _terminal_reading._closed_issue_pr(gh, issue, state)
    if linked_pr.defer:
        return True
    context = _terminal_context._ReviewTerminalContext(
        gh, spec, issue, state, linked_pr.pr,
        stage_name(gh.workflow_label(issue)),
    )
    _terminal_effects._finalize_closed_issue_with_open_pr(context)
    if linked_pr.pr is not None and gh.pr_state(linked_pr.pr) == _ISSUE_STATE_CLOSED:
        _terminal_effects._emit_closed_pr_rejection(context)
    return True
