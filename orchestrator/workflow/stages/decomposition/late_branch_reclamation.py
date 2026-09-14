# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reclaim only this issue's superseded branch and verify its local teardown.

The obligation remains failed until both the remote branch and local
checkout and branch are gone. An unowned branch is never deleted.
"""
from __future__ import annotations

import logging

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import cleanup as _worktree_cleanup, naming as _naming, paths as _worktree_paths
from orchestrator.github.client import GitHubClient
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.obligations import LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_cleanup_state as _late_cleanup_state,
)

log = logging.getLogger("orchestrator.workflow")



def _ours(
    spec: _config_models.RepoSpec, issue_number: int, branch: str,
) -> bool:
    """Whether a recorded target is one of THIS issue's own branches.

    Asked before anything is deleted by it, because the target comes off a
    ledger a human can edit and the call it is spent on is destructive: an
    entry naming `main` would otherwise delete an unprotected `main`.

    An exact match against the names this spec publishes this issue under,
    not a namespace test. `orchestrator/` with an `/issue-<n>` tail is also
    the shape of ANOTHER repository's branch for another issue that shares the
    number -- `orchestrator/other-repository/issue-41` passes a prefix-and-
    tail reading -- and two specs sharing one `target_root` is the ordinary
    case, not a contrived one. The number comes from the issue being walked
    rather than from the record, so a hand-edited identity cannot point the
    delete at a branch of somebody else's.
    """
    if not isinstance(branch, str):
        return False
    return branch in _naming._issue_branch_names(spec, issue_number)


def _reclaim_branch(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue_number: int,
    generation: LateGeneration,
    branch: str,
) -> LateGeneration:
    """Take down every surface this branch exists on, and record the answer.

    Three surfaces, one obligation: the remote ref, the checkout holding the
    branch, and the local ref itself. A remote delete that succeeded beside a
    worktree that would not come down is not settled -- what is left is a
    checkout on a superseded branch that the per-tick base refresh treats as a
    pre-PR tree and goes on merging into.

    The two halves are attempted independently, and the entry is what BOTH
    said. A remote that refuses is a permission or ruleset problem only an
    operator can clear, so a local teardown conditioned on it is one that
    waits for a human to take down a checkout the refresh is merging into
    every tick meanwhile -- and the local half needs nothing from the remote
    to succeed. The identity check is the one thing that does gate it: a
    target this issue is not published under aims both deletes at somebody
    else's branch, so nothing is attempted at all.

    The local half is verified rather than trusted. Its two helpers are
    best-effort by design and report nothing, so what decides the entry is a
    read taken afterwards, and that read fails closed.

    Recorded whichever way it went: a `failed` obligation is still an
    obligation, and writing it is what keeps the retry pointed at the same
    branch rather than at whatever the resolver would name later.
    """
    if not _ours(spec, issue_number, branch):
        log.error(
            "issue=#%d recorded branch %r is not one this issue is published "
            "under; refusing to delete it", issue_number, branch,
        )
        return _late_cleanup_state._recorded(generation, _late_cleanup_state._BRANCH, branch, LateResourceState.FAILED)
    try:
        deleted = gh.delete_remote_branch(branch)
    except Exception:
        log.exception("superseded branch %r delete raised", branch)
        deleted = False
    local_gone = _local_gone(spec, issue_number, branch)
    return _late_cleanup_state._recorded(generation, _late_cleanup_state._BRANCH, branch, (
        LateResourceState.RECONCILED if deleted and local_gone
        else LateResourceState.FAILED
    ))


def _local_gone(
    spec: _config_models.RepoSpec, issue_number: int, branch: str,
) -> bool:
    """Take the local checkout and ref down, and say whether they are gone."""
    _worktree_cleanup._remove_issue_worktree(spec, issue_number)
    _worktree_cleanup._delete_local_issue_branch(spec, issue_number, branch)
    if _worktree_paths._worktree_path(spec, issue_number).exists():
        log.warning(
            "issue=#%d worktree is still on disk after the teardown; the "
            "branch obligation stays owed", issue_number,
        )
        return False
    if _worktree_cleanup._local_branch_present(spec, branch):
        log.warning(
            "issue=#%d local branch %r survived the teardown; the branch "
            "obligation stays owed", issue_number, branch,
        )
        return False
    return True
