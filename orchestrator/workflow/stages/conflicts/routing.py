# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One reading of the branch, and everything decided behind it.

Every road out of this stage either publishes from the checkout or hands it
on, and neither is safe over a branch nobody has placed against its remote. So
the tick begins by restoring the worktree, re-fetching the PR branch's remote
tip, and comparing the two -- and every decision past that point is made with
the answer in hand, the dev resumes included.

What the comparison can report is handled in the one order that is safe. A
round a settlement already published is finished first, since nothing else
clears its receipt and it is owed whatever else the branch carries. A branch
BEHIND its remote is refused: force-pushing over it would drop the commits
that moved it, and handing it on would show a reviewer a head the pull request
does not have. A human's edit or reply is answered next -- but not over a
branch AHEAD of its remote, which carries an unpublished commit that every
publication behind a resume would be leased against and the size gate would
then refuse as somebody else's movement. So an ahead branch ships its
recovered commits instead, and the human waits a tick. A recovered push that
leaves the branch still behind base falls through to the rebase rather than
ending the tick, so the two land as one round.

The `MAX_CONFLICT_ROUNDS` cap stands in front of the REBASE and nothing else.
It guards a loop that genuinely cannot converge on its own -- an unmergeable
PR that no amount of rebasing fixes would otherwise spawn a dev run every tick
-- so what it refuses is another ATTEMPT. Everything above it is work already
done that this stage still owes an effect for, and refusing those does not end
the loop but strands them: nothing else pays a receipt, publishes a commit an
earlier tick made, or answers a person.

A park is not always a person, either. A reading that DID NOT HAPPEN -- a ref
nothing resolved, a status nothing read, a head nothing could name -- leaves a
park no reply can answer, so the tick that finds one standing retries the
reading rather than waiting on somebody, and the refusal is announced once so
those retries do not bury it.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import settings as config
from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import drift as _drift
from orchestrator.workflow.stages.conflicts import (
    divergence as _divergence,
    guards as _guards,
    models as _models,
    parks as _conflict_parks,
    rebase as _rebase,
    resume as _resume,
    state as _state,
    transitions as _transitions,
)

log = logging.getLogger("orchestrator.workflow")


def _drive_conflict_rebase(
    ctx: _models._ConflictContext, pr, pr_number,
) -> None:
    """Prepare the worktree, reconcile what it carries, and rebase.

    Every road out of this stage runs behind one reading -- the branch fetched
    and the checkout compared to it -- because every road either publishes
    from that checkout or hands it on, and neither is safe over a branch
    nobody placed. That includes the awaiting-human resume, which is asked
    among the reconciliations rather than in front of them: what it starts is
    an agent whose commit this stage force-pushes, so a reply answered over a
    checkout the remote has moved past drops the commits that moved it.

    The `MAX_CONFLICT_ROUNDS` cap stands in front of the REBASE and nothing
    else, because the rebase and the dev run behind it are the attempt it
    exists to refuse. Everything the reconciliation does is work already done
    that this stage still owes an effect for -- a round a settlement
    published, commits an earlier tick committed and never pushed, a human
    whose reply or edit is waiting -- and refusing those does not end the loop,
    it strands them: nothing else clears a receipt, publishes an unpushed
    commit, or answers a person.
    """
    conflict_round = int(ctx.state.get(_state._CONFLICT_ROUND) or 0)
    wt = _prepare_conflict_worktree(ctx, pr, pr_number, conflict_round)
    if wt is None:
        return
    if _capped(ctx, conflict_round):
        return

    _rebase._rebase_and_dispose(ctx, pr_number, conflict_round, wt)


def _prepare_conflict_worktree(
    ctx: _models._ConflictContext, pr, pr_number, conflict_round: int,
) -> Path | None:
    """Restore the worktree, refresh remote refs, and reconcile a diverged or
    crash-recovered branch before the base rebase.

    Returns the worktree to rebase, or ``None`` when the tick is fully handled
    (a fetch failure / diverged-branch / cap / dirty park, a settled round
    handed back to `validating`, or a crash-recovery push that flipped
    straight to `validating`) and the caller must return.
    """
    wt = _guards._ensure_conflict_worktree(ctx)
    branch = _naming._resolve_branch_name(
        ctx.state, ctx.spec, ctx.issue.number,
    )

    # Refresh `<remote>/<branch>` (the PR branch's remote tip) via the same
    # hardened authenticated path `_push_branch` uses. A stale local ref would
    # mis-classify a real "remote moved out from under us" as in-sync.
    if not _rebase._fetch_pr_branch(ctx, wt, branch):
        return None

    # Check the worktree against the freshly-fetched remote PR head. Three
    # shapes: in sync `(0, 0)` proceeds to the base rebase; HEAD ahead
    # `(>0, 0)` is the crash-recovery case (a prior tick committed a
    # resolution but crashed before the push / post-push state write landed);
    # anything `behind > 0` is a stale or diverged worktree we refuse to
    # force-push over.
    # One reading, so the counts and the head they were taken against name
    # the same commit: the recovered push below is pinned to the head this
    # comparison proved the branch was ahead of, and a ref something moved
    # between two readings would leave it proved against one and pinned to
    # another.
    divergence = _publication_probes._branch_divergence(ctx.spec, wt, branch)
    if not divergence.readable:
        _unreadable_divergence(ctx, branch)
        return None
    sync = _models._WorktreeSync(
        wt, branch, divergence.ahead, divergence.behind,
        fetched_tip=divergence.tip,
    )
    if _reconciled_before_the_rebase(ctx, pr, sync, conflict_round, pr_number):
        return None

    # In sync (or fell through after a recovered push to reconcile a stale
    # base). Refresh `<remote>/<base>` so the upcoming rebase sees the current
    # base tip.
    if not _rebase._fetch_base_ref(ctx, wt):
        return None
    return wt


def _unreadable_divergence(
    ctx: _models._ConflictContext, branch: str,
) -> None:
    """Park a tick that could not read where its worktree stands, and stop.

    A reading that did not happen is not an in-sync branch, and only one of
    the two may be rebased over: taken for "in sync" a stale checkout is
    rebased, spawned over, and force-pushed on evidence nobody took. The
    fetch a step earlier succeeded, so this is a ref nothing could resolve or
    a comparison git refused -- either way the branch is left exactly as it
    is and the next tick reads it again.
    """
    spec = ctx.spec
    remote_ref = f"{spec.remote_name}/{branch}"
    log.error(
        "issue=#%d resolving_conflict could not read how far its worktree "
        "stands from %s; refusing to rebase or push over a branch nothing "
        "compared", ctx.issue.number, remote_ref,
    )
    _conflict_parks._park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} how far this issue's worktree stands from "
        f"`{remote_ref}` could not be read, so no rebase was run and nothing "
        "was pushed: a reading that did not happen answers the same as a "
        "branch in sync, and acting on it would force-push a stale worktree "
        "over the real PR head. See orchestrator logs; the next tick fetches "
        "and reads it again.",
        reason=_state._REASON_UNREADABLE_DIVERGENCE,
        # Said once. A settled round is retried through this reading every
        # tick, so a ref that goes on refusing to resolve would bury the
        # notice an operator has to act on under a fresh copy of itself.
        once=True,
    )


def _reconciled_before_the_rebase(
    ctx: _models._ConflictContext,
    pr,
    sync: _models._WorktreeSync,
    conflict_round: int,
    pr_number,
) -> bool:
    """Whether this tick is finished before the base rebase may run.

    Three things the branch can be carrying, and none of them is a rebase. A
    round the size gate held and an adjudication has since published, where
    all that is left is the tail its own tick never reached -- asked before
    the rebase, which would read the published commit as a branch already
    standing on its base and flip it as a no-op that resolved nothing. Behind
    or diverged from the remote PR head, where it is refused rather than
    force-pushed over. Ahead of the remote, where it carries commits a crashed
    tick never pushed.

    The published round goes first, and the two things it now precedes were
    each their own way to lose it. The `MAX_CONFLICT_ROUNDS` cap refuses
    another ATTEMPT -- a push of recovered commits, a rebase, a dev run over
    the conflicted files -- and a round already finished and published is none
    of those: the commit is on the pull request, and only the counter and the
    label are owed. And a resume that commits writes the one receipt slot
    itself. Refused by either, the receipt stands with nothing left to clear
    it, no round is ever counted for a push that really happened, and the
    issue waits on a `validating` handoff no later tick makes.

    Nothing is risked by reading it first, because it publishes nothing and
    refuses every reading it cannot hand a reviewer: in sync with the remote
    AND standing on the commit the receipt names. It does NOT outrank the
    divergence guard behind it -- a branch behind its remote is one the
    reviewer would be spawned over as it stands, so what a `diverged_branch`
    park costs there is one round's telemetry until a human reconciles, and
    what waving it through costs is a verdict taken over a commit the pull
    request has moved past.

    Past it the order is the one each answer rests on: the divergence guard is
    what says the ahead/behind reading may be acted on at all, and it is where
    the EXCEPTIONAL lease comes from -- the one road that reads and validates
    the pull request's own head. Every other recovered push is pinned to the
    tip the comparison was taken against, which the sync record carries beside
    the counts, and one with neither refuses rather than letting git take its
    own reading at push time.

    The two dev resumes sit between the guard and the cap. Behind the guard
    because what either starts is an agent whose commit this stage
    force-pushes: over a checkout the remote has moved past, that push drops
    whatever moved it, and no lease catches it -- the tip the push is pinned
    to is the one the resume READ, so git has nothing to refuse. Neither a
    reply nor a body edit is what a diverged branch needs; the park it takes
    asks for the branch to be reconciled, which is the one thing that makes
    either resume safe again. Ahead of the cap because a reply IS the
    documented way off that park, and a comment is exactly what it invites.
    """
    if _transitions._finished_settled_round(
        ctx, sync, conflict_round, pr_number,
    ):
        return True
    guard = _divergence._guard_diverged_worktree(ctx, pr, sync)
    if guard.parked:
        return True
    if _resumes_the_dev(ctx, pr, pr_number, conflict_round, sync):
        return True
    return sync.ahead > 0 and _divergence._push_recovered_commits(
        ctx, sync, conflict_round, pr_number, guard.publish_lease,
    )


def _resumes_the_dev(
    ctx: _models._ConflictContext,
    pr,
    pr_number,
    conflict_round: int,
    sync: _models._WorktreeSync,
) -> bool:
    """Whether this tick belongs to a human rather than to a rebase.

    Two ways it can. A human edited the issue body while the dev was resolving
    conflicts, and the dev has to see the new body before deciding whether its
    in-flight resolution still applies -- a pushed answer hands back to
    `validating`, and a bare acknowledgement stays here without parking so a
    harmless clarification does not stall the rebase. Or the issue is parked
    awaiting a human and a reply arrived, which resumes on the reply text.

    The pull request rides along because both resumes need the head it is
    standing on NOW: the agent is out for minutes, and a head read after it
    returns is whatever landed in the meantime.

    What this owner decides is whether either may run at all.

    Two shapes of checkout are answered before any human is, because no reply
    can put either right and resuming over one publishes from it.

    A branch the remote has moved PAST needs reconciling rather than
    resolving: resuming over it force-pushes a checkout that never had what
    moved it, and the guard above parks for exactly that.

    A branch AHEAD of the remote carries a commit an earlier tick made and
    never published. What that costs turns on which head a resume's
    publication is leased against, so it is decided per resume rather than
    here -- see `_resumed`.

    A tree nothing could READ stops both. What either resume ends in is a
    publication from this checkout, and the probe that guards one reports the
    paths a status named -- so a reading that established nothing answers
    exactly as a clean tree does, and the commit goes out silently omitting
    whatever was uncommitted beside it. The size gate proves the tree itself,
    but only as part of a measurement `DECOMPOSE=off` never takes. A tree that
    is merely DIRTY is not this: that is the park a reply exists to unstick,
    and the dev is resumed to clean it.

    Which of the two a human actually asked for is `_resumed` below.
    """
    if not _worktree_status._worktree_status(sync.worktree).readable:
        _conflict_parks._park_unreadable_worktree(ctx)
        return True
    return _resumed(ctx, pr, pr_number, conflict_round, sync)


def _resumed(
    ctx: _models._ConflictContext,
    pr,
    pr_number,
    conflict_round: int,
    sync: _models._WorktreeSync,
) -> bool:
    """Whether a human had something to say, and the dev was resumed on it.

    The edit is asked first because it changes what "resolved" means, and the
    reply may be an answer to a question the edit has already overtaken.

    A checkout AHEAD of its remote stops the edit and not the reply, and the
    difference is which head each leases its publication against. The body
    edit leases against the head the round began at, read off this checkout --
    on an ahead branch a local commit the remote has never seen, which the
    size gate then refuses as somebody else's movement, with the edit already
    consumed and nothing left to detect it again. The reply's publication
    freezes the pull request's OWN head instead, read before the agent runs,
    so an unpublished commit under it changes nothing: the resolution goes out
    carrying it. Stopping that one too would push a commit the reply was never
    fed to as though it were finished work -- an agent a timeout parked can
    leave a clean commit behind, and the whole point of the reply is to say
    what to do about it.

    So the edit FALLS THROUGH on an ahead checkout rather than ending the
    tick, and that is not a detail. The drift hash covers the thread as well
    as the body, so a reply on a park moves it too -- every reply reaches this
    owner looking like an edit. Returning there would drop a parked issue
    straight into the recovered push, shipping the pre-reply commit with the
    reply neither fed to anybody nor consumed. Fallen through, the reply is
    answered as the reply it is, and a body edit that really did move waits
    for the branch to be in sync, its hash still unconsumed.

    A round a settlement already published is the one thing that does stop the
    reply, and only while the recovered push below can pay it: they share the
    one receipt slot, and that push is what writes it.

    A transient park is not a human waiting. What a reading that DID NOT
    HAPPEN needs is the reading again, so the tick carries on with its
    ordinary work rather than consuming itself on somebody who has nothing to
    say -- which is what would otherwise leave a repaired checkout parked for
    good, with the thing the notice asked for already done. That reading is
    only ever found standing where nobody WAS waiting, because a transient
    refusal taken over a human's park leaves the human's reason in place, and
    it is the same predicate on both ends that keeps the two agreeing.
    """
    edited = _drift._detect_user_content_change(ctx.gh, ctx.issue, ctx.state)
    if edited is not None and sync.ahead <= 0:
        _resume._resume_on_user_content_change(ctx, pr_number, edited)
        return True
    if not _conflict_parks._waits_on_a_human(ctx.state):
        return False
    if sync.ahead > 0 and _transitions._settled_round_owed(ctx.state)[0]:
        return False
    _resume._resume_awaiting_human(ctx, conflict_round, pr)
    return True


def _capped(ctx: _models._ConflictContext, conflict_round: int) -> bool:
    """Park a branch that has spent every round the cap allows it.

    The loop this ends genuinely cannot converge on its own: a pull request no
    amount of rebasing makes mergeable would spawn a dev run every tick
    forever. Escaping it is a human's move -- relabel off
    `workflow:resolving_conflict`, or comment, which the awaiting-human resume
    picks up.
    """
    if conflict_round < config.MAX_CONFLICT_ROUNDS:
        return False
    _conflict_parks._park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} auto-conflict-resolution still failing "
        f"after {conflict_round} round(s) "
        f"(`MAX_CONFLICT_ROUNDS={config.MAX_CONFLICT_ROUNDS}`); manual "
        "intervention needed.",
        reason="conflict_cap",
    )
    return True
