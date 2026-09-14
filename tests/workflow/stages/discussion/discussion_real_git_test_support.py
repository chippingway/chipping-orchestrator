# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The repositories the discussion stage's object-level tests are run against.

Two of this stage's checks are only as good as the object store behind them:
the base a round pins is spent on a local diff, and the ancestry a publication
judges a remote head by is a local command over local objects. Both take an id
the REMOTE named, so what they are really about is the gap between an id and
the commit it stands for -- and a mock can only show that a fetch was asked
for. So those tests build real repositories: an upstream standing in for
GitHub, a clone of it, and a linked worktree sharing its store.

The two token-bearing calls are what connect them. `_remote_branch_tip` and
`_authed_target_fetch` are the only places this stage reaches the network, so
each test redirects them at the upstream over a path and everything they hand
back is real -- real objects, a real refspec, a real store the worktree reads
from.

The base branch and slug are spelled here rather than taken from the hermetic
fixtures, because these modules build their own world: what has to agree is the
branch the upstream carries and the branch the spec names, and nothing here
depends on the values every mocked tick is seeded with.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from orchestrator.config import models as _config_models

GIT_COMMAND = "git"
QUIET_FLAG = "-q"
MESSAGE_FLAG = "-m"
BASE_BRANCH = "main"
REPO_SLUG = "chippingway/orchestrator"
SEED_FILE = "seed"
SEED_TEXT = "x\n"
UPSTREAM_DIR = "upstream"
CLONE_DIR = "clone"
PLAN_TEXT = "# the plan\n"
AUTHOR = "t"
AUTHOR_EMAIL = "t@t"
FETCH_FAILURE = 128


def _git(cwd: Path, *args: str) -> str:
    """Run one git command in `cwd` and return its stdout.

    None of these commands reads the developer's own git configuration: the
    identity comes from the environment, and global and system config are
    detached, so a signing key or commit template on the host cannot decide
    whether the commits this world is built from happen at all.
    """
    completed = subprocess.run(
        [GIT_COMMAND, *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": AUTHOR,
            "GIT_AUTHOR_EMAIL": AUTHOR_EMAIL,
            "GIT_COMMITTER_NAME": AUTHOR,
            "GIT_COMMITTER_EMAIL": AUTHOR_EMAIL,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        },
    )
    return completed.stdout


def _commit_file(repo: Path, path: str, text: str) -> str:
    """Write one file in `repo`, commit it, and return the commit's SHA."""
    target = repo / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", QUIET_FLAG, MESSAGE_FLAG, path)
    return _git(repo, "rev-parse", "HEAD").strip()


def _real_git_spec(root: Path) -> _config_models.RepoSpec:
    """The spec whose clone and upstream both live under `root`."""
    return _config_models.RepoSpec(
        slug=REPO_SLUG,
        target_root=root / CLONE_DIR,
        base_branch=BASE_BRANCH,
    )


def _failed_fetch(spec, branch: str) -> subprocess.CompletedProcess:
    """An authenticated fetch that reaches nothing and says so."""
    return subprocess.CompletedProcess(
        args=[GIT_COMMAND], returncode=FETCH_FAILURE, stdout="", stderr="",
    )


def _fetch_upstream(spec, branch: str) -> subprocess.CompletedProcess:
    """Fetch `branch` the way the authenticated target fetch does.

    Same refspec and same destination -- the clone whose object store the
    worktree shares -- reached over a path rather than through a token. The
    upstream stands beside that clone, so the spec names it as well.
    """
    upstream = spec.target_root.parent / UPSTREAM_DIR
    _git(
        spec.target_root, "fetch", QUIET_FLAG, str(upstream),
        f"+refs/heads/{branch}:refs/remotes/{spec.remote_name}/{branch}",
    )
    return subprocess.CompletedProcess(args=[GIT_COMMAND], returncode=0)


def _seed_upstream_clone(
    spec: _config_models.RepoSpec, upstream: Path, worktree: Path, branch: str,
) -> str:
    """Build an upstream on its base branch, a clone, and one checkout.

    Returns the base commit both start from -- the tip the clone was taken at,
    which is what a round measured against it is pinned to.
    """
    clone = spec.target_root
    upstream.mkdir(parents=True)
    _git(upstream, "init", QUIET_FLAG, "-b", BASE_BRANCH, ".")
    base_sha = _commit_file(upstream, SEED_FILE, SEED_TEXT)
    _git(clone.parent, "clone", QUIET_FLAG, str(upstream), str(clone))
    _git(
        clone, "worktree", "add", QUIET_FLAG, "-b", branch, str(worktree),
    )
    return base_sha
