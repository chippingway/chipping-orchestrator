# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Conflict parks and the durable reason that distinguishes them.

Transient refusals cannot replace a question already waiting on a human.
A repeated refusal can suppress its notice while still persisting the state
that this pass owes; unreadable heads and worktrees retain their own reasons.
"""
from __future__ import annotations

import logging

from orchestrator import config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.stages.conflicts import models as _models, state as _state

log = logging.getLogger("orchestrator.workflow")



def _park_conflict(
    ctx: _models._ConflictContext, message: str, *, reason: str,
    once: bool = False,
) -> None:
    """Park awaiting human and persist pinned state.

    Every `resolving_conflict` park pairs `_park_awaiting_human` with the
    matching `write_pinned_state`; routing them through here keeps the two
    from drifting apart across the handler's many exits.

    The reason is recorded durably as well as emitted, because two decisions
    past the park are made on it: whether the tick that finds it standing
    waits for a human or retries the reading that failed, and whether a
    refusal re-taken on a later tick is the SAME refusal.

    `once` answers the second. A refusal a tick can re-take every poll -- a
    ref nothing resolves, a branch that stays diverged -- would put a fresh
    notice on the thread each tick and bury the one an operator has to act on.
    So it is said once, and "once" means once per REASON rather than once per
    park: an issue parked on an agent's question that then becomes diverged is
    being told something new, and telling it is the whole point. Only the
    identical refusal standing again is silent, and there the flags are
    already what a park is, so the state write is all that is owed.

    A transient refusal taken over a park somebody OWES AN ANSWER TO is the
    other silence, and it answers the first decision. Recorded, the reason
    would be the one the next tick reads, and a reading that comes back is
    what clears a transient park -- so a fetch that failed for one poll while
    an agent's question stood unanswered would hand the tick after it a branch
    that reads as nobody waiting, and it would rebase, push, count the round
    and hand a `validating` reviewer work the human was asked about. The park
    already standing is the one that governs; the reading is retried under it
    every tick regardless, and it is not announced again because the notice an
    operator has to act on is the one already on the thread.
    """
    if _says_nothing_new(ctx.state, reason, once=once):
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    _guards._park_awaiting_human(ctx.gh, ctx.issue, ctx.state, message, reason=reason)
    # `_park_awaiting_human` clears the durable field on purpose, so every
    # caller that needs one re-sets it. This stage needs one on all of them.
    ctx.state.set(_state._PARK_REASON, reason)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _says_nothing_new(
    state: PinnedState, reason: str, *, once: bool,
) -> bool:
    """Whether this refusal adds nothing to the park already standing.

    Two shapes, and in both the flags are already what a park is, so all the
    caller still owes is the durable write.

    The identical refusal re-taken, which `once` asks for: what clears one of
    these is a reading rather than a reply, so every tick after it takes it
    again.

    And a transient refusal over a park a human owes an answer to, where
    recording it would REPLACE the standing reason with one the next tick
    reads as retryable -- the awaiting-human resume would be skipped and the
    rebase behind it would run while the question is still open.
    """
    if once and state.get(_state._PARK_REASON) == reason:
        return True
    return reason in _state._TRANSIENT_PARKS and _waits_on_a_human(state)


def _waits_on_a_human(state: PinnedState) -> bool:
    """Whether this issue is parked on something only a person can answer.

    The awaiting-human flag alone does not say it: every refusal this stage
    takes sets it, including the ones that name a reading that DID NOT HAPPEN
    and so name nothing a reply could address. Those are told apart by the
    durable reason, which is why both readers -- the resume that would consume
    a tick on a reply, and the park that would otherwise overwrite the reason
    they turn on -- ask this one predicate rather than spelling it twice.
    """
    if not state.get(_state._AWAITING_HUMAN):
        return False
    return state.get(_state._PARK_REASON) not in _state._TRANSIENT_PARKS


def _park_unreadable_head(ctx: _models._ConflictContext) -> None:
    """Stop a round whose checkout could not name the head it begins at.

    Shared by the two seams that read that head: the rebase, which leases the
    push its clean exit makes against it, and the body-edit resume, whose
    publication leases against it too. It is not bookkeeping either of them
    could go on without. The size gate reads "no head" as a caller that
    established none, and pins the push to whatever the pull request is
    standing on when IT looks -- which is after the rebase, or after an agent
    that was out for minutes. A commit somebody else landed in that window
    becomes the lease and is force-overwritten by work never proved against
    it.

    Refused before either runs, so nothing is rebased, no agent is spawned
    over a checkout nobody could read, and neither caller has consumed
    anything it would have to put back.
    """
    spec = ctx.spec
    log.error(
        "issue=#%d resolving_conflict: could not read the head its worktree "
        "stands on; refusing to rebase or resume over a checkout nobody read",
        ctx.issue.number,
    )
    _park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} nothing could read the commit this issue's "
        f"worktree stands on, so `git rebase {spec.remote_name}/"
        f"{spec.base_branch}` was not run and no dev session was resumed. "
        "That commit is the head every exit of this round leases its "
        "force-push against, and a push with no lease behind it adopts "
        "whatever the pull request has moved to and overwrites it. Nothing "
        "was pushed and nothing was discarded. Repair the checkout and the "
        "next tick rebases it again.",
        reason=_state._REASON_UNREADABLE_HEAD,
        # Said once: this refusal is retried by every tick after it, since
        # what clears it is the reading itself rather than a reply.
        once=True,
    )


def _park_unreadable_worktree(ctx: _models._ConflictContext) -> None:
    """Stop a tick whose checkout could not say what it is carrying.

    A status that established nothing names no paths, and so does a tree with
    nothing in it -- so every probe that reports paths alone reads the first
    as the second. What hangs off that answer is whether the commit about to
    be published is the whole of what the worktree holds: taken as clean, a
    checkout carrying uncommitted edits is pushed as a SHA that silently omits
    them, and the reviewer behind it runs on a tree the pull request does not
    have.

    The size gate proves the tree for itself before it freezes an entry, but
    that proof is part of the MEASUREMENT: an install running `DECOMPOSE=off`
    never freezes one, so the push goes out and the later proof can park but
    cannot take it back. So the reading is required here, ahead of the effect,
    on every road that publishes from this checkout or resumes an agent over
    it.
    """
    log.error(
        "issue=#%d resolving_conflict: could not read what its worktree is "
        "carrying; refusing to publish from or resume over a checkout whose "
        "status nobody read",
        ctx.issue.number,
    )
    _park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} nothing could read what this issue's "
        "worktree is carrying, so nothing was pushed from it and no dev "
        "session was resumed over it. A reading that established nothing "
        "names no paths, which is exactly what a clean tree names too -- and "
        "taken as clean, a checkout with uncommitted edits is published as a "
        "commit that silently omits them. Nothing was pushed and nothing was "
        "discarded. Repair the checkout so its status reads, and the next "
        "tick carries on.",
        reason=_state._REASON_UNREADABLE_WORKTREE,
        # Said once: a later tick's own status read is what clears this, so
        # every tick after this one retries it.
        once=True,
    )


def _left_unparked(ctx: _models._ConflictContext) -> None:
    """Drop the park a round handed on to `validating` runs out from under.

    Every road that reaches the tail with an agent behind it has already
    cleared the flags -- the dev resume does it, because it is reacting to a
    human -- and the one road that does not is the settled round, which is
    reached on an issue parked by the very reading it has just taken
    successfully. Left set, `validating` is handed an issue that reads as
    waiting on somebody nobody is waiting for.
    """
    ctx.state.set(_state._AWAITING_HUMAN, False)
    ctx.state.set(_state._PARK_REASON, None)
