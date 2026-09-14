# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real-git branch fixtures for the unpushed-commit probes."""

from __future__ import annotations

import contextlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import models as _config_models
from tests.workflow.stages.question.question_real_git_test_support import (
    _run_git,
    _seed_target_root,
    _spec_for,
)

REAL_GIT_SLUG = "orch__realgit"
GIT_BRANCH = "branch"
GIT_COMMIT_MESSAGE_FLAG = "-m"
GIT_REV_PARSE = "rev-parse"
GIT_UPDATE_REF = "update-ref"


@contextlib.contextmanager
def _temp_root(prefix: str):
    """Yield a throwaway directory as a `Path`, removed on exit."""
    with tempfile.TemporaryDirectory(prefix=prefix) as temp_dir:
        yield Path(temp_dir)


@dataclass(frozen=True)
class GitBranchFixture:
    target: Path
    base_sha: str
    issue_number: int
    branch: str

    @property
    def spec(self) -> _config_models.RepoSpec:
        return _spec_for(self.target)

    def create(self) -> None:
        _run_git(
            GIT_BRANCH,
            self.branch,
            self.base_sha,
            cwd=self.target,
        )

    def commit(self, message: str) -> None:
        self.create()
        tree = _run_git(
            GIT_REV_PARSE,
            "HEAD^{tree}",
            cwd=self.target,
        ).stdout.strip()
        new_commit = _run_git(
            "commit-tree",
            tree,
            "-p",
            self.base_sha,
            GIT_COMMIT_MESSAGE_FLAG,
            message,
            cwd=self.target,
        ).stdout.strip()
        _run_git(
            GIT_UPDATE_REF,
            f"refs/heads/{self.branch}",
            new_commit,
            cwd=self.target,
        )


def _seed_branch_fixture(
    temp_root: Path,
    issue_number: int,
    branch: str,
) -> GitBranchFixture:
    target, base_sha = _seed_target_root(temp_root)
    return GitBranchFixture(
        target=target,
        base_sha=base_sha,
        issue_number=issue_number,
        branch=branch,
    )
