# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The four ways a documenting tick stops and waits for a human, and one hold.

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

`_holds_the_delivery_cursor` is the hold, and it sits here rather than beside
the road that needs it because it has to ride the park's OWN write. A drift
unwind runs no agent, so a park it takes may not carry the delivery cursor
over the comment that moved the requirements -- and a correction applied
afterwards is a second write, which a crash between the two loses in the
direction that waits forever. `_asked_since` is the other half of that split:
where the hold is in force, the boundary a parked road reads its replies from
is the notice, not the cursor.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
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

    A park taken while a drift UNWIND is pending holds the delivery cursor
    back instead of carrying it, because that road runs no agent at all: the
    comment that moved the requirements is still unread, and a cursor left on
    this notice would mark it answered by a git failure. The unwind block owns
    every tick a pending unwind stands on, so no docs-pass park ever reaches
    that branch.
    """
    delivered_through = ctx.state.get(_state._LAST_ACTION_COMMENT_ID)
    _guards._park_awaiting_human(
        ctx.gh, ctx.issue, ctx.state, message, reason=reason,
    )
    ctx.state.set(_state._PARK_REASON, reason)
    if ctx.state.get(_state._UNWIND_PENDING):
        _holds_the_delivery_cursor(ctx.state, delivered_through)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _asked_since(state: PinnedState) -> int | None:
    """The comment a parked tick reads its replies from.

    Ordinarily the delivery cursor, which a park stamps at the notice it
    posted, so "what a human has said since we asked" and "what nobody has
    delivered" are one boundary. A drift unwind is where they part: its road
    hands nothing to any agent, so it holds the cursor back over the words
    that moved the requirements and records its own notice beside it. Every
    road that classifies a parked reply reads THIS, or the instruction the
    unwind never delivered joins the batch -- and a bare `/orchestrator
    continue` beside it reads as a command somebody wrote guidance for, which
    is the one shape that is neither refused nor retried.
    """
    asked_at = state.get(_state._UNWIND_ASKED_AT)
    if isinstance(asked_at, int):
        return asked_at
    return state.get(_state._LAST_ACTION_COMMENT_ID)


def _holds_the_delivery_cursor(state: PinnedState, delivered_through) -> None:
    """Put back the delivery cursor an unwind's park just moved, before the
    write that would make it durable.

    The shared park records the thread read as far as the notice it posted,
    which is right for a park decided between two of one tick's own steps: our
    own sentence has to be crossed or the next poll answers itself. Nothing on
    the unwind road delivered anything, so the comment that MOVED the
    requirements sits below that notice having reached no agent -- and the
    `workflow:fixing` round the eventual retry hands the issue to would never
    see it.

    What the park's mark is still needed for is the silence that road keeps
    while nothing fresh has happened, so it is kept as the unwind's own
    boundary and the cursor goes back where it was. Both go down in the write
    the park was going to make anyway: a correction in a SECOND write is one a
    crash between them loses, and it loses it in the direction that strands
    the input -- a cursor on our notice, no boundary beside it, and a gate
    that then falls back to that cursor and waits for a comment nobody has
    any reason to write.
    """
    asked_at = state.get(_state._LAST_ACTION_COMMENT_ID)
    if isinstance(asked_at, int):
        state.set(_state._UNWIND_ASKED_AT, asked_at)
    state.set(_state._LAST_ACTION_COMMENT_ID, delivered_through)


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
    state. The reported route names the docs pass so the record says which
    kind of developer run left the tree loose, which the shared refusal --
    reached from a fresh run, a fix round, and a rebase resume as well -- can
    only be told by its caller."""
    _checkout_parks._on_dirty_worktree(
        ctx.gh, ctx.issue, ctx.state,
        _guards._ParkedRun(
            documentation_result, _guards._ROUTE_DOCS_PASS,
        ),
        dirty,
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
    _dev_parks._on_question(
        ctx.gh, ctx.issue, ctx.state,
        _guards._ParkedRun(
            documentation_result, _guards._ROUTE_DOCS_PASS,
        ),
    )
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)
