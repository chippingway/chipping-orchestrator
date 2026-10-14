# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Where the worktree root defaults to.

``default_worktrees_dir`` places the worktree root beside the first configured
target, from the paths alone. Whether the package runs from its own source
checkout is ``orchestrator.service.paths``'s answer, which a setup reads too
without loading any configuration. Nothing here imports from the git layer,
which keeps this leaf below it like the rest of the package.
"""
from __future__ import annotations

import os
from pathlib import Path

_WORKTREES_DIR_NAME = "wt-orchestrator"


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
