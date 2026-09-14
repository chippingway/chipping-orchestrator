# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clones, checkouts, and specs the local artifact scan is read from.

Real repositories and real directories rather than doubles: what the scan
reads IS a ref store and a directory listing, so a fake of either would only
hand the fixture back. The branch names the tests compare against are spelled
out here instead of derived, so a change to the naming in ``paths`` fails
these tests rather than travelling through them unnoticed.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from orchestrator.config import models as _config_models, settings as config
from orchestrator.git import locks
from orchestrator.git.worktrees import paths
from tests.git.worktrees import artifact_git as _artifact_git

WIDGET_SLUG = "acme/widget"
GADGET_SLUG = "acme/gadget"
STRANGER_SLUG = "stranger/repo"
# Two slugs the sanitizer cannot tell apart: `:` is not ref-safe and becomes
# `_`, so both entries publish under one branch segment.
COLLIDING_SLUGS = ("acme/wid:get", "acme/wid_get")
LIFECYCLE_LOGGER = "orchestrator.worktree_lifecycle"
NOT_A_CHECKOUT = "not a checkout\n"
BROKEN_REF_CONTENT = "not-a-sha\n"
WORKTREES_DIR_NAME = "worktrees"


def _spec(slug: str, target_root: Path) -> _config_models.RepoSpec:
    """A repo spec on one clone, with the fields the scan reads set."""
    return _config_models.RepoSpec(
        slug=slug, target_root=target_root, base_branch=_artifact_git.BASE_BRANCH,
    )


def _namespaced_branch(slug: str, issue_number: int) -> str:
    """The current layout for one issue, written out rather than derived."""
    return f"orchestrator/{slug.replace('/', '__')}/issue-{issue_number}"


def _legacy_branch(issue_number: int) -> str:
    """The flat layout an issue in flight before slug namespacing is on."""
    return f"orchestrator/issue-{issue_number}"


def _worktrees_root(spec: _config_models.RepoSpec) -> Path:
    """Where this spec's per-issue checkouts sit inside the world."""
    return paths._repo_worktrees_root(spec)


def _block_worktrees_root(spec: _config_models.RepoSpec) -> Path:
    """Put a file where this spec's worktrees root belongs.

    Stands in for every root the host will not hand over as a directory:
    unreadable, replaced, mounted away.
    """
    root = _worktrees_root(spec)
    root.parent.mkdir(parents=True, exist_ok=True)
    root.write_text(NOT_A_CHECKOUT)
    return root


def _break_ref(root: Path, name: str) -> Path:
    """Leave a ref file git cannot parse where one branch's name is.

    Written straight into the ref store rather than made with git, because git
    is what has to meet it: a loose ref whose content is not a SHA is skipped
    with a warning on the next listing, which still exits zero and still
    reports every other branch.
    """
    ref = root / ".git" / "refs" / "heads" / name
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(BROKEN_REF_CONTENT)
    return ref


class _ArtifactWorld(_artifact_git._ArtifactGitFixture):
    """A temp-backed host: clones to read refs from, and a worktrees root.

    `WORKTREES_DIR` is redirected at this world for the test's duration, which
    is what makes the derivations in ``paths`` -- and therefore the scan
    reading them back -- land inside the temp tree.
    """

    def __init__(self) -> None:
        self._tmpdir = Path(tempfile.mkdtemp(prefix="orch-artifacts-"))
        self.worktrees = self._tmpdir / WORKTREES_DIR_NAME

    def prepare(self, test_case) -> None:
        locks._TARGET_ROOT_LOCKS.clear()
        test_case.addCleanup(
            shutil.rmtree, str(self._tmpdir), ignore_errors=True,
        )
        worktrees_patch = patch.object(
            config, "WORKTREES_DIR", self.worktrees,
        )
        worktrees_patch.start()
        test_case.addCleanup(worktrees_patch.stop)

    def path(self, name: str) -> Path:
        """A path inside the world, whether or not anything is at it."""
        return self._tmpdir / name
