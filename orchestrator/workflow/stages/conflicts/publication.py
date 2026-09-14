# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The two ways a rebase attempt ends, and what each publishes.

A clean rebase has three exits and a PROVED clean tree gates all of them,
including the one that pushes nothing. A no-op flip carries the worktree into
`validating` untouched, where the reviewer agent reads the tree directly -- so
an uncommitted edit left by a tick that crashed before its own dirty check
would put the reviewer's vote against content the PR does not have, and the
in_review ready-ping would then advertise that approval to a human merger. A
status nobody could read is that same edit with nothing to name it, so it
refuses too.

What the branch is standing on afterwards is proved rather than assumed, for
one step further on: an unreadable head read as "the base had not moved" hands
the round back to validating without anything having established whether the
rebase left a rewritten commit the pull request never received.

The no-op flip still bumps `conflict_round`. Nothing was resolved, but PyGithub
cannot tell a content conflict from a PR blocked by branch protection or
required reviewers, so without counting the no-op an unmergeable-for-other-
reasons PR would bounce between `in_review` and `resolving_conflict` forever
with the cap never firing.

Real content conflicts go to the dev instead, and the push that follows is
leased against the pre-rebase HEAD: the agent rewrote history from that SHA, so
that is the only remote state the force-push may legitimately replace.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import models as _config_models, settings as config
from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import naming as _naming
from orchestrator.workflow.engine import prompts as _prompts
from orchestrator.workflow.stages.conflicts import (
    evidence as _evidence,
    models as _models,
    outcomes as _outcomes,
    parks as _conflict_parks,
    replay_records as _replay_records,
    resume as _resume,
    state as _state,
    transitions as _transitions,
)
from orchestrator.workflow.stages.implementing import (
    late_push as _late_push,
    late_records as _late_records,
)
from orchestrator.workflow.state import WorkflowLabel

log = logging.getLogger("orchestrator.workflow")


# What a tree this stage could not prove clean is parked as. Both readings are
# the same refusal to an operator -- the checkout may not be handed on -- and
# they are worded apart because what has to be put back differs: uncommitted
# work is removed or committed, while a status nobody could read is a checkout
# to repair.
_DIRTY_TREE_PARK = (
    "{mentions} worktree has {count} uncommitted change(s) after `git rebase "
    "{base_ref}`; refusing to push or hand back to validating with a dirty "
    "tree."
)


_UNREADABLE_TREE_PARK = (
    "{mentions} nothing could read what the worktree is carrying after `git "
    "rebase {base_ref}`, so it cannot be proved clean. A reading that "
    "established nothing names no paths, which is exactly what an empty tree "
    "names too -- and the reviewer this round hands to reads the checkout "
    "directly, so an uncommitted edit waved through here becomes a vote "
    "against content the pull request does not carry. Nothing was pushed and "
    "no round was counted. Repair the checkout so its status reads, and the "
    "next tick rebases it again."
)


_UNREADABLE_HEAD_PARK = (
    "{mentions} `git rebase {base_ref}` reported clean and nothing could then "
    "read the commit the worktree is standing on. Read as \"already up to "
    "date\" the round would go back to validating without anyone knowing "
    "whether the rebase left a rewritten head the pull request never "
    "received -- and the reviewer would vote on the head it already has. "
    "Nothing was pushed and no round was counted. Repair the checkout and the "
    "next tick rebases it again."
)


# Why this stage may not hand a checkout on, spelled as the park records it.
# The two tree readings are told apart the way every other seam tells them
# apart: a list of paths a human removes or commits, against a repository to
# look at, which names no count because naming one would report a failed read
# as an empty tree.
_DIRTY_WORKTREE = "dirty_worktree"


def _publish_clean_rebase(
    ctx: _models._ConflictContext,
    wt: Path,
    replayed: _models._Replayed,
    conflict_round: int,
    pr_number,
) -> None:
    """Dispose of a clean `git rebase <remote>/<base>` outcome.

    Parks on a tree nothing proved clean and on a head nothing could read;
    flips to `validating` without a push when the base had not moved (no-op
    rebase, still counted against the cap); or force-pushes the rebased head
    and flips to `validating`. The caller returns immediately after; every
    exit writes pinned state.

    `replayed` is what the caller read while the branch still stood where it
    did: the head this push is leased against, and the fork point that head's
    contribution was read over. A rebase destroys both, and together they are
    the whole of the evidence a change a human already adjudicated may be
    recognized in the object that replaced it -- which is what keeps the last
    push before the merge button from adjudicating the same change twice.
    """
    spec = ctx.spec
    before_sha = replayed.head
    if _unprovable_tree(ctx, wt):
        return
    after_sha = _verification_probes._head_sha(wt)
    if not after_sha:
        # An unreadable head is not "the base had not moved". Read as one, the
        # no-op flip hands the round back to validating without anything
        # having established whether the rebase left a commit the pull request
        # does not carry -- and no later tick goes back for it, since the
        # branch it comes back to already carries its base.
        log.error(
            "issue=#%d resolving_conflict: could not read the head a clean "
            "`git rebase %s/%s` left; refusing to flip to validating over a "
            "checkout nobody read",
            ctx.issue.number, spec.remote_name, spec.base_branch,
        )
        _conflict_parks._park_conflict(
            ctx,
            _UNREADABLE_HEAD_PARK.format(
                mentions=config.HITL_MENTIONS, base_ref=_base_ref(spec),
            ),
            reason=_state._REASON_UNREADABLE_HEAD,
            # Said once: a later tick's own head read is what clears this, so
            # every tick after this one retries it.
            once=True,
        )
        return
    if after_sha == before_sha:
        _flip_base_up_to_date(ctx, conflict_round, pr_number, after_sha)
        return
    # The other half of the record the caller opened before it rebased, made
    # durable before the gate is entered rather than after: the window it
    # exists for is exactly the one between the replay and the permission the
    # gate's own grant persists.
    _replay_records._records_the_replayed_commit(ctx, replayed, after_sha)
    published = _late_push._publishes(
        _late_records._gate(ctx.gh, spec, ctx.issue, ctx.state, wt),
        _naming._resolve_branch_name(ctx.state, spec, ctx.issue.number),
        _late_records._Entered(
            head=before_sha or "", reconciling=True,
            # The head the rebase left, so a commit landing between that read
            # and the gate's own is refused rather than published in its
            # place under this round's name.
            candidate=after_sha,
            # The round this rebase resolved, handed to the gate for the exit
            # where this caller never reaches the tail: a hold relabels to the
            # adjudication, and the resumed tick would read the published
            # commit as a branch already carrying its base -- the no-op flip,
            # which resolves nothing and stamps no `last_conflict_resolved_at`.
            spends=_transitions._settles_the_held_round(
                "base_rebased_clean", after_sha,
            ),
            # What this replay REPLACED, which nothing past the rebase could
            # recover. Handed over whether or not this issue has an exemption
            # to carry, since only the gate holds the record that would say --
            # and it decides nothing here: a replay that moved a byte
            # fingerprints to some other contribution and is measured like any
            # other candidate.
            rewrite=_evidence._rewritten(
                ctx, wt, replayed, after_sha, pr_number,
            ),
        ),
    )
    if published.held:
        # The gate owns the issue from here -- parked, or handed to the
        # adjudication -- so the hand back to validating is not this tick's.
        ctx.gh.write_pinned_state(ctx.issue, ctx.state)
        return
    if not published.landed:
        _conflict_parks._park_conflict(
            ctx,
            f"{config.HITL_MENTIONS} git push failed after auto-rebasing "
            f"`{spec.remote_name}/{spec.base_branch}`; "
            "see orchestrator logs.",
            reason="push_failed",
        )
        return
    # Pushed branch diff -> hand straight back to validating; the single docs
    # pass runs after final reviewer approval. The replay record goes with it:
    # the commit it explains is on the remote, so nothing is left for a later
    # tick to recover, and this tail's own write carries the drop.
    _replay_records._forgets_the_replay(ctx.state)
    _transitions._hand_resolved_round_to_validating(
        ctx, conflict_round, pr_number,
        outcome="base_rebased_clean", sha=after_sha,
    )


def _base_ref(spec: _config_models.RepoSpec) -> str:
    """The remote-tracking ref this stage rebases onto."""
    return f"{spec.remote_name}/{spec.base_branch}"


def _unprovable_tree(ctx: _models._ConflictContext, wt: Path) -> bool:
    """Refuse a clean-rebase exit over a tree nothing proved clean.

    Asked once, ahead of BOTH clean-rebase exits -- the no-op flip and the
    rebased-head push -- because the no-op is the one that carries the
    worktree into `validating` untouched, where the reviewer agent reads the
    tree directly. An uncommitted edit a crashed tick left behind would put
    that vote against content the pull request does not have, and the
    in_review ready-ping would advertise the approval to a human merger.

    Proved, not merely un-named. A status read that established nothing names
    no paths, and so does a tree with nothing in it: taken as an absence, a
    checkout whose `git status` could not be run at all is handed on as a
    clean one. So the reading has to have HAPPENED and named nothing, which is
    the one question `is_clean` answers.
    """
    tree = _worktree_status._worktree_status(wt)
    if tree.is_clean:
        return False
    base_ref = _base_ref(ctx.spec)
    if tree.readable:
        _conflict_parks._park_conflict(
            ctx,
            _DIRTY_TREE_PARK.format(
                mentions=config.HITL_MENTIONS,
                count=len(tree.paths),
                base_ref=base_ref,
            ),
            reason=_DIRTY_WORKTREE,
        )
        return True
    log.error(
        "issue=#%d resolving_conflict: could not prove the worktree clean "
        "after `git rebase %s`; refusing to push or flip",
        ctx.issue.number, base_ref,
    )
    _conflict_parks._park_conflict(
        ctx,
        _UNREADABLE_TREE_PARK.format(
            mentions=config.HITL_MENTIONS, base_ref=base_ref,
        ),
        reason=_state._REASON_UNREADABLE_WORKTREE,
        once=True,
    )
    return True


def _flip_base_up_to_date(
    ctx: _models._ConflictContext, conflict_round: int, pr_number, after_sha,
) -> None:
    """Hand a no-op base rebase (branch already current) back to `validating`.

    Increments `conflict_round` even though no diff was applied: an unmergeable
    PR blocked purely by branch protection / required reviewers (PyGithub
    cannot tell those from a content conflict) would otherwise loop
    in_review <-> resolving_conflict forever with the cap never firing.
    Counting the no-op against the cap surfaces it within MAX_CONFLICT_ROUNDS
    ticks. Does NOT stamp `last_conflict_resolved_at` -- nothing was resolved.

    The replay record the caller opened goes with it, on this exit's own
    write: a rebase that moved nothing replaced nothing, so the account it
    began describes no replay for any later tick to finish.
    """
    log.info(
        "issue=#%d resolving_conflict: branch already up-to-date with %s/%s",
        ctx.issue.number, ctx.spec.remote_name, ctx.spec.base_branch,
    )
    _replay_records._forgets_the_replay(ctx.state)
    ctx.state.set(_state._REVIEW_ROUND, 0)
    ctx.state.set(_state._CONFLICT_ROUND, conflict_round + 1)
    _transitions._emit_conflict_round_incremented(
        ctx,
        pr_number=int(pr_number),
        new_round=conflict_round + 1,
        outcome="base_up_to_date",
        sha=after_sha,
    )
    _conflict_parks._left_unparked(ctx)
    ctx.gh.set_workflow_label(ctx.issue, WorkflowLabel.VALIDATING)
    ctx.gh.write_pinned_state(ctx.issue, ctx.state)


def _resolve_conflicts_with_agent(
    ctx: _models._ConflictContext,
    conflicted_files,
    before_sha: str,
    conflict_round: int,
) -> None:
    """Resume the dev session to resolve real rebase content conflicts.

    Builds the conflict-resolution prompt from the conflicted files,
    resumes the locked backend, and funnels the result through
    `_post_conflict_resolution_result` (leasing the push against
    `before_sha`). Returns without touching durable state when a live
    pause lands mid-run.
    """
    spec = ctx.spec
    fix_prompt = _prompts._build_conflict_resolution_prompt(
        f"{spec.remote_name}/{spec.base_branch}", conflicted_files,
    )
    run = _resume._run_conflict_resume(ctx, fix_prompt)
    # Live pause applied mid-run: return before
    # `_post_conflict_resolution_result` pushes / relabels / writes pinned
    # state -- the resolved commit stays on the branch until the label is
    # removed.
    if run.paused:
        return
    _outcomes._post_conflict_resolution_result(
        ctx, run, before_sha, conflict_round,
        force_with_lease=before_sha or None,
    )
