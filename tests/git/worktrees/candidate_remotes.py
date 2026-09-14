# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Bare repositories serving the candidate host through authenticated test transports."""
from __future__ import annotations

import contextlib
from pathlib import Path

from orchestrator.config import models as _config_models
from tests.git.auth_session_test_support import _SESSIONS
from tests.git.worktrees import candidate_refs as _candidate_refs
from tests.git.worktrees.artifact_git import BASE_BRANCH
from tests.git.worktrees.artifact_test_support import _ArtifactWorld
from tests.workflow.stages.question.question_real_git_test_support import (
    _run_git,
)

REMOTE_DIR = "remote.git"
# A path nothing was ever cloned from: what a remote that cannot be
# reached looks like to the read every branch proof starts with.
UNREACHABLE_DIR = "unreachable.git"


class _CandidateRemotes(_ArtifactWorld):
    """The remotes a candidate world publishes to and reads independently of local refs."""

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
        pushed = _candidate_refs._revision(root, revision)
        _run_git(
            "push", _candidate_refs.QUIET, str(remote or self.remote),
            f"{pushed}:refs/heads/{branch}",
            cwd=root,
        )
        return pushed

    def unpublish(self, root: Path, branch: str) -> None:
        """Delete `branch` on the remote, as merging a pull request does."""
        _run_git(
            "push", _candidate_refs.QUIET, str(self.remote), "--delete",
            f"refs/heads/{branch}",
            cwd=root,
        )

    def _served(self, spec: _config_models.RepoSpec, name: str) -> Path:
        """One bare repository, wired to this repository's authenticated calls."""
        remote = self.path(name)
        remote.mkdir()
        _run_git("init", "--bare", _candidate_refs.QUIET, "-b", BASE_BRANCH, cwd=remote)
        self._serving.enter_context(
            _SESSIONS.registered(spec.slug, str(remote)),
        )
        self.publish(
            spec.target_root, BASE_BRANCH, BASE_BRANCH, remote=remote,
        )
        return remote
