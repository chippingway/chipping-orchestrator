# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The worktree a resume runs in, restored when a prior tick's is gone.

Every resume path -- the human reply, the drift followup, and the parked
`/orchestrator continue` retry -- needs a checkout to run the agent in, and any
of them can arrive after the directory was reaped (an operator cleaned up, or a
terminal stage removed it). Reusing an existing path is the common case and
must stay cheap; recreating one has to go through the pinned branch name so the
restored worktree lands back on the branch this issue's commits are on rather
than a freshly derived one.

It sits apart from the resume owners because all three of them ask for it
before they have a session, a prompt, or a decision -- and because a caller
that skipped it would silently run the agent in whatever directory the path
happened to point at.
"""
from __future__ import annotations

from pathlib import Path

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import (
    creation as _worktree_creation,
    naming as _naming,
)
from orchestrator.github.pinned_state import PinnedState


def _admitted_resume(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> tuple[str, Path | None]:
    """The branch a resume stands on and the checkout already standing for it, or `naming.BranchRefused`.

    Reads only, so a road that posts, records, or relabels before it resumes
    anybody asks it ahead of all of that rather than meeting the refusal at
    the restore. The branch is resolved whether or not the checkout is still
    on disk, and a checkout standing at the issue's path is taken only once it
    is proven the issue's own (`creation._retained_checkout`) -- detached in
    the middle of rebasing exactly that branch included, which is how a
    conflict resolution parked mid-rebase leaves it. A record naming no branch
    live work may use, and any other tree, refuse with every file in place.
    None is a path with nothing at it, for the restore to create.
    """
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    return branch, _worktree_creation._retained_checkout(spec, issue.number, rebasing=True)


def _refuses_live_work(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> bool:
    """Whether the record or the checkout standing for it refuses live work (`_admitted_resume`), said where met.

    For a dispatcher road that holds the tick rather than raising: a refusal
    there would escape the handler's own catch, so the road asks this first
    and holds with nothing parked, posted, measured, or pushed.
    """
    try:
        _admitted_resume(spec, issue, state)
    except _naming.BranchRefused:
        return True
    return False


def _ensure_resume_worktree(
    spec: _config_models.RepoSpec, issue: Issue, state: PinnedState,
) -> Path:
    """The checkout a resumed session runs in, once the record names its branch.

    Admitted first (`_admitted_resume`): every dev resume builds its run
    through here before it launches, so a record naming no branch live work
    may use, or a tree at the issue's path that is not the issue's own,
    raises `naming.BranchRefused` before any agent runs. A checkout that is
    gone is recreated on that branch.
    """
    branch, retained = _admitted_resume(spec, issue, state)
    if retained is not None:
        return retained
    return _worktree_creation._ensure_worktree(spec, issue.number, branch=branch)
