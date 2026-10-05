# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the running package sits, and where the worktree root defaults to.

``is_source_checkout`` tells this project's own source checkout -- an ordinary
clone, a linked worktree, or an editable install of either, all of which run
the package from inside the checkout -- apart from an installed distribution,
whose package root is an environment's ``site-packages``. It is proved at that
root alone: git metadata there and a ``pyproject.toml`` naming this project,
so neither an unrelated repository enclosing an installed environment nor the
directory a run was launched from can stand in for one.

``default_worktrees_dir`` places the worktree root beside the first configured
target. Both answer from the filesystem without running git, which keeps this
leaf below the git layer like the rest of the package.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

_PROJECT_NAME = "chipping-orchestrator"
_WORKTREES_DIR_NAME = "wt-orchestrator"
_GITDIR_PREFIX = "gitdir:"


def _has_git_metadata(root: Path) -> bool:
    """Whether ``root`` carries a git directory of its own, linked or not."""
    dot_git = root / ".git"
    if dot_git.is_dir():
        return (dot_git / "HEAD").is_file()
    try:
        pointer = dot_git.read_text(encoding="utf-8").partition("\n")[0]
    except (OSError, UnicodeDecodeError):
        return False
    if not pointer.startswith(_GITDIR_PREFIX):
        return False
    # A linked worktree's `.git` file names its git directory, relative to
    # the worktree when it is not absolute.
    git_dir = root / pointer.removeprefix(_GITDIR_PREFIX).strip()
    return (git_dir / "HEAD").is_file()


def _names_this_project(root: Path) -> bool:
    """Whether ``root/pyproject.toml`` declares this distribution."""
    try:
        manifest = tomllib.loads(
            (root / "pyproject.toml").read_text(encoding="utf-8"),
        )
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return False
    project = manifest.get("project")
    return isinstance(project, dict) and project.get("name") == _PROJECT_NAME


def is_source_checkout(package_root: Path) -> bool:
    """Whether the package runs from this project's own source checkout."""
    return _has_git_metadata(package_root) and _names_this_project(package_root)


def default_worktrees_dir(first_target: Path, *, from_repos: bool) -> Path:
    """``wt-orchestrator`` beside the first configured target.

    A ``REPOS`` target is made absolute first, lexically and with every
    symlink kept as spelled, so a ``.`` entry still puts the root beside that
    checkout rather than inside it. The developer default beside
    ``TARGET_REPO_ROOT`` takes that setting exactly as spelled, relative or
    through a symlink, so the root an existing checkout's worktrees and host
    locks sit under stays where it was.
    """
    if from_repos:
        return Path(os.path.abspath(first_target)).parent / _WORKTREES_DIR_NAME
    return first_target.parent / _WORKTREES_DIR_NAME
