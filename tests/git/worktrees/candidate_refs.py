# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Real commits and ref edits for candidate evidence, including forged tracking refs."""
from __future__ import annotations

from pathlib import Path

from tests.support.git import (
    _run_git,
)

QUIET = "-q"


def _revision(root: Path, revision: str) -> str:
    """The object id one revision in this clone names."""
    resolved = _run_git("rev-parse", "--verify", revision, cwd=root)
    return (resolved.stdout or "").strip()


def _branch_at(root: Path, branch: str, revision: str | None = None) -> str:
    """Put one local branch on `revision`, or take it away when there is none.

    The removal goes through `update-ref -d` rather than `branch -D` because
    that is what it takes to delete a branch a worktree has checked out --
    `branch -D` refuses, `update-ref` does it -- and that is the state worth
    building: a live checkout left standing on a ref nothing resolves.
    """
    if revision is None:
        _run_git("update-ref", "-d", f"refs/heads/{branch}", cwd=root)
        return ""
    tip = _revision(root, revision)
    _run_git("update-ref", f"refs/heads/{branch}", tip, cwd=root)
    return tip


def _symbolic_ref(root: Path, name: str, target: str) -> None:
    """Leave a branch name pointing at another ref rather than at a commit.

    What a deletion that dereferences would follow: the name a teardown was
    handed resolves to somebody else's branch, and deleting what it resolves to
    takes that branch instead.
    """
    _run_git(
        "symbolic-ref", f"refs/heads/{name}", f"refs/heads/{target}", cwd=root,
    )


def _tracking_ref(root: Path, branch: str, revision: str) -> str:
    """Point this clone's copy of a remote branch at `revision`.

    Written directly, which is the point: the ref lives in the object store
    the per-issue worktrees share, so this is a thing an agent can do to it
    and a classification must not believe.
    """
    mirrored = _revision(root, revision)
    _run_git(
        "update-ref", f"refs/remotes/origin/{branch}", mirrored, cwd=root,
    )
    return mirrored


def _track_file(root: Path, name: str, written: str) -> str:
    """Commit one file onto the clone's base branch.

    A checkout with a tracked file in it is what makes a status read
    observable: with nothing tracked there is no stat data to refresh, so a
    probe that writes the index and one that does not leave the same tree
    behind.
    """
    (root / name).write_text(written)
    _run_git("add", name, cwd=root)
    _run_git("commit", QUIET, "-m", f"track {name}", cwd=root)
    return _revision(root, "HEAD")
