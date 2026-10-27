# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout a documenting drift unwind resets, over a real clone.

The unwind hard-resets and cleans the tree at the issue's path onto the pull
request's head, so it is made only in a checkout proven the issue's own. One
standing on the flat branch -- carrying an operator's commit, edits, and
notes -- refuses the unwind before its notice, and one switched onto that
branch while the issue's branch is fetched refuses before the reset, each
with its head, its files, the label, and the record exactly as they were.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import branch_transport
from orchestrator.git.worktrees import naming, paths
from orchestrator.workflow.engine import content_hash
from orchestrator.workflow.stages.documenting import handler
from tests.support.fakes import FakeGitHubClient, FakePR, make_issue
from tests.support.git import _run_git

ISSUE = 7
PR_NUMBER = 42
DOCUMENTING = "workflow:documenting"
_BASE = "main"
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"
_TRACKED = "tracked.txt"
_NOTES = "notes.txt"
_EDITS = "operator edits\n"
_PUBLISHED = "base\n"


def _earlier_hash() -> str:
    """The requirements hash the reviewer approved, over a body edited since."""
    return content_hash._compute_user_content_hash(make_issue(ISSUE, body="earlier body"), set())


def _published_clone(clone: Path) -> None:
    """Initialize `clone` with the one commit its pull request's head stands on."""
    clone.mkdir()
    _run_git("init", "-q", "-b", _BASE, cwd=clone)
    (clone / _TRACKED).write_text(_PUBLISHED)
    _run_git("add", ".", cwd=clone)
    _run_git("commit", "-qm", "base", cwd=clone)


def _head_of(checkout: Path) -> str:
    """The commit `checkout` stands on."""
    return _run_git("rev-parse", "HEAD", cwd=checkout).stdout.strip()


class DriftCheckoutTest(unittest.TestCase):
    """A drift unwind over the tree at the issue's path, against a pull request on its current branch."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="orch-docs-drift-")))
        self.enterContext(patch.object(config, "WORKTREES_DIR", root / "worktrees"))
        self.enterContext(patch.object(branch_transport, "_authed_fetch", side_effect=self._fetched))
        clone = root / "clone"
        _published_clone(clone)
        self.spec = config.RepoSpec("acme/widget", clone, _BASE)
        self.branch = naming._branch_name(self.spec, ISSUE)
        _run_git("update-ref", f"refs/remotes/origin/{self.branch}", "HEAD", cwd=clone)
        self.checkout = paths._worktree_path(self.spec, ISSUE)
        self.checkout.parent.mkdir(parents=True)
        self.switch_on_fetch = False
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=DOCUMENTING)
        self.gh.add_issue(self.issue)
        self.gh.add_pr(FakePR(number=PR_NUMBER, head_branch=self.branch))

    def test_the_issue_s_own_checkout_is_reset(self) -> None:
        self._worked_on(self.branch)
        self.gh.seed_state(ISSUE, branch=self.branch, pr_number=PR_NUMBER, user_content_hash=_earlier_hash())

        handler._handle_documenting(self.gh, self.spec, self.issue)

        self.assertEqual((self.checkout / _TRACKED).read_text(), _PUBLISHED)
        self.assertFalse((self.checkout / _NOTES).exists())
        self.assertEqual(self.gh.workflow_label(self.issue), "workflow:validating")

    def test_a_flat_checkout_announces_nothing(self) -> None:
        before = self._worked_on(_FLAT_BRANCH)
        self.gh.seed_state(ISSUE, branch=self.branch, pr_number=PR_NUMBER, user_content_hash=_earlier_hash())
        recorded = self.gh.pinned_data(ISSUE)

        self.assertRaises(naming.BranchRefused, handler._handle_documenting, self.gh, self.spec, self.issue)

        self._assert_kept(before, recorded)
        self.assertEqual(self.gh.posted_comments, [])

    def test_a_switch_during_the_fetch_resets_nothing(self) -> None:
        before = self._worked_on(self.branch)
        self.gh.seed_state(
            ISSUE, branch=self.branch, pr_number=PR_NUMBER, docs_drift_unwind_pending=True,
            user_content_hash=content_hash._compute_user_content_hash(self.issue, set()),
        )
        recorded = self.gh.pinned_data(ISSUE)
        self.switch_on_fetch = True

        self.assertRaises(naming.BranchRefused, handler._handle_documenting, self.gh, self.spec, self.issue)

        self._assert_kept(before, recorded)

    def _fetched(self, *_args, **_kwargs) -> MagicMock:
        """A fetch that lands, switching the checkout onto the flat branch first where the case says so."""
        if self.switch_on_fetch:
            _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=self.checkout)
        return MagicMock(returncode=0, stdout="", stderr="")

    def _worked_on(self, branch: str) -> str:
        """Stand a worktree on a new `branch` at the issue's path, worked on by an operator; its head."""
        added = ("worktree", "add", "-q", "-b", branch)
        _run_git(*added, str(self.checkout), _BASE, cwd=self.spec.target_root)
        (self.checkout / _TRACKED).write_text("operator commit\n")
        _run_git("commit", "-qam", "operator work", cwd=self.checkout)
        (self.checkout / _TRACKED).write_text(_EDITS)
        (self.checkout / _NOTES).write_text("operator notes\n")
        return _head_of(self.checkout)

    def _assert_kept(self, head: str, recorded: dict) -> None:
        """The checkout still on `head` with every edit and note, the label and the record unmoved."""
        self.assertEqual(_head_of(self.checkout), head)
        self.assertEqual((self.checkout / _TRACKED).read_text(), _EDITS)
        self.assertTrue((self.checkout / _NOTES).exists())
        self.assertEqual(self.gh.workflow_label(self.issue), DOCUMENTING)
        self.assertEqual(self.gh.pinned_data(ISSUE), recorded)


if __name__ == "__main__":
    unittest.main()
