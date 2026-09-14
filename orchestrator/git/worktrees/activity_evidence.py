# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Whether a checkout has been quiet long enough for artifact maintenance.

The checkout, index, and HEAD reflog all matter: activity in any one of them
keeps the directory, and an unreadable timestamp cannot establish quiet."""
from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

from orchestrator.git.worktrees import (
    evidence_reads as _evidence_reads,
)
from orchestrator.git.worktrees.models import ProbeAnswer

log = logging.getLogger("orchestrator.worktree_lifecycle")


# The two files a checkout's own git directory carries that git writes when
# somebody works in that tree: the index every `add`, `commit`, and refreshed
# `status` rewrites, and the reflog every move of its HEAD appends to.
_INDEX = "index"

_HEAD_REFLOG = "logs/HEAD"


def _checkout_git_dir(worktree: Path) -> Path | None:
    """The git directory this checkout keeps for itself, or None.

    Its OWN, not the store it shares: a linked worktree has a directory under
    the parent's `worktrees/` holding the HEAD, the index, and the reflog that
    belong to that tree alone. Those are the files git writes when somebody
    works in it, which is what makes them the evidence the read below is after
    -- the shared store would answer the same for every checkout of the clone.

    Answered absolutely, so a caller does not have to know which directory it
    is relative to; `None` when git would not say, which the caller spends as
    a reading that established nothing rather than as a tree nobody has been
    near.
    """
    located = _evidence_reads._hardened_read(worktree, "rev-parse", "--absolute-git-dir")
    if located is None or located.returncode != 0:
        return None
    git_dir = (located.stdout or "").strip()
    return Path(git_dir) if git_dir else None


def _last_touched(paths_touched: Iterable[Path]) -> float | None:
    """The newest modification time among some paths, or None if one refused.

    A path that is not there contributes nothing rather than failing the read:
    the reflog is absent wherever `core.logAllRefUpdates` is off, and its
    absence says nothing at all about when the tree was last worked in. Any
    OTHER refusal answers `None`, since a reading that could not be taken must
    not come back as the oldest timestamp it managed to collect.
    """
    newest = None
    for path in paths_touched:
        try:
            touched = path.lstat().st_mtime
        except FileNotFoundError:
            continue
        except OSError as read_error:
            log.debug("could not read when %s was touched: %s", path, read_error)
            return None
        newest = touched if newest is None else max(newest, touched)
    return newest


def _quiet_checkout(worktree: Path, since: float) -> ProbeAnswer:
    """Whether this checkout PROVED nothing has touched it since `since`.

    The restraint a caller about to delete a tree owes an operator who may
    still be standing in it. Every other read here asks what the checkout
    HOLDS; this one asks when it was last disturbed, which is the only
    question that separates an issue that finished months ago from one whose
    agent stopped a minute before the pass ran.

    Three timestamps, because no one of them sees the whole of it. The
    directory's own answers for an entry created, renamed, or removed at the
    top of the tree -- a clone, a build root, a file dropped in by hand -- and
    for nothing else: editing a tracked file deeper in leaves it exactly where
    it was, and so does committing that edit. What git writes on a commit is
    the checkout's OWN index and its own reflog, both under the per-worktree
    git directory, so those two are what say a tree was being worked in a
    moment ago even though everything in it is now clean and committed.

    `since` is a wall-clock instant the caller decided, so what counts as
    lately is the pass's policy rather than this module's. `REFUTED` is a tree
    touched after it -- an established fact about the checkout -- and
    `UNREADABLE` is a host that would not say: a path gone since the scan named
    it answers that way too, because a caller may not read "the tree I was
    about to delete cannot be found" as proof that deleting it costs nothing.
    A checkout whose git directory could not be located is the same answer, for
    the same reason: without it, the only timestamp left is the one a commit
    does not move.
    """
    git_dir = _checkout_git_dir(worktree)
    if git_dir is None:
        log.debug("could not locate the git directory of %s", worktree)
        return ProbeAnswer.UNREADABLE
    touched = _last_touched((
        worktree, git_dir / _INDEX, git_dir / _HEAD_REFLOG,
    ))
    if touched is None:
        return ProbeAnswer.UNREADABLE
    if touched > since:
        return ProbeAnswer.REFUTED
    return ProbeAnswer.CONFIRMED
