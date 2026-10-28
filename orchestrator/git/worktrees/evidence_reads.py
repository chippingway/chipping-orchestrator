# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hardened checkout reads and clone reads serialized with worktree mutations.

Two checkout reads are spelled here rather than at their caller: whether git
reads a directory as the root of its own work tree, and which branch an
unfinished rebase in the tree is rewriting, since a rebase leaves HEAD
detached until it finishes.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git import commands, locks
from orchestrator.git.worktrees.models import ProbeAnswer

log = logging.getLogger("orchestrator.worktree_lifecycle")

# Where git keeps an unfinished rebase's state, one directory per backend, and
# the file in it naming the branch the rebase is rewriting.
_REBASE_HEAD_NAMES = ("rebase-merge/head-name", "rebase-apply/head-name")

_LOCAL_BRANCH_PREFIX = "refs/heads/"



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


def _rooted_here(worktree: Path) -> ProbeAnswer:
    """Whether git reads `worktree` as the root of a work tree, rather than a directory inside another's.

    Git discovers a repository from any directory below one, so a plain
    directory inside the clone shares the clone's store as squarely as a
    linked worktree does, and stands on whatever branch the clone has checked
    out. The top level git reads there is what tells them apart: a linked
    worktree's is the checkout itself. `UNREADABLE` is a git that would not
    answer or a path that will not resolve.
    """
    located = _hardened_read(worktree, "rev-parse", "--show-toplevel")
    if located is None or located.returncode != 0:
        return ProbeAnswer.UNREADABLE
    top = (located.stdout or "").strip()
    if not top:
        return ProbeAnswer.UNREADABLE
    try:
        rooted = Path(top).resolve() == worktree.resolve()
    except (OSError, RuntimeError):
        return ProbeAnswer.UNREADABLE
    return ProbeAnswer.CONFIRMED if rooted else ProbeAnswer.REFUTED


def _rebase_head_name(worktree: Path, head_name: str) -> str | None:
    """What one rebase backend's state file names, "" where it has none, None where it would not read."""
    located = _hardened_read(worktree, "rev-parse", "--git-path", head_name)
    if located is None or located.returncode != 0:
        return None
    state_file = Path((located.stdout or "").strip())
    if not state_file.is_absolute():
        state_file = worktree / state_file
    try:
        return state_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except OSError:
        return None


def _rebased_branch(worktree: Path) -> tuple[ProbeAnswer, str]:
    """Whether an unfinished rebase in this checkout is rewriting a branch, and which one.

    A rebase leaves HEAD detached until it finishes, so a checkout an
    interrupted rebase or a conflict left mid-replay names no branch through
    HEAD; the state directory git keeps for the rebase names the branch it is
    rewriting, and that is the one reading that ties the detached tree to a
    branch. `REFUTED` is no rebase in progress, or one rewriting a detached
    HEAD; `UNREADABLE` is a git or a file that would not answer.
    """
    for head_name in _REBASE_HEAD_NAMES:
        named = _rebase_head_name(worktree, head_name)
        if named is None:
            return ProbeAnswer.UNREADABLE, ""
        if named.startswith(_LOCAL_BRANCH_PREFIX):
            return ProbeAnswer.CONFIRMED, named.removeprefix(_LOCAL_BRANCH_PREFIX)
        if named:
            return ProbeAnswer.REFUTED, ""
    return ProbeAnswer.REFUTED, ""


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
