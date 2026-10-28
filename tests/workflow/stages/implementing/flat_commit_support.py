# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A real clone whose checkout at the issue's path stands on the flat branch, carrying an oversized commit.

The tree a quiet recovery of committed work meets when somebody switched the
issue's checkout onto the flat `orchestrator/issue-<n>` and committed there.
The commit is what such a recovery would measure, and past a one-line ceiling
with decomposition on, the size gate records it as the issue's candidate and
hands it to an adjudication, so a recovery that has not admitted the checkout
first is seen moving the label and the record. The remote names the base for
the branch, which is what the gate's reading is taken over.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git import branch_transport, ref_transport
from orchestrator.git.worktrees import naming, paths
from orchestrator.workflow.engine import content_hash
from orchestrator.workflow.stages.implementing import handler
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.git import _run_git, _seed_target_root

ISSUE = 7
_FOREIGN_FILE = "foreign.txt"
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"


def _commits_on_the_flat_branch(spec) -> str:
    """Stand a worktree on the flat branch at the issue's path, carrying an oversized commit; that commit."""
    checkout = paths._worktree_path(spec, ISSUE)
    checkout.parent.mkdir(parents=True)
    added = ("worktree", "add", "-q", "-b", _FLAT_BRANCH)
    _run_git(*added, str(checkout), spec.base_branch, cwd=spec.target_root)
    (checkout / _FOREIGN_FILE).write_text("foreign work\n" * 5)
    _run_git("add", _FOREIGN_FILE, cwd=checkout)
    _run_git("commit", "-q", "-m", "foreign work", cwd=checkout)
    return _run_git("rev-parse", "HEAD", cwd=checkout).stdout.strip()


class FlatCommitWorld:
    """The clone, the flat checkout's commit over the base, and the issue on `workflow:implementing`."""

    def __init__(self, case) -> None:
        root = Path(case.enterContext(tempfile.TemporaryDirectory(prefix="orch-flat-commit-")))
        case.enterContext(patch.object(config, "WORKTREES_DIR", root / "worktrees"))
        case.enterContext(patch.object(config, "DECOMPOSE", True))
        case.enterContext(patch.object(config, "MAX_ADDED_LINES", 1))
        target, base = _seed_target_root(root)
        self.base = base
        landed = ref_transport._RefRead(sha=base)
        case.enterContext(patch.object(branch_transport, "_remote_branch_read", return_value=landed))
        self.spec = config.RepoSpec("acme/widget", target, "main")
        self.issue = make_issue(ISSUE, label="workflow:implementing")
        self.gh = FakeGitHubClient()
        self.gh.add_issue(self.issue)
        self.candidate = _commits_on_the_flat_branch(self.spec)

    def seeds(self, **pinned: object) -> None:
        """Pin the issue's current branch and its requirements baseline, with `pinned` beside them."""
        baseline = content_hash._compute_user_content_hash(self.issue, set())
        record = {"branch": naming._branch_name(self.spec, ISSUE), "user_content_hash": baseline, **pinned}
        self.gh.seed_state(ISSUE, **record)

    def refuses(self, case) -> None:
        """One implementing tick raises `BranchRefused`, with the record, the label, and the thread as they were."""
        recorded = self.gh.pinned_data(ISSUE)

        with case.assertRaises(naming.BranchRefused):
            handler._handle_implementing(self.gh, self.spec, self.issue)

        case.assertEqual(self.gh.pinned_data(ISSUE), recorded)
        case.assertEqual((self.gh.label_history, self.gh.posted_comments), ([], []))
