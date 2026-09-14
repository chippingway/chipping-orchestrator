# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Git doubles and repo specs shared by the publication owner tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.config import models as _config_models

# The probes call the command owner by attribute, so both names patch there.
GIT_HELPER = "_git"
HARDENED_HELPER = "_git_hardened"

WORKTREE = Path("/tmp/orchestrator-test-git-publication")
TARGET_ROOT = Path("/tmp/orchestrator-test-target-root")
DEFAULT_REVISION_RANGE = "origin/main..HEAD"
FEATURE_PREFIX = "feat"


def _spec(
    *,
    base_branch: str = "main",
    remote_name: str = "origin",
) -> _config_models.RepoSpec:
    """Build a spec whose remote and base branch the probes must honor."""
    return _config_models.RepoSpec(
        slug="acme/widget",
        target_root=TARGET_ROOT,
        base_branch=base_branch,
        remote_name=remote_name,
    )


def _git_result(
    *,
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> MagicMock:
    """One canned command-owner return for a scripted sequence of calls."""
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


class _GitRecorder:
    """Command-owner double recording argv and replaying one canned result."""

    def __init__(
        self,
        stdout: str = "",
        *,
        returncode: int = 0,
        stderr: str = "",
    ) -> None:
        self.calls: list[tuple] = []
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr

    def __call__(self, *args, cwd):
        self.calls.append((args, cwd))
        return MagicMock(
            returncode=self.returncode,
            stdout=self.stdout,
            stderr=self.stderr,
        )
