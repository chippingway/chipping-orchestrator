# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Per-issue worktree removal and local branch deletion.

The two teardown steps share this module because git refuses to delete a
branch that is still checked out, so every caller runs them as one ordered
pair. Each step splits into a bare runner and a best-effort wrapper: the
wrapper owns the exception boundary, which lets a caller tear down the
next surface even when this one failed.

Best-effort is right for a caller whose issue is already terminal -- a stale
ref there is tidiness -- and not for one that has to RECORD whether the
teardown happened. The forced removal is spent only on a checkout proven the
issue's own (`_own_checkout`): a path reached through a symlink, a tree that is
no worktree of the clone, and one that stands on a flat or foreign branch each
keep every file in them. `_local_branch_present` is what the second kind asks
afterwards, and it fails closed: a read that established nothing answers
"still here", because a caller that took it for gone would mark an obligation
settled that nothing had settled.
"""
from __future__ import annotations

import logging
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands, locks
from orchestrator.git.worktrees import evidence, paths
from orchestrator.git.worktrees.models import ProbeAnswer

# The channel is named for the worktree-lifecycle domain rather than for
# this module's path: operators filter the rendered
# `orchestrator.worktree_lifecycle` prefix and attach handlers to it, so
# every owner in this package reports where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")


def _own_checkout(
    spec: _config_models.RepoSpec,
    issue_number: int,
    worktree: Path,
    log_prefix: str,
) -> bool:
    """Whether the tree at this issue's path is proven the issue's own.

    The removal behind this is forced, so it takes whatever the tree holds;
    it may be spent only on a worktree of this clone standing on the issue's
    exact current-layout branch, reached at that path itself rather than
    through a symlink. A path that leads elsewhere, a tree on a flat
    `orchestrator/issue-<n>`, on another repository's branch, or on a
    detached HEAD is foreign, and one whose identity could not be read is not
    proven -- both stay, every file in them included, for an operator to
    dispose of.
    """
    identity = evidence._checkout_identity(spec, issue_number, worktree)
    if identity is ProbeAnswer.CONFIRMED:
        return True
    log.warning(
        "issue=#%d %scheckout %s is not proven this issue's own (%s); "
        "leaving it for manual disposition",
        issue_number, log_prefix, worktree, identity,
    )
    return False


def _run_issue_worktree_removal(
    spec: _config_models.RepoSpec, issue_number: int, log_prefix: str,
) -> None:
    """Force-remove one issue worktree proven the issue's own, under the
    parent lock, logging a non-zero git result."""
    worktree = paths._worktree_path(spec, issue_number)
    if not worktree.exists():
        return
    if not _own_checkout(spec, issue_number, worktree, log_prefix):
        return
    with locks._target_root_lock(spec.target_root):
        remove_result = commands._git(
            "worktree", "remove", "--force", str(worktree),
            cwd=spec.target_root,
        )
    if remove_result.returncode != 0:
        log.warning(
            "issue=#%d %sworktree remove failed: %s",
            issue_number,
            log_prefix,
            (remove_result.stderr or "").strip(),
        )


def _remove_issue_worktree(
    spec: _config_models.RepoSpec, issue_number: int, *, log_prefix: str = "",
) -> None:
    """Best-effort removal of one issue worktree under the parent lock."""
    try:
        _run_issue_worktree_removal(spec, issue_number, log_prefix)
    except Exception:
        log.exception(
            "issue=#%d %sworktree remove raised", issue_number, log_prefix,
        )


def _run_local_branch_deletion(
    spec: _config_models.RepoSpec, issue_number: int, branch: str, log_prefix: str,
) -> None:
    """Delete one local issue branch under the parent lock (no-op when the
    branch is absent), logging a non-zero git result."""
    with locks._target_root_lock(spec.target_root):
        have_local = commands._git(
            "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
            cwd=spec.target_root,
        ).returncode == 0
        if not have_local:
            return
        delete_result = commands._git(
            "branch", "-D", branch, cwd=spec.target_root,
        )
    if delete_result.returncode != 0:
        log.warning(
            "issue=#%d %slocal branch %r delete failed: %s",
            issue_number,
            log_prefix,
            branch,
            (delete_result.stderr or "").strip(),
        )


def _delete_local_issue_branch(
    spec: _config_models.RepoSpec,
    issue_number: int,
    branch: str,
    *,
    log_prefix: str = "",
) -> None:
    """Best-effort deletion of one local issue branch under the parent lock."""
    try:
        _run_local_branch_deletion(spec, issue_number, branch, log_prefix)
    except Exception:
        log.exception(
            "issue=#%d %slocal branch %r delete raised",
            issue_number,
            log_prefix,
            branch,
        )


def _local_branch_present(spec: _config_models.RepoSpec, branch: str) -> bool:
    """Whether the local clone still carries `branch`.

    The verification half of a teardown a caller has to record. Fail-closed on
    everything that is not a clean answer: `--verify --quiet` exits 0 when the
    ref resolves and 1 when it does not, and any other exit -- a repository
    that could not be read, a git that could not be run -- is a reading that
    established nothing, which a caller must not spend as proof the branch is
    gone.
    """
    try:
        with locks._target_root_lock(spec.target_root):
            resolved = commands._git(
                "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
                cwd=spec.target_root,
            )
    except Exception:
        log.exception("local branch %r could not be read", branch)
        return True
    if resolved.returncode == 0:
        return True
    if resolved.returncode == 1:
        return False
    log.warning(
        "local branch %r read answered %d; treating it as still present",
        branch, resolved.returncode,
    )
    return True
