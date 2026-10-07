# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist the parks an auto-rebase attempt ends in, and the rollback behind them.

Every refresh-time failure parks for a human the same way
(`_park_auto_rebase_failure`), and every road that has to put the checkout
back onto the anchor before it parks goes through one tail
(`_reset_clear_and_park`), which drops the attempt and the records the reset
abandoned only where the reset itself landed. The finish of a rewrite that
landed is the workflow's (`workflow/engine/rewrite_finish.py`), whichever road
reached it.
"""
from __future__ import annotations

from github.Issue import Issue

from orchestrator.git import commands
from orchestrator.git.base_sync import attempts
from orchestrator.git.base_sync.models import (
    _AutoRebaseContext,
    _AutoRebaseRecoveryContext,
)
from orchestrator.git.base_sync.state import (
    _AUTO_REBASE_PARK_REASONS,
    _PARK_REASON,
    log,
)
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState


def _park_auto_rebase_failure(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    *,
    message: str,
    reason: str,
) -> None:
    """Park an issue awaiting human for an auto-rebase failure.

    Wraps `_park_awaiting_human` so every refresh-time failure mode
    parks identically: `awaiting_human=True`, the HITL message lands
    on the issue thread (NOT the PR -- the resume-on-human-reply
    scan reads from the issue), `last_action_comment_id` is ratcheted
    forward by `_park_awaiting_human`, and the durable
    `park_reason` is re-set after the helper clears it by contract.
    `gh.write_pinned_state` is called here so the caller can return
    immediately.

    `reason` must be one of `_AUTO_REBASE_PARK_REASONS` -- the refresh
    recovery branch keys off the same set to decide whether a new
    human comment on this issue is the "retry now" signal.
    """
    # Lazy import: the guard owner sits in the workflow layer above this
    # package, and that layer imports this package at module load time, so
    # binding it here at module load would be circular.
    from orchestrator.workflow.engine import guards as _guards
    assert reason in _AUTO_REBASE_PARK_REASONS, (
        f"_park_auto_rebase_failure called with reason={reason!r}, "
        f"which is not in _AUTO_REBASE_PARK_REASONS"
    )
    _guards._park_awaiting_human(gh, issue, state, message, reason=reason)
    state.set(_PARK_REASON, reason)
    gh.write_pinned_state(issue, state)


def _reset_clear_and_park(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    reset_sha: str,
    *,
    message: str,
    reason: str,
    clean: bool = False,
) -> None:
    """Restore the worktree to `reset_sha`, drop the recovery anchor, and park.

    The shared tail of every auto-rebase park path: a rebase / push /
    recovery step could not safely finalize, so HEAD is hard-reset back
    to a known SHA (the pre-rebase anchor = the last-known remote PR
    head) so the same-tick stage handler dispatch never reads a local
    HEAD the PR may not carry, the crash-recovery anchor is cleared (the
    reset put HEAD back at it, so a follow-up tick would only hit the
    "HEAD == anchor" no-op case), and the issue is parked awaiting human.
    `clean=True` also runs `git clean -fd` after the reset to discard the
    untracked leftovers a dirty rebase produced (recoverable via
    `git reflog`).

    A failed reset / clean is logged but does not abort the park: the
    `awaiting_human` flag is what short-circuits the same-tick handlers,
    and it still lands even if the worktree is left on an unexpected SHA
    for the operator to inspect.

    What the park DROPS is held to that reset landing, and every record it
    would drop is held to it alike. The size gate measures a rebased head
    before it is pushed and, at or under the ceiling, records it as a commit
    still owed a publication -- and a reset that landed puts the branch back
    on the pre-rebase SHA, so that commit is not on this branch any more and
    only the reflog still has it. Left standing there, it is a debt nothing
    can pay and everything trips over: the pre-tick base refresh freezes this
    branch out of the sync for as long as the issue lives, and the
    reconciliation ahead of every handler stops the tick for a publication
    that is never coming. An approval whose commit was abandoned is
    superseded, which has always been one of the three things that drops one
    -- so the owner doing the abandoning is the one that drops it. The whole
    attempt goes with it for the same reason: the reset put HEAD back on the
    anchor, so a follow-up tick would find the branch exactly where the
    attempt started and have nothing to recover.

    A reset that FAILED abandoned nothing, and what the comment carries is the
    only account of where the checkout may be standing: the anchor the branch
    would go back to, the replay the attempt recorded making and the
    publication it made it for, the approved commit, the head its push is
    pinned to, and the route bookkeeping that push closes. Dropped there, the
    next tick has no anchor to bring the recovery back with and no id to ask
    for the candidate by -- it measures whatever the worktree turns out to be,
    while the permission the reset could not undo is left with nothing naming
    the attempt it belongs to. So nothing is dropped: the reset is proved
    first, and every record follows it rather than the intent.

    The permission a transfer granted goes in the same write and for the same
    reason: a rebase of a commit an authorized settlement accepted may be licensed to
    carry that verdict over, and the reset puts the branch back onto the
    commit the exemption never left. The exemption itself needs no repair --
    the grant moved nothing -- so what is left over is a claim about a push
    that will never happen, for an object no branch has any more. Only an
    outstanding record this build can read back whole is dropped, which is the
    rollback's own rule wherever a rewrite is undone.
    """
    reset = commands._git_hardened(
        "reset", "--hard", reset_sha, cwd=context.worktree,
    )
    restored = reset.returncode == 0
    if not restored:
        log.error(
            "issue=#%d auto-rebase recovery: reset --hard to %s failed: "
            "%s; the awaiting_human park still short-circuits same-tick "
            "handler dispatch but operator inspection of HEAD is needed",
            context.issue.number,
            reset_sha[:8],
            (reset.stderr or "").strip(),
        )
    if clean:
        cleaned = commands._git_hardened("clean", "-fd", cwd=context.worktree)
        if cleaned.returncode != 0:
            log.error(
                "issue=#%d auto-rebase recovery: `git clean -fd` after "
                "the reset failed: %s",
                context.issue.number, (cleaned.stderr or "").strip(),
            )
    if restored:
        attempts._clears_the_attempt(context.state)
        _forgets_the_reset(context, reset_sha)
    _park_auto_rebase_failure(
        context.gh,
        context.issue,
        context.state,
        message=message,
        reason=reason,
    )


def _forgets_the_reset(
    context: _AutoRebaseContext | _AutoRebaseRecoveryContext,
    reset_sha: str,
) -> None:
    """Drop what a landed reset just took the branch off, in memory.

    Both records name a commit only the reflog still has once the branch is
    back on the pre-rebase anchor: the approval says a push is owed for it,
    and a transfer's permission says what that push may carry a human's
    verdict over. Neither has anything left to be paid by, and both are staged
    rather than written so the park's own write is what makes the drop
    durable.
    """
    # Lazily bound for the reason the guard owner is: the size gate sits in
    # the workflow layer above this package, and binding it at module load
    # would make every git-side import pay for the stage tree.
    from orchestrator.workflow.stages.implementing import (
        late_approval_reading as _late_approval_reading,
        late_approval_state as _late_approval_state,
        late_records,
        late_transfer,
    )
    if _late_approval_reading._approved_commit(context.state) != reset_sha:
        _late_approval_state._forget_approval(context.state)
    late_transfer._abandoned_authorization(
        late_records._gate(
            context.gh, context.spec, context.issue, context.state,
            context.worktree,
        ),
        reset_sha,
    )
