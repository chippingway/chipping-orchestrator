# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Checkouts of a named project, the directories a target or a source layout is.

Shared by the configuration tests that hold every target to a checkout and
read the developer layout off one, the runtime tests that probe a source
checkout's own HEAD, and the service tests that validate a setup's clone and
tell a source package from an installed one.
"""
from __future__ import annotations

from pathlib import Path

from tests.support.git import _run_git

_MANIFEST = "pyproject.toml"


def make_checkout(root: Path, project_name: str = "chipping-orchestrator") -> Path:
    """Make ``root`` a git checkout whose ``pyproject.toml`` names a project."""
    root.mkdir(parents=True, exist_ok=True)
    (root / _MANIFEST).write_text(f'[project]\nname = "{project_name}"\n')
    _run_git("init", "-q", "-b", "main", cwd=root)
    return root


def committed_checkout(root: Path) -> Path:
    """A checkout of this project at ``root`` with its manifest committed.

    A commit is what a branch, a linked worktree, or a remote-tracking ref
    needs to point at.
    """
    make_checkout(root)
    _run_git("add", _MANIFEST, cwd=root)
    _run_git("commit", "-q", "-m", "init", cwd=root)
    return root
