# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hardened checkout reads and clone reads serialized with worktree mutations."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands, locks

log = logging.getLogger("orchestrator.worktree_lifecycle")



def _hardened_read(
    root: Path, *args: str,
) -> subprocess.CompletedProcess | None:
    """Run one hardened read in `root`, or report that it never ran.

    `None` is the reading that did not happen -- a git that could not be
    spawned, a `root` the host will not run a process in -- as against the
    non-zero result a caller reads off a command that did. Both fail closed
    downstream, but only one of them says anything about the artifact, so
    they are not folded together here.
    """
    try:
        return commands._git_hardened(*args, cwd=root)
    except OSError as spawn_error:
        log.warning("could not run a git read in %s: %s", root, spawn_error)
        return None


def _clone_read(
    spec: _config_models.RepoSpec, *args: str,
) -> subprocess.CompletedProcess | None:
    """The same read against the clone, under the lock its refs move behind.

    Every mutation of this clone's worktrees and branches serializes on that
    lock, so a ref read taken outside it can land between a `worktree add`
    and the branch it creates -- and answer that a branch this orchestrator
    is in the middle of publishing does not exist. The lock is re-entrant, so
    a caller already holding it pays nothing for asking again.
    """
    with locks._target_root_lock(spec.target_root):
        return _hardened_read(spec.target_root, *args)
