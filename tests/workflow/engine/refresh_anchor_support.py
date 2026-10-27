# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real checkout at an issue's layout path with an interrupted refresh anchor pinned over it.

The anchor says a base rebase started over the issue's branch and nothing
recorded how it ended, so the refresh hands the checkout to its recovery,
whose reset takes whatever the tree holds. What the tree is decides whether
that recovery may run: the checkout an interrupted rebase of the issue's own
branch leaves, detached mid-replay, or a tree somebody switched onto the flat
branch since -- before the pass, or while its fetch runs. The remote cannot be
read, which is the recovery's reset-and-park road.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.git.worktrees import naming, paths
from orchestrator.workflow.engine import base_refresh
from tests.support.fakes import FakeGitHubClient, FakePR, make_issue

ISSUE = 7
PR_NUMBER = 42
FOREIGN_FILE = "foreign.txt"
BASE_FILE = "base.txt"

_LABEL = "workflow:validating"
_BASE = "main"
_HEAD = "HEAD"
_REMOTE_BASE = "refs/remotes/origin/main"
_PLAN = "plan.md"
_IDENTITY = ("-c", "user.name=Review", "-c", "user.email=review@example.invalid")
_ADD_WORKTREE = ("worktree", "add")
_SWITCH = ("checkout", "-q")

_UNREACHABLE = subprocess.CompletedProcess(["git", "fetch"], 1, "", "remote unavailable")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _commits(checkout: Path, name: str, text: str) -> None:
    (checkout / name).write_text(text)
    _git(checkout, "add", name)
    _git(checkout, *_IDENTITY, "commit", "-q", "-m", f"change {name}")


def _anchored_at(github: FakeGitHubClient, branch: str, anchor: str) -> None:
    """Pin `anchor` with the terms every attempt records in its own write: its pull request and stage."""
    github.seed_state(
        ISSUE, branch=branch, pr_number=PR_NUMBER,
        pending_auto_base_rebase_push_sha=anchor,
        pending_auto_base_rebase_rewrite_pr=PR_NUMBER,
        pending_auto_base_rebase_rewrite_stage=_LABEL,
    )


def _seeded_clone(target: Path, branch: str) -> str:
    """A clone whose base and issue branch both stand on one commit, which it returns."""
    target.mkdir()
    _git(target, "init", "-b", _BASE)
    _git(target, *_IDENTITY, "commit", "--allow-empty", "-m", "base")
    _git(target, "update-ref", _REMOTE_BASE, _HEAD)
    _git(target, "branch", branch, _HEAD)
    return _git(target, "rev-parse", branch)


def behind_its_base(world, *, pr_number: int | None = PR_NUMBER) -> str:
    """Put the issue's own checkout a commit ahead of a base that moved on, with no anchor; its head.

    The record names the issue's branch, and the pull request `pr_number`
    names where that pull request stands -- or, with None, no pull request
    at all, the pre-PR refresh's road.
    """
    world.on_its_branch()
    _commits(world.checkout, "work.txt", "Issue work\n")
    head = world.head()
    _commits(world.target, BASE_FILE, "Advanced base\n")
    _git(world.target, "update-ref", _REMOTE_BASE, _HEAD)
    if pr_number is None:
        world.gh.seed_state(ISSUE, branch=world.branch)
    else:
        world.gh.seed_state(ISSUE, branch=world.branch, pr_number=pr_number)
        world.gh.get_pr(pr_number).head.sha = head
    return head


class AnchoredCheckout:
    """The clone, the checkout at the issue's path, and the issue whose anchor names the branch tip."""

    def __init__(self, case) -> None:
        root = Path(case.enterContext(tempfile.TemporaryDirectory(prefix="orch-anchor-")))
        case.enterContext(patch.object(config, "WORKTREES_DIR", root / "worktrees"))
        self.target = root / "clone"
        self.spec = config.RepoSpec("acme/widget", self.target, _BASE)
        self.branch = naming._branch_name(self.spec, ISSUE)
        self.checkout = paths._worktree_path(self.spec, ISSUE)
        self.checkout.parent.mkdir(parents=True)
        tip = _seeded_clone(self.target, self.branch)
        self.gh = FakeGitHubClient()
        self.gh.add_issue(make_issue(ISSUE, label=_LABEL))
        pull_request = FakePR(number=PR_NUMBER, head_branch=self.branch)
        pull_request.head.sha = tip
        self.gh.add_pr(pull_request)
        _anchored_at(self.gh, self.branch, tip)

    def on_its_branch(self) -> None:
        """The issue's own checkout, on its branch at the anchored tip."""
        _git(self.target, *_ADD_WORKTREE, str(self.checkout), self.branch)

    def switched_to_the_flat_branch(self) -> None:
        """A checkout on `orchestrator/issue-<n>`, carrying a commit of its own -- switched there where one stands."""
        flat = f"orchestrator/issue-{ISSUE}"
        if self.checkout.exists():
            _git(self.checkout, *_SWITCH, "-b", flat)
        else:
            _git(self.target, *_ADD_WORKTREE, "-b", flat, str(self.checkout), _BASE)
        _commits(self.checkout, FOREIGN_FILE, "Foreign work must survive.\n")

    def left_mid_rebase(self) -> None:
        """The issue's own checkout, detached in the middle of rebasing its branch.

        The branch and the base each change one line, so the rebase stops on
        the conflict with the issue's branch named as the one it rewrites.
        """
        _git(self.target, *_ADD_WORKTREE, str(self.checkout), self.branch)
        _commits(self.checkout, _PLAN, "the branch's line\n")
        _git(self.checkout, *_SWITCH, "--detach", _BASE)
        _commits(self.checkout, _PLAN, "the base's line\n")
        _git(self.checkout, "update-ref", _REMOTE_BASE, _HEAD)
        _git(self.checkout, *_SWITCH, self.branch)
        _anchored_at(self.gh, self.branch, self.head())
        subprocess.run(
            ["git", *_IDENTITY, "rebase", "origin/main"], cwd=self.checkout,
            check=False, capture_output=True,
        )

    def head(self) -> str:
        return _git(self.checkout, "rev-parse", _HEAD)

    def standing(self) -> tuple:
        """The checkout's head and the issue's record, as one reading."""
        return self.head(), self.gh.pinned_data(ISSUE)

    def syncs(self, during_the_fetch=None) -> None:
        """One refresh pass over the checkout, with the remote unreachable.

        `during_the_fetch` is called with each fetch's arguments before it
        fails, and answers `mock.DEFAULT` to let that failure through.
        """
        fetch = MagicMock(side_effect=during_the_fetch, return_value=_UNREACHABLE)
        with patch.object(branch_transport, "_authed_fetch", fetch):
            base_refresh._sync_worktree_with_base(self.gh, self.spec, self.checkout, ISSUE)
