# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Create a squash commit in the issue's checkout or restore its original head."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from orchestrator.config.models import RepoSpec
from orchestrator.git import commands
from orchestrator.git.publication import commits, planning
from orchestrator.git.verification import probes as verification_probes
from orchestrator.git.worktrees import creation as _worktree_creation

log = logging.getLogger("orchestrator.branch_publication")


class _SquashResetError(RuntimeError):
    """The soft reset failed while the original commits were still on the branch."""


class _SquashCommitError(RuntimeError):
    """The soft reset succeeded, but creating or reading the new commit failed."""

    def __init__(self, step: str, message: str) -> None:
        super().__init__(message)
        self.step = step


def _rollback_squash(
    spec: RepoSpec, issue_number: int, worktree: Path, restored: str, reason: str,
) -> bool:
    """Restore the ref and index, preserving edits made while publication was in flight."""
    _worktree_creation._proven_checkout(spec, issue_number, worktree)
    rollback_result = commands._git_hardened("reset", "--mixed", restored, cwd=worktree)
    if rollback_result.returncode == 0:
        return True
    log.error(
        "issue=#%s rollback to %s after %s failed; worktree may be "
        "in an inconsistent state and the approved commit's debt is "
        "left standing for it: %s",
        issue_number, restored, reason, (rollback_result.stderr or "").strip(),
    )
    return False


def _create_squash_commit(
    worktree: Path, message: str,
) -> subprocess.CompletedProcess:
    """Create the orchestrator-owned commit with hooks and signing disabled."""
    return commits._orchestrator_git(worktree, "commit", "-m", message)


def _rewrite_squash(
    spec: RepoSpec, issue_number: int, worktree: Path, plan: planning._SquashPlan,
) -> str:
    """Soft-reset and recommit the index, returning the commit to measure and publish."""
    _worktree_creation._proven_checkout(spec, issue_number, worktree)
    reset_result = commands._git_hardened("reset", "--soft", plan.base_sha, cwd=worktree)
    if reset_result.returncode != 0:
        detail = (reset_result.stderr or "").strip()
        raise _SquashResetError(f"reset --soft failed: {detail}")

    # The commit writes to whichever branch HEAD names after the reset.
    _worktree_creation._proven_checkout(spec, issue_number, worktree)
    commit_result = _create_squash_commit(worktree, plan.message)
    if commit_result.returncode != 0:
        detail = (commit_result.stderr or "").strip()
        raise _SquashCommitError("squash commit", f"squash commit failed: {detail}")

    new_sha = verification_probes._head_sha(worktree)
    if not new_sha:
        raise _SquashCommitError("post-commit head read", "could not read new HEAD after squash")
    return new_sha
