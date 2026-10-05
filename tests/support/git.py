# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Hermetic git subprocesses shared across workflow and git integration tests."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from types import MappingProxyType

from orchestrator.config import models as _config_models

_INIT = "init"

# Git's own test switch for reading every repository as another user's, with
# global and system config detached so no `safe.directory` exception the host
# carries can admit one anyway.
_FOREIGN_OWNER_ENV = MappingProxyType({
    "GIT_TEST_ASSUME_DIFFERENT_OWNER": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
})


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
    _run_git(_INIT, "-q", "-b", "main", cwd=target)
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


def _append_git_config(checkout: Path, config_text: str) -> Path:
    """Append `config_text` to the config of the clone at `checkout`."""
    with (checkout / ".git" / "config").open("a", encoding="utf-8") as config:
        config.write(config_text)
    return checkout


def _claim_work_tree(enclosing: Path, name: str) -> Path:
    """`enclosing/name`, named as its work tree by a repository at `enclosing`.

    Discovery from that directory reaches `enclosing` and reads it as the
    directory's own repository, so the layout tells a check that asks the
    directory's own `.git` from one that lets git look around it. The
    directory itself is left for the caller to create.
    """
    _run_git(_INIT, str(enclosing), cwd=enclosing.parent)
    _run_git("config", "core.worktree", str(enclosing / name), cwd=enclosing)
    return enclosing / name


def _foreign_owner_settings(scratch: Path) -> dict[str, str] | None:
    """Settings under which git refuses every checkout as another user's.

    `None` when the git on this host does not honour the switch: a repository
    made in `scratch` is asked about under the settings, and opening it means
    nothing a test could prove with them.
    """
    probe_repository = scratch / "foreign-owner-probe"
    _run_git(_INIT, str(probe_repository), cwd=scratch)
    opened = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(probe_repository),
        capture_output=True,
        check=False,
        env={**_git_env(), **_FOREIGN_OWNER_ENV},
    )
    return None if opened.returncode == 0 else dict(_FOREIGN_OWNER_ENV)
