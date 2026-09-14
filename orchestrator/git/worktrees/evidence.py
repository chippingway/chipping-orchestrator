# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tri-state checkout identity and cleanliness evidence.

A reclaim must prove that this is the issue's own checkout before interpreting
what it carries. Dirty, ignored, foreign, and unreadable trees remain distinct
answers so deletion never mistakes an unasked question for an empty tree.
Commit tips, checkout activity, and complete listings live on sibling owners."""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.verification import status as _worktree_status
from orchestrator.git.worktrees import (
    evidence_reads as _evidence_reads,
    naming as _naming,
    probes,
    tip_evidence as _tip_evidence,
)
from orchestrator.git.worktrees.models import ProbeAnswer

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a read that could not be taken reports
# where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")


def _clean_worktree(worktree: Path) -> ProbeAnswer:
    """Whether this checkout PROVED it is carrying nothing loose.

    Read through the verification probe rather than a `status` of its own,
    because that owner is where the ways a clean answer can be arranged are
    already handled: the tree is named on the command line so per-worktree
    `core.worktree` cannot redirect the read, untracked files and submodules
    are asked for explicitly so local config cannot hide them, the report is
    NUL-delimited so a path cannot be read as rename syntax, and the index is
    asked whether it has been told to stop comparing entries at all.

    Its `readable` flag is what separates the two negatives here. A tree
    whose status could not be taken -- and a tree whose index carries a
    suppressed entry, which that owner reports the same way -- is
    `UNREADABLE`, never `REFUTED`: nothing was established about what the
    checkout holds, and a reclamation that read it as merely dirty would go
    on to say so as though somebody had looked.

    A checkout the read cannot reach is answered the same way rather than
    raised over, and the boundary is total because the ways it fails are not
    all of one kind. The scan named the directory some moments earlier and an
    agent owns what is under it, so by now the path can be gone -- which fails
    the spawn with an `OSError` -- or be a symlink loop, which fails in the
    `Path.resolve` behind the `--work-tree` argument and fails as a
    `RuntimeError` on Python 3.12 while merely coming back unchanged on 3.13.
    A probe whose contract is three answers may not have a fourth: an
    exception out of one candidate's tree ends the pass for every other
    candidate in it, which is the one way an unreadable checkout can cost more
    than the artifact it is about.
    """
    try:
        status = _worktree_status._worktree_status(worktree)
    except Exception:
        log.warning(
            "the checkout %s could not be reached", worktree, exc_info=True,
        )
        return ProbeAnswer.UNREADABLE
    if not status.readable:
        log.debug("the checkout %s would not report its status", worktree)
        return ProbeAnswer.UNREADABLE
    if status.paths:
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _nothing_ignored(worktree: Path) -> ProbeAnswer:
    """Whether this checkout PROVED it is hiding nothing under its own rules.

    The half of "carrying nothing" that `_clean_worktree` does not answer, and
    the one that only a caller about to delete the tree has to ask. A file the
    repository's ignore rules cover is invisible to every status a publication
    takes and to git's own refusal to remove a dirty worktree, so without this
    the whole proof that a checkout may go rests on a reading that was never
    about those files.

    `REFUTED` names them rather than merely counting them, in the log: what an
    operator does about a retention here is look at what is there and decide,
    and "something is hidden in that tree" sends them through the whole of it.

    Total and tri-state like the read beside it, and for the same reasons. The
    scan named the directory some moments earlier and an agent owns what is
    under it, so the path can be gone by now or be a symlink loop -- and a
    probe whose contract is three answers may not have a fourth.
    """
    try:
        hidden = _worktree_status._ignored_paths(worktree)
    except Exception:
        log.warning(
            "the checkout %s could not be reached", worktree, exc_info=True,
        )
        return ProbeAnswer.UNREADABLE
    if hidden is None:
        log.debug("the checkout %s would not report what it hides", worktree)
        return ProbeAnswer.UNREADABLE
    if hidden:
        log.info(
            "the checkout %s is hiding %s under its own ignore rules",
            worktree, ", ".join(hidden),
        )
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _shared_repository(spec: _config_models.RepoSpec, worktree: Path) -> ProbeAnswer:
    """Whether this checkout is a worktree of the configured clone.

    A directory sitting at the path this issue's checkout belongs at is not
    the checkout: an agent can run `git init` in it, an operator can park an
    unrelated clone there, and a reclaim that read the path as the identity
    would take a repository this orchestrator never created. What answers is
    the store the two share -- a linked worktree keeps its own git directory
    and registers it under the parent's, so the common directory is the one
    spelling that comes back equal for a checkout and the clone that made it.
    """
    checkout_dir = probes._checkout_clone(worktree)
    clone_dir = probes._checkout_clone(spec.target_root)
    if checkout_dir is None or clone_dir is None:
        return ProbeAnswer.UNREADABLE
    if checkout_dir != clone_dir:
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _head_ref(worktree: Path) -> tuple[ProbeAnswer, str]:
    """Whether this checkout's HEAD is on a branch, and which one.

    The pair rather than either half alone, because one read answers two
    questions its callers ask separately: whether the tree belongs to this
    issue at all, and -- once it does -- which branch to ask the remote and
    GitHub about the commit under it. A caller that only ever got the verdict
    would have to read HEAD a second time to learn the name.

    A detached HEAD is `REFUTED` rather than unreadable: `symbolic-ref
    --quiet` spells it as the plain no it is, and every checkout the issue
    creators make is on a branch. What made it detached is somebody else's
    doing, and a commit sitting on no branch is exactly the work a reclaim
    must not take.

    The name comes back stripped of `refs/heads/`, which is how every
    derivation in ``paths`` spells a branch, so it can be compared against
    them and handed to a lookup without either side adjusting it.
    """
    head = _evidence_reads._hardened_read(worktree, "symbolic-ref", "--quiet", _tip_evidence._HEAD)
    if head is None:
        return ProbeAnswer.UNREADABLE, ""
    if head.returncode == _tip_evidence._GIT_NEGATIVE:
        return ProbeAnswer.REFUTED, ""
    named = (head.stdout or "").strip()
    if head.returncode != 0 or not named.startswith(_tip_evidence._LOCAL_REF_PREFIX):
        log.debug(
            "could not read the HEAD of %s: %s",
            worktree, (head.stderr or "").strip(),
        )
        return ProbeAnswer.UNREADABLE, ""
    return ProbeAnswer.CONFIRMED, named[len(_tip_evidence._LOCAL_REF_PREFIX):]


def _head_is_own_branch(
    spec: _config_models.RepoSpec, issue_number: int, worktree: Path,
) -> ProbeAnswer:
    """Whether this checkout's HEAD is on a branch this issue publishes under.

    The half of the identity that says the tree belongs to this issue rather
    than to whatever was checked out into it afterwards. Both names one issue
    can be published under are accepted, since a checkout made before slug
    namespacing landed is still on the flat one.
    """
    answer, branch = _head_ref(worktree)
    if answer is not ProbeAnswer.CONFIRMED:
        return answer
    if branch not in _naming._issue_branch_names(spec, issue_number):
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED


def _checkout_identity(
    spec: _config_models.RepoSpec, issue_number: int, worktree: Path,
) -> ProbeAnswer:
    """Whether this checkout is the one this issue's own creator made.

    Both halves have to hold and neither implies the other: a worktree of the
    configured clone can be sitting on any branch in it, and a HEAD naming
    this issue's branch can belong to a repository somebody else made. The
    repository is asked first, because a HEAD read against a tree that is not
    ours answers about a ref store this classification is not entitled to
    reason about.
    """
    shared = _shared_repository(spec, worktree)
    if shared is not ProbeAnswer.CONFIRMED:
        return shared
    return _head_is_own_branch(spec, issue_number, worktree)
