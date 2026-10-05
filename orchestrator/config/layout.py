# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the running package sits, and where the worktree root defaults to.

``is_source_checkout`` tells this project's own source checkout -- an ordinary
clone, a linked worktree, or an editable install of either, all of which run
the package from inside the checkout -- apart from an installed distribution,
whose package root is an environment's ``site-packages``. It is proved at that
root alone: a ``pyproject.toml`` naming this project there, and git opening
that root as the top of a checkout, as ``checkouts`` asks it, so neither an
unrelated repository enclosing an installed environment nor the directory a
run was launched from can stand in for one.

``default_worktrees_dir`` places the worktree root beside the first configured
target, from the paths alone. Neither imports anything from the git layer,
which keeps this leaf below it like the rest of the package.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path

from orchestrator.config.checkouts import checkout_problem

_PROJECT_NAME = "chipping-orchestrator"
_WORKTREES_DIR_NAME = "wt-orchestrator"


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
    # The manifest is read first: an installed root has none, and is then
    # answered without starting git.
    return (
        _names_this_project(package_root)
        and checkout_problem(package_root) is None
    )


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
