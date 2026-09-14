# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the checkout was holding before a round could open over it.

The probes a discussion tick takes ahead of everything else, split from the
round they run in front of because the reader is `settlement` rather than the
spawn: what a tree holding work or a tip off the anchor is WORTH -- a
publication, a report, or a hold -- is decided there, and nothing here writes,
restores, or removes so much as a directory.

Running ahead of the round is the whole of why they are their own step.
Preparing a checkout force-removes a dirty tree that carries no commits, so the
restorer in `run` is exactly the step that would destroy the only evidence an
operator has of a round that died before it could park on what it wrote. Read
here first, that tree is preserved instead of recreated over.

Between themselves the two reads are ordered, and the order is load-bearing.
The tree is asked first, because the anchor comparison's own `HEAD` read can
fail: unresolvable, it comes back empty and compares unequal to every anchor
there is, so a checkout nothing has established anything about would answer "a
round committed here" -- and a publication is what follows that answer. A tree
`git status` could not report on is the shape a broken checkout really takes,
and holding on it is what keeps the comparison from being asked of it at all.

What a moved anchor MEANS is the caller's question, not this owner's. The tip
being off the anchor says only that the branch is no longer where this stage's
last round opened it, never who put the commit there. The anchor it is measured
against is written by `run` before the spawn precisely so a round that ended
with no disposition of its own is still classifiable a tick later.
"""
from __future__ import annotations

from orchestrator.git.verification import probes as _verification_probes, status as _worktree_status
from orchestrator.git.worktrees import (
    paths as _worktree_paths,
    recovery as _worktree_recovery,
)
from orchestrator.workflow.stages.discussion import models as _models, state as _state

# What a checkout the round is free to open over reports: read, and holding
# nothing. It is also the answer for a directory that is not there at all --
# nothing to preserve, and no probe that could have failed to say so -- and the
# reading a caller hands the blocked-resume park when what blocks it is a
# commit rather than anything in the tree.
_CLEAN_TREE = _worktree_status._WorktreeStatus(readable=True)

# What a checkout that could not answer for itself reports, whichever of
# the two reads failed: a tree `git status` could not report on and a
# `HEAD` that would not resolve are both checkouts nothing here has
# established anything about, and the callers hold on either.
_UNREADABLE_TREE = _worktree_status._WorktreeStatus(readable=False)


def _stranded_worktree_state(
    run: _models._DiscussionRun,
) -> _worktree_status._WorktreeStatus:
    """What the checkout was holding before this round could open, if anything.

    Every park this stage writes suppresses the next tick, so work waiting in
    the tree at the top of a discussion tick came either from a round that died
    before it could park on what it wrote, or from the stage the issue was
    relabeled out of. Reading it here -- ahead of the `_ensure_worktree` that
    would force-remove exactly that tree -- is what lets the caller preserve it
    instead of recreating over it.

    The STATUS form of the read rather than the path list, because what follows
    a clean answer is destructive. The list form maps its own failure to "no
    paths", which is exactly what a clean tree reports, so a `git status` that
    could not run -- a corrupt index, a half-removed directory -- would read as
    a tree with nothing in it worth keeping and be force-removed before an
    operator ever saw why it failed. A tree nothing proved empty is not empty,
    and the post-round checks lean on this one having proved it.

    It is asked BEFORE the anchor comparison beside it for the same reason. An
    unresolvable `HEAD` comes back as the empty string and compares unequal to
    every anchor there is, so that comparison read on an unproven checkout
    answers "a round committed here" -- and what follows that answer is a
    publication. A checkout `git status` could not report on is the shape a
    broken one really takes, and holding it here is what keeps the comparison
    from being asked of it at all.
    """
    worktree = _worktree_paths._worktree_path(run.spec, run.issue.number)
    if not worktree.exists():
        return _CLEAN_TREE
    return _worktree_status._worktree_status(worktree)


def _round_anchor_moved(run: _models._DiscussionRun) -> bool | None:
    """True when the checkout no longer sits where the last round opened it.

    The anchor is what makes this answerable: it is written before the spawn
    and outlives every park, so what a moved tip MEANS is decided by the
    caller. On an issue this stage does not have parked it is a round withheld
    by a mid-run pause or cut short by a crash, and the movement is the commit
    it left. On a parked one the round did reach a disposition, and the
    movement is somebody having written on the branch since -- the same
    violation, minus the question of who. HEAD is compared against the anchor
    rather than against the base, so a branch that already carried commits when
    the issue was relabeled here stays innocent either way.

    A missing checkout falls back to the branch tip, for the same reason the
    read-only relabel guard consults the branch at all: a directory can be
    removed while the local branch survives carrying the commits, and
    `_ensure_worktree` would restore it under the next round as that round's
    own baseline. It is the tip of the branch the round RECORDED that is read,
    and it is compared rather than measured against base -- an issue relabeled
    here from a PR stage has a branch ahead of base whatever this stage did, and
    an issue pinned to a legacy branch has a slug-namespaced ref beside it whose
    unchanged tip says nothing about where the round actually ran.

    A `HEAD` that could not be read is neither, which is why the answer has a
    third value. It comes back empty, and empty compares unequal to every
    anchor there is -- so read as a move it would put the commit the branch
    already carried onto a pull request in this stage's name, attributed to a
    round that wrote nothing; read as a match it would open a round in a
    checkout nothing has established anything about, recreating it over
    whatever is there. `None` says so, and the caller holds.
    """
    anchor = run.state.get(_state._ROUND_SHA)
    if not anchor:
        return False
    worktree = _worktree_paths._worktree_path(run.spec, run.issue.number)
    if not worktree.exists():
        return _recorded_branch_moved(run, str(anchor))
    head = _verification_probes._head_sha(worktree)
    if not head:
        return None
    return head != str(anchor)


def _recorded_branch_moved(run: _models._DiscussionRun, anchor: str) -> bool:
    """True when the branch the round opened on no longer sits at `anchor`.

    A branch the anchor does not name is not this round's, and a branch that
    no longer exists carries nothing to attribute, so both read as "no commit".
    """
    branch = run.state.get(_state._ROUND_BRANCH)
    if not branch:
        return False
    branch_tip = _worktree_recovery._branch_tip_sha(run.spec, str(branch))
    return bool(branch_tip) and branch_tip != anchor
