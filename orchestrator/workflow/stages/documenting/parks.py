# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The four ways a documenting tick stops and waits for a human.

Three of them go through `_park_documenting`, which re-stamps `park_reason`
after the shared HITL park cleared it: the tag is what a later tick branches on
-- the awaiting-human resume reads it to tell a stale flag from a live park,
`/orchestrator continue` keys its retry-or-refuse decision off it, and the
refresh loop recognizes its own auto-rebase reasons in it. The fourth, the
missing-`pr_number` park, is the one that must not repeat: it fires on a label
an operator applied by hand and would otherwise re-post on every poll, so
`awaiting_human` alone gates it.

The dirty-tree and question parks defer to the implementing owner rather than
composing their own notice, because both carry state this stage does not model
-- the classified reason and the silent-park streak that eventually rotates a
poisoned session, and the dirty-file count that rides on the event. Every park
here writes pinned state, so the caller returns unconditionally.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import settings as config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.documenting import (
    models as _models,
    state as _state,
)
from orchestrator.workflow.stages.implementing import checkout_parks as _checkout_parks, parks as _dev_parks
from orchestrator.workflow.state import WorkflowLabel


def _park_documenting(
    ctx: _models._DocumentingContext, message: str, reason: str,
) -> None:
    """Park the docs pass awaiting a human and re-stamp the durable
    `park_reason`.

    `_park_awaiting_human` clears `park_reason` by contract; re-set the
    durable tag so future ticks / dashboards can branch on it -- documenting's
    awaiting-human resume also reads it to distinguish stale park flags after
    a relabel. Writes pinned state; the caller returns unconditionally.
    """
    _guards._park_awaiting_human(
        ctx.gh, ctx.issue, ctx.state, message, reason=reason,
    )
    ctx.state.set(_state._PARK_REASON, reason)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _park_documenting_without_pr(
    gh: GitHubClient, issue: Issue, state: PinnedState,
) -> None:
    """Park a `documenting` issue that has no pinned `pr_number`.

    Documenting only runs against an existing PR worktree. Without a
    pinned `pr_number` we cannot anchor on the dev's branch and must not
    branch off the base (that would orphan the docs commit from the
    implementing PR). Park once and let the operator relabel; idempotency
    by `awaiting_human` mirrors `_handle_in_review`'s missing-pr-number
    guard.
    """
    if state.get(_state._AWAITING_HUMAN):
        return
    # The relabel instruction names the label verbatim: it is what the human
    # reading this has to type into GitHub, so it carries the namespace even
    # though the prose around it names the stage.
    _guards._park_awaiting_human(
        gh, issue, state,
        f"{config.HITL_MENTIONS} `{WorkflowLabel.DOCUMENTING}` without a "
        "pinned `pr_number`; the documenting stage runs against an existing "
        f"PR worktree. Relabel back to `{WorkflowLabel.IMPLEMENTING}` "
        "(the dev's PR opens there) after fixing.",
        reason="missing_pr_number",
    )
    gh.write_pinned_state(issue, state)


def _park_documenting_dirty(
    ctx: _models._DocumentingContext, documentation_result: AgentResult, dirty,
) -> None:
    """Park an uncommitted docs edit via `_on_dirty_worktree`; writes pinned
    state."""
    _checkout_parks._on_dirty_worktree(
        ctx.gh, ctx.issue, ctx.state, documentation_result, dirty,
    )
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _park_documenting_question(
    ctx: _models._DocumentingContext, documentation_result: AgentResult,
) -> None:
    """Park an unknown verdict via `_on_question`.

    `_on_question` posts the HITL ping, distinguishes the silent-crash case
    via stderr diagnostics, and tags `silent_park_count` so a poisoned session
    can be dropped on the next resume. Writes pinned state.
    """
    _dev_parks._on_question(ctx.gh, ctx.issue, ctx.state, documentation_result)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
