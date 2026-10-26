# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real tree reached at an issue's own path that is not the issue's own checkout.

Shared by the worktree teardown tests and the late split's branch reclamation
tests, which both hold that a forced removal is spent only on a checkout proven
the issue's own. Every shape here carries an uncommitted file nothing has saved.
By default the tree sits at the current-layout path, a worktree of the clone
standing on the flat `orchestrator/issue-<n>`. Linked, it is a flat
`WORKTREES_DIR/issue-<n>` checkout standing on the issue's own current branch,
reached from the current-layout path through a symlink: one at the issue's path
itself (`LINKED_CHECKOUT`), or a per-repository parent that is one
(`LINKED_PARENT`).
"""
from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths
from tests.support.git import _git_env, _run_git, _seed_target_root, _spec_for

LOOSE_CONTENT = "operator work\n"

LINKED_CHECKOUT = "checkout"

LINKED_PARENT = "parent"

_LOOSE_FILE = "uncommitted.txt"


@dataclass(frozen=True)
class ForeignCheckout:
    """The clone's spec, the branch the tree stands on, and its loose file."""

    spec: _config_models.RepoSpec
    branch: str
    loose: Path

    def branch_present(self) -> bool:
        """Whether the clone still carries the branch the tree stands on."""
        return subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{self.branch}"],
            cwd=str(self.spec.target_root),
            env=_git_env(),
            capture_output=True,
            check=False,
        ).returncode == 0


@contextmanager
def foreign_checkout(issue_number: int, link: str = "") -> Iterator[ForeignCheckout]:
    """Seed one such tree under a temporary `WORKTREES_DIR`, linked as `link` says."""
    with (
        tempfile.TemporaryDirectory(prefix="foreign-checkout-") as temp_dir,
        patch.object(config, "WORKTREES_DIR", Path(temp_dir) / "worktrees"),
    ):
        if link:
            yield _linked(Path(temp_dir), issue_number, link)
        else:
            yield _seeded(Path(temp_dir), issue_number)


def _seeded(root: Path, issue_number: int) -> ForeignCheckout:
    """A clone under `root`, with a checkout on the flat branch at the issue's path."""
    target, base_sha = _seed_target_root(root)
    spec = _spec_for(target)
    return _planted(
        spec, base_sha, paths._worktree_path(spec, issue_number),
        f"orchestrator/issue-{issue_number}",
    )


def _linked(root: Path, issue_number: int, link: str) -> ForeignCheckout:
    """A clone under `root`, with a flat checkout the issue's path reaches by symlink."""
    target, base_sha = _seed_target_root(root)
    spec = _spec_for(target)
    flat = _planted(
        spec, base_sha, config.WORKTREES_DIR / f"issue-{issue_number}",
        f"orchestrator/orch__realgit/issue-{issue_number}",
    )
    if link == LINKED_PARENT:
        _link(paths._repo_worktrees_root(spec), config.WORKTREES_DIR)
    else:
        _link(paths._worktree_path(spec, issue_number), flat.loose.parent)
    return flat


def _planted(
    spec: _config_models.RepoSpec, base_sha: str, worktree: Path, branch: str,
) -> ForeignCheckout:
    """Add a worktree of the clone at `worktree` on a new `branch`, and leave a loose file in it."""
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _run_git("worktree", "add", "-b", branch, str(worktree), base_sha, cwd=spec.target_root)
    (worktree / _LOOSE_FILE).write_text(LOOSE_CONTENT)
    return ForeignCheckout(spec=spec, branch=branch, loose=worktree / _LOOSE_FILE)


def _link(at: Path, to: Path) -> None:
    """Make `at` a symlink to the directory `to`."""
    at.parent.mkdir(parents=True, exist_ok=True)
    at.symlink_to(to, target_is_directory=True)
