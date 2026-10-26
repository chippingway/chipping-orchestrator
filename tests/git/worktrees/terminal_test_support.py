# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real worktree plus local branch for the question-cleanup test."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths
from tests.support.git import (
    _git_env,
    _run_git,
    _seed_target_root,
    _spec_for,
)
from tests.workflow.stages.question.question_test_support import _issue_branch

REAL_GIT_SLUG = "orch__realgit"


@dataclass(frozen=True)
class CleanupFixture:
    spec: _config_models.RepoSpec
    target: Path
    branch: str
    worktree: Path


def _branch_exists(fixture: CleanupFixture) -> bool:
    branch_probe = subprocess.run(
        [
            "git",
            "rev-parse",
            "--verify",
            "--quiet",
            f"refs/heads/{fixture.branch}",
        ],
        cwd=str(fixture.target),
        env=_git_env(),
        capture_output=True,
        text=True,
        check=False,
    )
    return branch_probe.returncode == 0


def _seed_cleanup_fixture(
    temp_root: Path,
    issue_number: int,
    *,
    create_worktree: bool,
) -> CleanupFixture:
    target, base_sha = _seed_target_root(temp_root)
    branch = _issue_branch(issue_number, slug=REAL_GIT_SLUG)
    spec = _spec_for(target)
    worktree = paths._worktree_path(spec, issue_number)
    if create_worktree:
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _run_git(
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree),
            base_sha,
            cwd=target,
        )
    else:
        _run_git("branch", branch, base_sha, cwd=target)
    return CleanupFixture(
        spec=spec,
        target=target,
        branch=branch,
        worktree=worktree,
    )


def _flat_branch(fixture: CleanupFixture, issue_number: int) -> CleanupFixture:
    """Put the flat `orchestrator/issue-<n>` beside the fixture's own branch.

    Answered as a fixture naming that branch, so the same existence probe reads
    both of them back.
    """
    branch = f"orchestrator/issue-{issue_number}"
    _run_git("branch", branch, fixture.branch, cwd=fixture.target)
    return replace(fixture, branch=branch)
