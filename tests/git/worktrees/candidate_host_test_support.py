# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The host a terminal-artifact classification reads: clone, remote, checkouts.

Real throughout, and the remote most of all. What the classification asks the
host IS a ref store, a working tree, and a remote's answer about a branch, so
a double of any of them would hand the fixture back instead of git -- and the
one thing these probes exist to prove is that a local ref an agent can write
cannot stand in for what the remote says. A bare repository on disk is what
makes the difference between the two visible: `refs/remotes/<remote>/<branch>`
can be pointed anywhere while the remote goes on answering what it actually
holds.

The commits are written with `commit-tree` straight into the object store. A
branch carrying work and a branch sitting exactly on base are two refs and
nothing else here reads a working tree to find that out, so there is no reason
to check anything out to make one.
"""

from __future__ import annotations

import os
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths
from tests.git.worktrees import candidate_refs as _candidate_refs, candidate_remotes as _candidate_remotes
from tests.git.worktrees.artifact_git import BASE_BRANCH
from tests.workflow.stages.question.question_real_git_test_support import (
    _run_git,
)

CLONE_NAME = "target"
COMMIT_MESSAGE = "candidate work"
# The two files under a checkout's own git directory that git writes when
# somebody works in the tree.
INDEX_FILE = "index"
HEAD_REFLOG = "logs/HEAD"
# The file inside that directory pointing back at the tree, which is what
# `worktree list` follows to report the worktree at all.
WORKTREE_BACKLINK = "gitdir"


class _CandidateWorld(_candidate_remotes._CandidateRemotes):
    """A clone, the bare remote it has pushed its base to, and its checkouts.

    The remote is a repository rather than a tracking ref, because that is the
    distinction under test: an agent shares the clone's object store and can
    move any `refs/remotes/...` in it, so a fixture that only wrote tracking
    refs would prove the tampering it is meant to catch is undetectable.
    """

    def commit_on(
        self, root: Path, branch: str, *, start: str = BASE_BRANCH,
    ) -> str:
        """Put one commit on `branch`, creating the branch if it is new.

        The branch is named in the message, because everything else about two
        commits made here is identical -- same tree, same parent, same
        identity, same second -- and git would hand back one object under two
        names. A case that needs two branches to disagree would then be
        asserting that they agree.
        """
        made = _run_git(
            "commit-tree",
            _candidate_refs._revision(root, f"{start}^{{tree}}"),
            "-p", _candidate_refs._revision(root, start),
            "-m", f"{COMMIT_MESSAGE} on {branch}",
            cwd=root,
        )
        tip = (made.stdout or "").strip()
        _candidate_refs._branch_at(root, branch, tip)
        return tip

    def attached_checkout(
        self, spec: _config_models.RepoSpec, issue_number: int, branch: str,
    ) -> Path:
        """Add the issue's worktree on the branch its creator leaves it on."""
        return self.checkout_at(
            spec, paths._worktree_path(spec, issue_number), branch,
        )

    def checkout_at(
        self, spec: _config_models.RepoSpec, worktree: Path, branch: str,
    ) -> Path:
        """Add a worktree of this clone at a named path, on a named branch.

        The path is stated rather than derived, for the one case where it is
        not what the derivation writes now: a checkout made before slug
        namespacing sits directly under `WORKTREES_DIR`, and a host that was
        running then can still be holding it.
        """
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _run_git(
            "worktree", "add", _candidate_refs.QUIET, str(worktree), branch,
            cwd=spec.target_root,
        )
        return worktree


def _checkout_git_dir(worktree: Path) -> Path:
    """The git directory this checkout keeps for itself.

    Asked of git rather than assembled, because a linked worktree keeps its
    own under the parent's `worktrees/` and the `.git` at its root is a file
    pointing there.
    """
    located = _run_git("rev-parse", "--absolute-git-dir", cwd=worktree)
    return Path((located.stdout or "").strip())


def _index_path(worktree: Path) -> Path:
    """The index file this checkout compares its tree against."""
    return _checkout_git_dir(worktree) / INDEX_FILE


def _unlink_backlink(worktree: Path) -> Path:
    """Remove the administrative backlink a linked worktree is listed through.

    What a half-finished move or a stray cleanup leaves: the entry under the
    clone's `worktrees/` is still there and the tree still works, but
    `worktree list` passes over it in silence -- exit zero, nothing on stderr,
    and one fewer worktree in the answer.
    """
    backlink = _checkout_git_dir(worktree) / WORKTREE_BACKLINK
    backlink.unlink()
    return backlink


def _settle_checkout(worktree: Path, when: float) -> None:
    """Back-date every trace of somebody having worked in this checkout.

    The tree's own directory and the two files under its git directory that
    git writes when it is worked in -- a fixture that moved only the first
    would leave a checkout the probe still reads as touched a moment ago, and
    a case expecting a pass to act would fail for a reason it is not about.
    """
    git_dir = _checkout_git_dir(worktree)
    for touched in (worktree, git_dir / INDEX_FILE, git_dir / HEAD_REFLOG):
        if touched.exists():
            os.utime(touched, (when, when))


def _foreign_checkout(spec: _config_models.RepoSpec, issue_number: int) -> Path:
    """Put a repository of somebody else's where the checkout belongs."""
    worktree = paths._worktree_path(spec, issue_number)
    worktree.mkdir(parents=True)
    _run_git("init", _candidate_refs.QUIET, "-b", BASE_BRANCH, cwd=worktree)
    return worktree
