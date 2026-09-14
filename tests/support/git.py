# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hermetic git subprocesses shared across workflow and git integration tests."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from orchestrator.config import models as _config_models


def _git_env() -> dict:
    """Hermetic git env: detached from the operator's global / system
    config and with a deterministic author/committer so the test does
    not depend on the host's `~/.gitconfig`."""
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_AUTHOR_NAME": "orchestrator-test",
        "GIT_AUTHOR_EMAIL": "orchestrator-test@example.invalid",
        "GIT_COMMITTER_NAME": "orchestrator-test",
        "GIT_COMMITTER_EMAIL": "orchestrator-test@example.invalid",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _run_git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env=_git_env(),
    )


def _seed_target_root(td: Path) -> tuple[Path, str]:
    """Initialize a temp git repo to serve as `spec.target_root`.

    Creates an initial empty commit on `main` and an `origin/main`
    remote-tracking ref pointing at it, mirroring the shape of a
    freshly-cloned repo just after `_authed_target_fetch`. Returns
    `(target_root, base_sha)` so tests can branch from it.
    """
    target = td / "target"
    target.mkdir()
    _run_git("init", "-q", "-b", "main", cwd=target)
    _run_git(
        "commit",
        "--allow-empty",
        "-q",
        "-m",
        "init",
        cwd=target,
    )
    base_sha = _run_git(
        "rev-parse",
        "HEAD",
        cwd=target,
    ).stdout.strip()
    _run_git(
        "update-ref",
        "refs/remotes/origin/main",
        base_sha,
        cwd=target,
    )
    return target, base_sha


def _spec_for(target_root: Path) -> _config_models.RepoSpec:
    return _config_models.RepoSpec(
        slug="orch/realgit",
        target_root=target_root,
        base_branch="main",
        remote_name="origin",
    )
