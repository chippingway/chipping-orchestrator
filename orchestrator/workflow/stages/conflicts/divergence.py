# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Diverged-worktree admission and commit-pinned recovery publication.

Only an orchestrator-produced stale head or this stage's recorded replay
licenses a force-push over divergence. Recovery carries its original lease
through the size gate, and settles the conflict round only after the push
lands and the checkout has caught up with the base.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git import commands as _git_commands
from orchestrator.git.verification import probes as _verification_probes
from orchestrator.workflow.stages.conflicts import (
    evidence as _evidence,
    guards as _guards,
    models as _models,
    parks as _conflict_parks,
    recovery_guards as _recovery_guards,
    replay_records as _replay_records,
    transitions as _transitions,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_push as _late_push,
    late_records as _late_records,
)

log = logging.getLogger("orchestrator.workflow")

# What a round a recovered push finished is recorded as, in the audit event
# and in the receipt a hold leaves for the tick that resumes behind it.
_RECOVERED_PUSH = "recovered_push"


def _guard_diverged_worktree(
    ctx: _models._ConflictContext, pr, sync: _models._WorktreeSync,
) -> _models._DivergeDecision:
    """Decide the fate of a worktree behind the remote PR head.

    When `behind > 0` the worktree is normally stale or diverged and we refuse
    the force-push, park, and return a parked decision. Two exceptions yield a
    lease pinned to the validated head instead, so the recovered-push router
    can force-publish: a worktree already rebased onto base and ahead of a
    stale orchestrator-produced PR head, and one whose divergence this stage's
    own replay record accounts for. Every other case (including `behind == 0`)
    returns an unparked decision with no lease.

    A REPLAY is why the second exists. A rebase moves the branch off the head
    it replayed, so the pull request stops being an ancestor and the checkout
    comes back ahead of it AND behind it -- the very shape this guard parks. A
    tick that rebased and died before its push therefore reaches here looking
    exactly like a stale checkout, and without an exception the recovery that
    finishes it could never run.
    """
    if sync.behind <= 0:
        return _models._DivergeDecision(parked=False)

    # One exception to the refuse-and-park default: the worktree is already
    # correctly rebased ONTO base, ahead of the PR head, and the "behind"
    # commits are the orchestrator's OWN superseded pre-rebase commits on a
    # head it produced (a rebase a prior run ran but never pushed -- exactly
    # the case the fixing dead-lock router hands us). That is the
    # reconciliation this handler exists for: publish instead of park.
    # `_already_rebased_onto_base` re-fetches base to be sure, and the
    # orchestrator-produced check proves there is no external commit on the PR
    # branch to lose.
    if (
        sync.ahead > 0
        and _guards._pr_head_orchestrator_produced(ctx.state, pr)
        and _guards._already_rebased_onto_base(ctx.spec, sync.worktree)
    ):
        log.info(
            "issue=#%d resolving_conflict: worktree already rebased onto "
            "%s/%s and ahead of a stale orchestrator-produced PR head "
            "(`%s`); force-publishing instead of parking",
            ctx.issue.number, ctx.spec.remote_name, ctx.spec.base_branch,
            pr.head.sha[:8],
        )
        # Pin the upcoming force-push lease to the exact PR head we just
        # validated as orchestrator-produced. A bare `_push_branch` would do a
        # fresh `ls-remote` and lease against whatever SHA is live at push time
        # -- if a foreign push lands on the PR branch between `gh.get_pr()` and
        # the push below, the new SHA would become the lease and the force-push
        # would silently overwrite it. Leasing against the validated SHA
        # refuses any such concurrent update.
        return _models._DivergeDecision(parked=False, publish_lease=pr.head.sha)

    # The second exception, and the one a rebase of an adjudicated commit
    # takes. The record this stage wrote before it replayed names the head it
    # was about to replace, the commit it produced, and the pull request it was
    # made against -- so a remote still standing on that head is one nobody has
    # pushed to since, and the commits this force-push drops are exactly the
    # ones the replay superseded. It proves more than the head recognition
    # above does, which is why it needs no base reading beside it: what makes
    # the overwrite safe is knowing whose commits are being dropped, not where
    # the branch has got to.
    if _evidence._replays_the_publication(ctx, sync.worktree, pr):
        log.info(
            "issue=#%d resolving_conflict: worktree carries the replay this "
            "stage recorded over PR head `%s`; force-publishing instead of "
            "parking",
            ctx.issue.number, pr.head.sha[:8],
        )
        # The pre-rebase head, which is the head the record names and the head
        # the pull request is standing on -- one commit, proved to be both.
        return _models._DivergeDecision(parked=False, publish_lease=pr.head.sha)

    _park_diverged_worktree(ctx, pr, sync)
    return _models._DivergeDecision(parked=True)


def _park_diverged_worktree(
    ctx: _models._ConflictContext, pr, sync: _models._WorktreeSync,
) -> None:
    """Park a stale / diverged worktree: force-pushing the local state would
    clobber the real PR head.

    Said once. This refusal stands in front of the awaiting-human resume, so
    an issue whose branch stays diverged reaches it on every poll -- and the
    thing it asks for is the branch reconciled, which no amount of repeating
    brings closer. Repeated, it buries the notice under copies of itself.
    """
    spec = ctx.spec
    pr_head_short = pr.head.sha[:8]
    _conflict_parks._park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} worktree on `{sync.branch}` is {sync.ahead} "
        f"ahead and {sync.behind} behind `{spec.remote_name}/{sync.branch}` "
        f"(PR head `{pr_head_short}`); refusing to rebase a stale "
        "or diverged branch -- force-pushing the local state would "
        "clobber the real PR head. Manual intervention needed.",
        reason="diverged_branch",
        once=True,
    )


def _push_recovered_commits(
    ctx: _models._ConflictContext,
    sync: _models._WorktreeSync,
    conflict_round: int,
    pr_number,
    publish_lease: str | None,
) -> bool:
    """Push crash-recovered commits ahead of the remote PR head.

    Measured first, like every other push onto a pull request the remote
    already carries. A crash between a commit and the gate is exactly the
    window this recovery exists for, so the commits it finds are the ones
    least likely ever to have been read -- publishing them on the strength of
    "an earlier tick meant to" is the unmeasured publication the gate exists
    to stop.

    Pinned to the head the ahead/behind comparison was TAKEN against, which
    the caller carries here rather than leaving the gate to read the pull
    request for itself. "Ahead and not behind" is a claim about one commit,
    and it is the whole of what licenses this push: a foreign push landing
    between that reading and this one would otherwise become the lease, and
    the recovered commits would force-overwrite it having been proved against
    the head it used to be on. The diverged guard's own lease outranks it on
    the one road that has one -- there the pull request was READ and
    validated as orchestrator-produced, which is a stronger claim about the
    same fact -- and where neither names a head this refuses rather than
    publishing under a lease git would take for itself.

    The rewrite it hands the gate is READ rather than taken: the commits it
    finds are whatever an earlier tick left, and no probe run here says which
    -- a replay that tick made, a resolution its agent authored, or unpushed
    fix commits the `fixing` drift reroute sent over, on base as readily as
    behind it, since that is one of the two shapes that reroute fires on. So
    what is handed over is the account a replay wrote about ITSELF, and only
    where it is about this commit and this lease. Everything else presents
    nothing and is measured, the ordinary cumulative gate being what a change
    nobody adjudicated is owed.

    Returns True when the tick is fully handled (caller returns): a dirty
    tree, an unpinnable push, or a failed push parks, and a recovered push
    that leaves HEAD on base flips straight to `validating`. Returns False --
    continue to the base rebase -- when the push landed but the worktree is
    still behind base (the fixing dead-lock reroute lands unpushed fix
    commits here, NOT a rebase, so the combined push+rebase round is owned by
    the rebase path).
    """
    wt = sync.worktree
    lease = publish_lease or sync.fetched_tip
    if _recovery_guards._parked_dirty_recovery(ctx, wt) or _recovery_guards._parked_unpinnable_recovery(
        ctx, sync, lease,
    ):
        return True
    log.info(
        "issue=#%d resolving_conflict: pushing %d recovered commit(s) "
        "ahead of %s/%s before attempting base rebase",
        ctx.issue.number, sync.ahead, ctx.spec.remote_name, sync.branch,
    )
    # Probe whether the worktree is still behind base, BEFORE the push rather
    # than after it. The reading is the same either way -- pushing moves the
    # remote, not this checkout's HEAD or the base ref it is counted against
    # -- and taken first it says which round this push would complete, which
    # is what a hold has to be told before it relabels.
    #
    # A branch still behind base has not finished a round, and two shapes
    # reach here. Crash recovery carries a rebase a prior tick ran and never
    # published: HEAD already contains base, the rebase behind this push
    # would be a no-op, and the flip to validating is all that is left. The
    # `fixing` drift router (`_reconcile_parked_fixing`) reroutes a
    # `push_failed` park here carrying UNPUSHED FIX COMMITS on a stale base:
    # those are not a rebase, so the push leaves the branch behind base
    # still. Flipping to validating there publishes a still-behind pull
    # request and spends a `conflict_round` on a rebase that never ran --
    # and under a low `MAX_CONFLICT_ROUNDS` the cap can block the real
    # rebase pass outright. So behind base falls through to the rebase path,
    # which owns the bookkeeping (conflict_round bump, event emit, label
    # flip) for the combined push+rebase round.
    still_behind = _still_behind_base(wt, _base_ref(ctx.spec))
    recovered_sha = _verification_probes._head_sha(wt)
    if _recovery_guards._parked_unnameable_push(ctx, sync, recovered_sha):
        return True
    published = _late_push._publishes(
        _late_records._gate(ctx.gh, ctx.spec, ctx.issue, ctx.state, wt),
        sync.branch,
        _late_gate_models._Entered(
            head=lease, reconciling=True,
            # The round this push would complete, handed to the gate for the
            # exit where this caller never reaches the tail: a hold relabels
            # to the adjudication, and the resumed tick reads the published
            # commit as a branch already standing on its base -- the no-op
            # flip, which resolves nothing and stamps no
            # `last_conflict_resolved_at`. Nothing is owed where the rebase
            # behind this one owns the round instead.
            spends=_recovered_round(still_behind, recovered_sha),
            # The commit this push is about, named on EVERY road out of here
            # rather than only the one that finishes a round. The gate proves
            # the checkout for itself, so a commit landing between this
            # owner's reading and that one is a different candidate --
            # measured, pushed, and receipted under a lease proved against the
            # head the branch used to be on. Named, the two are one decision
            # and a moved checkout refuses instead. Only what the push OWES
            # turns on the behind-base reading beside it.
            candidate=recovered_sha,
            # The replay this push is finishing, where a record says that is
            # what it is. Read rather than probed, since nothing about the
            # branch tells a replay from work somebody wrote.
            rewrite=_evidence._recovered(
                ctx, wt, lease, recovered_sha, pr_number,
            ),
        ),
    )
    if not published.landed:
        _refused_the_recovery(ctx, published.held)
        return True
    if still_behind != 0:
        log.info(
            "issue=#%d resolving_conflict: pushed %d recovered commit(s) "
            "but worktree still %d behind %s; continuing with base rebase",
            ctx.issue.number, sync.ahead, still_behind, _base_ref(ctx.spec),
        )
        return False
    # Pushed branch diff -> hand straight back to validating; the single docs
    # pass runs after final reviewer approval. A replay record goes with it:
    # the commit it explains is on the remote, and this tail's own write
    # carries the drop.
    _replay_records._forgets_the_replay(ctx.state)
    _transitions._hand_resolved_round_to_validating(
        ctx, conflict_round, pr_number,
        outcome=_RECOVERED_PUSH, sha=recovered_sha,
    )
    return True


def _refused_the_recovery(
    ctx: _models._ConflictContext, held: bool,
) -> None:
    """What a recovered push that did not reach the remote leaves behind.

    Held is the gate having taken the issue -- parked, or handed to the
    adjudication -- so a state write is the whole of what this caller still
    owes, and neither the rebase behind this push nor the hand back to
    `validating` is its tick's to make. Anything else is a push that was
    allowed and then failed, which parks with the commits still on the branch
    for a later push to carry.
    """
    if held:
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    _conflict_parks._park_conflict(
        ctx,
        f"{config.HITL_MENTIONS} git push of recovered conflict "
        "resolution failed; see orchestrator logs.",
        reason="push_failed",
    )


def _base_ref(spec: _config_models.RepoSpec) -> str:
    """The remote-tracking ref the behind-base probe counts against."""
    return f"{spec.remote_name}/{spec.base_branch}"


def _recovered_round(still_behind: int, recovered_sha: str):
    """The round a held recovered push owes, or nothing where it owes none.

    Only the push that FINISHES a round leaves a receipt. One that lands with
    the branch still behind base is a preamble: the rebase behind it owns the
    round, and it leaves its own receipt when the gate holds it. Recording one
    here too would have the resumed tick close a round the rebase has not run
    yet -- and it is the resumed tick's only evidence, since the settlement
    publishes the commit and leaves it reading a branch already standing on
    its base, which is the no-op flip that resolves nothing.
    """
    if still_behind:
        return _late_gate_models._SPENDS_NOTHING
    return _transitions._settles_the_held_round(_RECOVERED_PUSH, recovered_sha)


def _still_behind_base(wt: Path, base_ref: str) -> int:
    """Count commits on `base_ref` missing from HEAD, failing closed to 1.

    A probe failure (stale base ref, transient git error) reports "behind" so
    the caller falls through to the rebase path: `_rebase_base_into_worktree`
    no-ops when HEAD already contains base and re-fetches to self-correct a
    stale ref, which is the safer default than a blind fast-path to validating.
    """
    behind_base_r = _git_commands._git(
        "rev-list", "--count", f"HEAD..{base_ref}", cwd=wt,
    )
    if behind_base_r.returncode != 0:
        return 1
    try:
        return int((behind_base_r.stdout or "").strip() or 0)
    except ValueError:
        return 1
