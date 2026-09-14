# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Rebasing one issue worktree onto its base, and the pre-PR path that runs it.

Every command here goes through the hardened git envelope because the
worktree is agent-writable: even the read-only unmerged-path probe would
otherwise execute a planted hooksPath or fsmonitor under the orchestrator's
UID. The pre-PR path is the only caller that may abort on conflict and leave
the worktree on its original SHA -- nothing is pushed yet, so no remote head
depends on the rewrite and conflict resolution can wait until a PR exists.
The rebase-state probes are published for the conflict stage, which asks
whether a worktree still sits mid-rebase before it parks one.
"""
from __future__ import annotations

from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands as _commands
from orchestrator.git.base_sync import state as _state

log = _state.log


def _rebase_base_into_worktree(
    spec: _config_models.RepoSpec, worktree: Path
) -> tuple[bool, list[str]]:
    """Run `git rebase origin/<base>` in the worktree.

    Returns `(succeeded, conflicted_files)`. On success, `conflicted_files`
    is empty -- whether the rebase was a no-op or replayed commits is the
    caller's job to detect via the HEAD-SHA delta. On failure, the
    conflicted-file list is the unmerged paths from
    `git diff --name-only --diff-filter=U`; an empty list means the rebase
    failed for a non-conflict reason (hooks, permissions, etc.) and the
    caller should park rather than ask the agent to resolve nothing.

    Both subprocess calls run under `_git_hardened`: the diff is
    read-only but still executes inside an agent-writable worktree, so
    a planted hooksPath / fsmonitor would otherwise execute attacker
    code under the orchestrator's UID at diff time.
    """
    rebase_result = _commands._git_hardened(
        "rebase",
        f"{spec.remote_name}/{spec.base_branch}", cwd=worktree,
    )
    if rebase_result.returncode == 0:
        return True, []
    conflicted = _commands._git_hardened(
        "diff", "--name-only", "--diff-filter=U", cwd=worktree,
    )
    files = [
        line.strip() for line in (conflicted.stdout or "").splitlines()
        if line.strip()
    ]
    return False, files


def _merge_base_into_worktree(
    spec: _config_models.RepoSpec, worktree: Path
) -> tuple[bool, list[str]]:
    """Compatibility alias for older patches/imports.

    TODO(remove after 2026-08-24): drop once out-of-repo patches have moved
    to `_rebase_base_into_worktree`.
    """
    return _rebase_base_into_worktree(spec, worktree)


def _rebase_state_exists(worktree: Path, state_dir: str) -> bool:
    """Resolve one git rebase-state path and report whether it exists."""
    git_path_result = _commands._git_hardened(
        "rev-parse", "--git-path", state_dir, cwd=worktree,
    )
    if git_path_result.returncode != 0:
        return False
    path = (git_path_result.stdout or "").strip()
    if not path:
        return False
    state_path = Path(path)
    if not state_path.is_absolute():
        state_path = worktree / state_path
    return state_path.exists()


def _rebase_in_progress(worktree: Path) -> bool:
    """Return True when the worktree still has an unfinished rebase."""
    return any(
        _rebase_state_exists(worktree, state_dir)
        for state_dir in ("rebase-merge", "rebase-apply")
    )


def _sync_pre_pr_worktree(
    spec: _config_models.RepoSpec,
    worktree: Path,
    issue_number: int,
    behind: int,
) -> None:
    """Rebase one clean pre-PR worktree and restore it on failure."""
    base_ref = f"{spec.remote_name}/{spec.base_branch}"
    succeeded, conflicted_files = _rebase_base_into_worktree(spec, worktree)
    if succeeded:
        log.info(
            "issue=#%d rebased worktree onto %s (was %d commit(s) behind)",
            issue_number,
            base_ref,
            behind,
        )
        return

    abort_result = _commands._git_hardened("rebase", "--abort", cwd=worktree)
    if abort_result.returncode != 0:
        log.warning(
            "issue=#%d base rebase failed and abort failed: %s",
            issue_number,
            (abort_result.stderr or "").strip(),
        )
    if conflicted_files:
        log.info(
            "issue=#%d base rebase has %d conflict(s); aborted -- "
            "resolving_conflict will handle it once a PR exists",
            issue_number,
            len(conflicted_files),
        )
        return
    log.warning(
        "issue=#%d base rebase failed without conflicted files; aborted",
        issue_number,
    )
