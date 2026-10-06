# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A pull request branch on a real remote, rebased cleanly onto a moved base.

The clone, the bare remote, the rebase, and the authenticated transport the
rewrite is read and published through are all real: only the askpass session
is pointed at the bare repository on disk instead of at GitHub, so the
hardened push, its lease, and the remote read run as they do in production.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from types import MappingProxyType

from orchestrator.config import models as _config_models
from orchestrator.git.base_sync import (
    pre_pr as _pre_pr,
    rewrite_facts as _rewrite_facts,
)
from orchestrator.git.base_sync.rewrite_handoffs import (
    _RewriteAttempt,
    _RewriteCandidate,
)
from orchestrator.workflow.state import WorkflowLabel
from tests.git.auth_session_test_support import _SESSIONS

SLUG = "acme/rewrite"

BASE_BRANCH = "main"

PR_BRANCH = "orchestrator/acme__rewrite/issue-7"

PR_NUMBER = 42

ORIGIN = "origin"

FEATURE_FILE = "feature.py"

# The base as the clone's remote-tracking ref names it, and the refspec that
# lands the clone's base commits on the remote.
_BASE_REF = f"{ORIGIN}/{BASE_BRANCH}"

_BASE_PUSH = f"HEAD:refs/heads/{BASE_BRANCH}"

# Every commit a fixture writes names its author, so the suite does not lean
# on an identity the machine running it happens to export.
_IDENTITY = MappingProxyType({
    "GIT_AUTHOR_NAME": "Dev",
    "GIT_AUTHOR_EMAIL": "dev@example.com",
    "GIT_COMMITTER_NAME": "Dev",
    "GIT_COMMITTER_EMAIL": "dev@example.com",
    "GIT_TERMINAL_PROMPT": "0",
})


class RewriteRepository:
    """One clone, its bare remote, and an issue worktree a rebase rewrote."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.remote = root / "remote.git"
        self.clone = root / "work"
        self.worktree = root / "worktrees" / "issue-7"
        self.spec = _config_models.RepoSpec(
            slug=SLUG, target_root=self.clone, base_branch=BASE_BRANCH,
        )
        self.anchor = ""

    def git(self, *args: str, cwd: Path) -> str:
        """Run one plain git command and hand back what it printed."""
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            env={**os.environ, **_IDENTITY},
            check=True,
        )
        return completed.stdout.strip()

    def commit(self, cwd: Path, path: str, text: str) -> str:
        """Commit one file in `cwd` and name the commit it made."""
        (cwd / path).write_text(text)
        self.git("add", path, cwd=cwd)
        self.git("commit", "-m", f"add {path}", cwd=cwd)
        return self.head_of("HEAD", cwd)

    def head_of(self, revision: str, cwd: Path) -> str:
        """The commit `revision` names in `cwd`, a bare repository included."""
        return self.git("rev-parse", "--verify", revision, cwd=cwd)

    def advance_base(self) -> str:
        """Land a commit on the remote base and fetch it, as another merge would."""
        # Named after the tip it lands on, so every advance changes something.
        previous = self.head_of("HEAD", self.clone)
        advanced = self.commit(self.clone, "base.txt", f"after {previous}\n")
        self.git("push", ORIGIN, _BASE_PUSH, cwd=self.clone)
        return advanced

    def pushes_a_foreign_commit(self) -> str:
        """Move the remote pull request branch to a commit no rebase here made."""
        foreign = self.git(
            "commit-tree", f"{self.anchor}^{{tree}}", "-p", self.anchor,
            "-m", "pushed from elsewhere", cwd=self.remote,
        )
        self.git("update-ref", f"refs/heads/{PR_BRANCH}", foreign, cwd=self.remote)
        return foreign

    def prepared(self) -> _RewriteCandidate:
        """Read the candidate the rebase left, for the attempt anchored on it."""
        attempt = _RewriteAttempt(
            anchor=self.anchor, pr_number=PR_NUMBER, stage=WorkflowLabel.VALIDATING,
        )
        return _rewrite_facts._prepares_the_candidate(
            self.spec, self.worktree, attempt, PR_BRANCH,
        )


def rewrite_repository(test_case) -> RewriteRepository:
    """Build a pull request branch one base advance behind, and rebase it.

    The rebase is the auto-rebase's own hardened one, run once the advance is
    on the clone's base ref, and the authenticated transport is pointed at the
    bare remote for as long as the test runs.
    """
    root = Path(tempfile.mkdtemp(prefix="orch-rewrite-real-"))
    test_case.addCleanup(shutil.rmtree, str(root), ignore_errors=True)
    repository = _published_behind_its_base(root)
    test_case.enterContext(_SESSIONS.registered(SLUG, str(repository.remote)))
    rebased, conflicted = _pre_pr._rebase_base_into_worktree(
        repository.spec, repository.worktree,
    )
    test_case.assertTrue(rebased, conflicted)
    return repository


def pull_request_head(repository: RewriteRepository) -> str:
    """Where the bare remote itself has the pull request branch.

    Read off the remote's own refs rather than off anything a push reported,
    so a case asserting a landing is asserting what the remote really carries.
    """
    return repository.head_of(f"refs/heads/{PR_BRANCH}", repository.remote)


def _published_behind_its_base(root: Path) -> RewriteRepository:
    """A pull request branch on the remote, and then a base that moved past it.

    The branch is pushed before the base moves, so the remote stands on the
    anchor every rewrite of it is leased against.
    """
    repository = RewriteRepository(root)
    clone = repository.clone
    worktree = repository.worktree
    repository.git("init", "--bare", "-b", BASE_BRANCH, str(repository.remote), cwd=root)
    repository.git("clone", str(repository.remote), str(clone), cwd=root)
    repository.commit(clone, "README.md", "hello\n")
    repository.git("push", ORIGIN, _BASE_PUSH, cwd=clone)
    repository.git("worktree", "add", "-b", PR_BRANCH, str(worktree), _BASE_REF, cwd=clone)
    repository.anchor = repository.commit(worktree, FEATURE_FILE, "feature\n")
    repository.git("push", ORIGIN, PR_BRANCH, cwd=worktree)
    repository.advance_base()
    return repository
