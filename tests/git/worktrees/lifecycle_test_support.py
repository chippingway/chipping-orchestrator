# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Faked git plumbing and a temp worktrees root for the lifecycle owners."""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git import branch_transport, commands
from orchestrator.git.worktrees import decomposition, paths

BASE_BRANCH = "main"
ORIGIN_REMOTE = "origin"
PRIVATE_REMOTE = "private"
REPO_SLUG = "acme/widget"
TARGET_ROOT = Path("/tmp/orchestrator-test-target-root")
ISSUE_NUMBER = 300
ISSUE_BRANCH = "orchestrator/acme__widget/issue-300"
LEGACY_BRANCH = "orchestrator/issue-300"
FETCH = "fetch"
REV_LIST = "rev-list"
REV_PARSE = "rev-parse"
REMOTE_REFS_PREFIX = "refs/remotes/"
WORKTREE_ADD = ("worktree", "add")
WORKTREE_REMOVE_FORCE = ("worktree", "remove", "--force")

_GitArgs = tuple[str, ...]
_GitCall = tuple[_GitArgs, Path]


def _git_result(
    *, returncode: int = 0, stdout: str = "", stderr: str = "",
) -> MagicMock:
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def _spec(remote_name: str = ORIGIN_REMOTE) -> _config_models.RepoSpec:
    return _config_models.RepoSpec(
        slug=REPO_SLUG,
        target_root=TARGET_ROOT,
        base_branch=BASE_BRANCH,
        remote_name=remote_name,
    )


class _GitRecorder:
    """Answer the probes the lifecycle owners make and record every call.

    `local_branch_present` drives the `rev-parse --verify <branch>` probe
    that decides between attaching to an existing ref and restoring one,
    and `remote_branch_present` the `refs/remotes/...` probe that decides
    which ref a restore anchors on -- both false is the merged PR whose
    branch GitHub deleted, seen from a host with no local ref left.
    `commit_probe` and `worktree_add` let a test hand back the exact
    `rev-list --count` and `worktree add` results a scenario needs.
    """

    def __init__(
        self,
        *,
        local_branch_present: bool = True,
        remote_branch_present: bool = True,
        commit_probe: MagicMock | None = None,
        worktree_add: MagicMock | None = None,
    ) -> None:
        self.calls: list[_GitCall] = []
        self.local_branch_present = local_branch_present
        self.remote_branch_present = remote_branch_present
        self.commit_probe = commit_probe or _git_result()
        self.worktree_add = worktree_add or _git_result()

    def __call__(self, *args: str, cwd: Path) -> MagicMock:
        self.calls.append((args, cwd))
        if args[0] == REV_PARSE:
            return _git_result(returncode=0 if self._ref_present(args) else 1)
        if args[0] == REV_LIST:
            return self.commit_probe
        if args[:2] == WORKTREE_ADD:
            return self.worktree_add
        return _git_result()

    @property
    def worktree_adds(self) -> list[_GitArgs]:
        return [args for args, _cwd in self.calls if args[:2] == WORKTREE_ADD]

    @property
    def worktree_removes(self) -> list[_GitArgs]:
        return [
            args
            for args, _cwd in self.calls
            if args[:3] == WORKTREE_REMOVE_FORCE
        ]

    @property
    def plain_fetches(self) -> list[_GitArgs]:
        """Fetches that bypassed the authenticated helper.

        A plain `git fetch` inherits the ambient credential helper, which
        under systemd has none -- every fetch has to ride the askpass token.
        """
        return [args for args, _cwd in self.calls if args[0] == FETCH]

    def _ref_present(self, args: _GitArgs) -> bool:
        """Which ref was asked about decides which seed answers."""
        if any(arg.startswith(REMOTE_REFS_PREFIX) for arg in args):
            return self.remote_branch_present
        return self.local_branch_present


class _AuthedFetchRecorder:
    """Record the branches handed to the authenticated target-root fetch."""

    def __init__(self) -> None:
        self.branches: list[str] = []

    def __call__(self, _spec_arg: _config_models.RepoSpec, branch: str) -> MagicMock:
        self.branches.append(branch)
        return _git_result()


@dataclass(frozen=True)
class _WorktreeFixture:
    """Recorders plus the temp worktrees root one patched run observes."""

    git: _GitRecorder
    fetches: _AuthedFetchRecorder
    spec: _config_models.RepoSpec

    def plant_issue_worktree(self) -> Path:
        """Leave a per-issue worktree on disk for the creators to find."""
        worktree = paths._worktree_path(self.spec, ISSUE_NUMBER)
        worktree.mkdir(parents=True)
        return worktree

    def plant_decompose_worktree(self) -> Path:
        """Leave a decomposer scratch checkout on disk from a prior run."""
        worktree = decomposition._decompose_worktree_path(
            self.spec, ISSUE_NUMBER,
        )
        worktree.mkdir(parents=True)
        return worktree

    def run(self, ensure, **options) -> Path:
        return ensure(self.spec, ISSUE_NUMBER, **options)


@contextmanager
def _worktree_fixture(
    *, remote_tip: str | None = "", **recorder_options,
) -> Iterator[_WorktreeFixture]:
    """Point the worktrees root at a temp dir and fake the git plumbing.

    The owners bind `git.commands` and `git.branch_transport` directly, so a
    test that has to intercept what they run patches those owners.
    `WORKTREES_DIR` moves so `Path.exists()` answers for
    real -- the reuse decision turns on it.

    `remote_tip` is what the remote itself says about the branch, which is the
    only thing that turns a missing remote-tracking ref into a confirmed
    deletion: `""` is "no such branch", a SHA is "still there and this host
    just could not fetch it", and `None` is a read that failed.
    """
    recorder = _GitRecorder(**recorder_options)
    fetches = _AuthedFetchRecorder()
    with (
        tempfile.TemporaryDirectory(prefix="orch-worktree-") as temp_dir,
        patch.object(config, "WORKTREES_DIR", Path(temp_dir)),
        patch.object(commands, "_git", recorder),
        patch.object(branch_transport, "_authed_target_fetch", fetches),
        patch.object(
            branch_transport, "_remote_branch_tip", return_value=remote_tip,
        ),
    ):
        yield _WorktreeFixture(
            git=recorder, fetches=fetches, spec=_spec(),
        )
