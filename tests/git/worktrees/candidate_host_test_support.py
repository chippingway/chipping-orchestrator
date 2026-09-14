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

import contextlib
import os
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths
from tests.git.auth_session_test_support import _SESSIONS
from tests.git.worktrees.artifact_test_support import (
    BASE_BRANCH,
    _ArtifactWorld,
)
from tests.workflow.stages.question.question_real_git_test_support import (
    _run_git,
)

CLONE_NAME = "target"
REMOTE_DIR = "remote.git"
# A path nothing was ever cloned from: what a remote that cannot be
# reached looks like to the read every branch proof starts with.
UNREACHABLE_DIR = "unreachable.git"
COMMIT_MESSAGE = "candidate work"
QUIET = "-q"
# The two files under a checkout's own git directory that git writes when
# somebody works in the tree.
INDEX_FILE = "index"
HEAD_REFLOG = "logs/HEAD"
# The file inside that directory pointing back at the tree, which is what
# `worktree list` follows to report the worktree at all.
WORKTREE_BACKLINK = "gitdir"


class _CandidateWorld(_ArtifactWorld):
    """A clone, the bare remote it has pushed its base to, and its checkouts.

    The remote is a repository rather than a tracking ref, because that is the
    distinction under test: an agent shares the clone's object store and can
    move any `refs/remotes/...` in it, so a fixture that only wrote tracking
    refs would prove the tampering it is meant to catch is undetectable.
    """

    def prepare(self, test_case) -> None:
        """Redirect the worktrees root and own this world's teardown."""
        super().prepare(test_case)
        self.remote = None
        self._serving = contextlib.ExitStack()
        test_case.addCleanup(self._serving.close)

    def serve(self, spec: _config_models.RepoSpec) -> Path:
        """Give this repository a remote it has already pushed its base to.

        The authenticated transport is pointed at that bare repository for the
        rest of the test, so every read the classification takes over it --
        `ls-remote` and the token resolution and the transport-config refusal
        in front of it -- runs for real against something that answers.
        """
        self.remote = self._served(spec, REMOTE_DIR)
        return self.remote

    def serve_beside(self, spec: _config_models.RepoSpec, name: str) -> Path:
        """Give a second repository sharing this clone a remote of its own.

        A remote is the one thing two `REPOS` entries over a single checkout do
        not share, so a case about what a shared clone's branches belong to
        needs both of them answering: a fixture serving one would prove only
        that the other could not be reached.

        The world's own `remote` stays the first one, since that is what its
        publications are spelled against -- what this hands back is the second
        repository's, for a case that has to reach into it directly.
        """
        return self._served(spec, name)

    def unreachable(self, spec: _config_models.RepoSpec) -> Path:
        """Point this repository's transport at a remote that is not there.

        What an `ls-remote` that establishes nothing looks like without
        breaking anything else in the envelope: the token still resolves, the
        argv is still hardened, and the command still runs -- against a path
        no repository was ever created at.
        """
        self.remote = self.path(UNREACHABLE_DIR)
        self._serving.enter_context(
            _SESSIONS.registered(spec.slug, str(self.remote)),
        )
        return self.remote

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
            _revision(root, f"{start}^{{tree}}"),
            "-p", _revision(root, start),
            "-m", f"{COMMIT_MESSAGE} on {branch}",
            cwd=root,
        )
        tip = (made.stdout or "").strip()
        _branch_at(root, branch, tip)
        return tip

    def publish(
        self,
        root: Path,
        branch: str,
        revision: str,
        *,
        remote: Path | None = None,
    ) -> str:
        """Push `revision` onto the remote's `branch`, as a publication does.

        The world's own remote unless a case names another, which is what a
        shared clone's second repository needs: the two entries publish to two
        different hosts under names that are otherwise identical.
        """
        pushed = _revision(root, revision)
        _run_git(
            "push", QUIET, str(remote or self.remote),
            f"{pushed}:refs/heads/{branch}",
            cwd=root,
        )
        return pushed

    def unpublish(self, root: Path, branch: str) -> None:
        """Delete `branch` on the remote, as merging a pull request does."""
        _run_git(
            "push", QUIET, str(self.remote), "--delete",
            f"refs/heads/{branch}",
            cwd=root,
        )

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
            "worktree", "add", QUIET, str(worktree), branch,
            cwd=spec.target_root,
        )
        return worktree

    def _served(self, spec: _config_models.RepoSpec, name: str) -> Path:
        """One bare repository, wired to this repository's authenticated calls."""
        remote = self.path(name)
        remote.mkdir()
        _run_git("init", "--bare", QUIET, "-b", BASE_BRANCH, cwd=remote)
        self._serving.enter_context(
            _SESSIONS.registered(spec.slug, str(remote)),
        )
        self.publish(
            spec.target_root, BASE_BRANCH, BASE_BRANCH, remote=remote,
        )
        return remote


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
    _run_git("init", QUIET, "-b", BASE_BRANCH, cwd=worktree)
    return worktree
