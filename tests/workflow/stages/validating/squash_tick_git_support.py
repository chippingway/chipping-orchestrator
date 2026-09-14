# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real per-issue checkout, at the path a validating tick derives for one.

The seam a stage test usually stands in for is the one a squash recovery has
most at stake in: the WORKTREE. So this builds it -- a bare remote, the parent
clone every worktree of it is added from, and a genuine `git worktree` under
the configured worktrees root, on the branch a reviewer approved.

The path matters as much as the repository. What the stage looks for is
`_worktree_path(spec, issue)`, and what an ordinary preparation does to a
checkout carrying no commits over its base is remove it -- so a fixture that
handed the owner some other directory would answer a question nobody asks.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from orchestrator import config
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming, paths as _worktree_paths
from orchestrator.observability.analytics import settings as _analytics_settings

ISSUE_NUMBER = 9

PR_NUMBER = 77

BASE_BRANCH = "main"

REMOTE_NAME = "origin"

REPO_SLUG = "chippingway/orchestrator"

# What the topic branch adds over the base, one file per commit -- and the
# count a record of collapsing them claims.
APPROVED_COMMITS = ("fix: the first", "feat: the second", "chore: the third")

# The two surfaces a tick writes its events to, which a fixture points at its
# own directory so a test leaves nothing on the host's.
_EVENT_SURFACES = ("ANALYTICS_LOG_PATH", "TRAJECTORY_LOG_PATH")

# Who every object this fixture writes is authored by: a checkout with no
# identity configured has none to inherit, and git will not invent one.
_AUTHOR = MappingProxyType({
    "GIT_AUTHOR_NAME": "Dev",
    "GIT_AUTHOR_EMAIL": "dev@example.com",
    "GIT_COMMITTER_NAME": "Dev",
    "GIT_COMMITTER_EMAIL": "dev@example.com",
})


def run_git(*args: str, cwd: Path, env_extra: dict | None = None) -> str:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd), capture_output=True, text=True, env=env, check=True,
    ).stdout


@dataclass(frozen=True)
class ApprovedCheckout:
    """One issue's checkout, standing where a reviewer's approval left it.

    `accepted` is the head the approval was given on -- the commit a squash
    collapses and the head its push is leased against -- and `base` the fork
    point it was read over. Both are read off the objects, so a case asserting
    on them is asserting about the repository rather than about a seed.
    """

    spec: _config_models.RepoSpec
    branch: str
    path: Path
    accepted: str
    base: str

    def head(self) -> str:
        """The commit this checkout is standing on, right now."""
        return run_git("rev-parse", "HEAD", cwd=self.path).strip()

    def staged(self) -> list[str]:
        """The paths the index carries over HEAD, which is a made collapse."""
        listed = run_git("diff", "--cached", "--name-only", cwd=self.path)
        return [line for line in listed.splitlines() if line.strip()]

    def rewinds_onto_the_base(self) -> None:
        """Rewind the branch with the collapse staged, as the squash does.

        The half of the rewrite that lands first: HEAD is the base, so the
        checkout carries nothing over it, and every change the squash is about
        is in the index waiting for the commit that never came.
        """
        run_git(
            "reset", "--soft", f"{REMOTE_NAME}/{BASE_BRANCH}", cwd=self.path,
        )


class ApprovedCheckoutMixin:
    """Build the repository, the checkout, and the paths a stage derives."""

    def build_checkout(self) -> ApprovedCheckout:
        tmpdir = Path(self.enterContext(tempfile.TemporaryDirectory(
            prefix="orch-collapse-tick-", ignore_cleanup_errors=True,
        )))
        self.enterContext(patch.object(
            config, "WORKTREES_DIR", tmpdir / "worktrees",
        ))
        for surface in _EVENT_SURFACES:
            self.enterContext(patch.object(
                _analytics_settings, surface, tmpdir / f"{surface}.jsonl",
            ))
        spec = _config_models.RepoSpec(
            slug=REPO_SLUG,
            target_root=tmpdir / "target",
            base_branch=BASE_BRANCH,
        )
        branch = _naming._branch_name(spec, ISSUE_NUMBER)
        self._seeds_the_base(spec, tmpdir)
        self._seeds_the_branch(spec, branch)
        path = self._adds_the_worktree(spec, branch)
        return ApprovedCheckout(
            spec=spec,
            branch=branch,
            path=path,
            accepted=run_git("rev-parse", "HEAD", cwd=path).strip(),
            base=run_git(
                "rev-parse", f"{REMOTE_NAME}/{BASE_BRANCH}", cwd=path,
            ).strip(),
        )

    def _seeds_the_base(self, spec: _config_models.RepoSpec, tmpdir: Path) -> None:
        """A bare remote and the parent clone every worktree is added from."""
        remote = tmpdir / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", "-b", BASE_BRANCH, str(remote)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "clone", str(remote), str(spec.target_root)],
            check=True, capture_output=True,
        )
        (spec.target_root / "README.md").write_text("hello\n")
        self._commits(spec.target_root, "initial", "README.md")
        run_git("push", REMOTE_NAME, BASE_BRANCH, cwd=spec.target_root)

    def _seeds_the_branch(self, spec: _config_models.RepoSpec, branch: str) -> None:
        """The commits a reviewer approved, published and then stepped off.

        The parent clone is left on the base so the branch is free for the
        worktree below, and fetched so that checkout reads the base ref the
        same way a tick does.
        """
        target = spec.target_root
        run_git("checkout", "-b", branch, cwd=target)
        for index, subject in enumerate(APPROVED_COMMITS, start=1):
            (target / f"f{index}.txt").write_text(f"{index}\n")
            self._commits(target, subject, f"f{index}.txt")
        run_git("push", REMOTE_NAME, branch, cwd=target)
        run_git("checkout", BASE_BRANCH, cwd=target)
        run_git("fetch", REMOTE_NAME, cwd=target)

    def _adds_the_worktree(self, spec: _config_models.RepoSpec, branch: str) -> Path:
        """The per-issue checkout, at the path the stage derives for it."""
        path = _worktree_paths._worktree_path(spec, ISSUE_NUMBER)
        path.parent.mkdir(parents=True, exist_ok=True)
        run_git(
            "worktree", "add", str(path), branch, cwd=spec.target_root,
        )
        return path

    def _commits(self, worktree: Path, message: str, path: str) -> None:
        run_git("add", path, cwd=worktree)
        run_git("commit", "-m", message, cwd=worktree, env_extra=_AUTHOR)
