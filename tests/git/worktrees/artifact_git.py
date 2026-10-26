# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real clones, branch refs, and detached worktrees in a temporary artifact host."""
from __future__ import annotations

from pathlib import Path

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths
from tests.support.git import (
    _run_git,
)

BASE_BRANCH = "main"


def _flat_checkout_path(issue_number: int) -> Path:
    """Where a checkout sat before the slug went into the path.

    Spelled out rather than derived: no owner derives it any more, and the
    tests that plant one are proving that nothing attributes or removes it.
    """
    return config.WORKTREES_DIR / f"issue-{issue_number}"


class _ArtifactGitFixture:
    """Git objects and detached checkouts rooted in the artifact world."""

    def clone(self, name: str) -> Path:
        """A repository with one commit, standing in for a `target_root`."""
        root = self.path(name)
        root.mkdir(parents=True)
        _run_git("init", "-q", "-b", BASE_BRANCH, cwd=root)
        _run_git("commit", "-q", "--allow-empty", "-m", "init", cwd=root)
        return root

    def branch(self, root: Path, name: str) -> None:
        _run_git("branch", name, cwd=root)

    def tag(self, root: Path, name: str) -> None:
        _run_git("tag", name, cwd=root)

    def checkout(self, spec: _config_models.RepoSpec, issue_number: int) -> Path:
        """Add the issue's worktree where the creators would put it."""
        return self._checkout_at(
            spec, paths._worktree_path(spec, issue_number),
        )

    def legacy_checkout(
        self, spec: _config_models.RepoSpec, issue_number: int,
    ) -> Path:
        """Add the issue's worktree where they put one before namespacing.

        Directly under `WORKTREES_DIR`, with no per-repository parent, so the
        directory carries nothing saying which entry made it -- and no scan
        attributes it to any of them.
        """
        return self._checkout_at(spec, _flat_checkout_path(issue_number))

    def _checkout_at(self, spec: _config_models.RepoSpec, worktree: Path) -> Path:
        """One detached worktree of this spec's clone, at a named path."""
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _run_git(
            "worktree", "add", "-q", "--detach", str(worktree),
            cwd=spec.target_root,
        )
        return worktree
