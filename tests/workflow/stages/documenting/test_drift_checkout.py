# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The checkout a documenting drift unwind resets, over a real clone.

The unwind hard-resets and cleans the tree at the issue's path onto the pull
request's head, so it is made only in a checkout proven the issue's own. One
standing on the flat branch -- carrying an operator's commit, edits, and
notes -- refuses the unwind before its notice, and one switched onto that
branch while the issue's branch is fetched refuses before the reset, each
with its head, its files, the label, and the record exactly as they were.
One switched while the reset itself runs refuses before the clean behind it,
with the files the switched tree carries in place, nothing handed back, and
the pending unwind left on the record.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.git import branch_transport, commands
from orchestrator.git.worktrees import naming, paths
from orchestrator.workflow.stages.documenting import handler
from tests.support.fakes import FakeGitHubClient, FakePR, make_issue
from tests.support.git import _run_git
from tests.workflow import verified_approvals as _verified

ISSUE = 7
PR_NUMBER = 42
DOCUMENTING = "workflow:documenting"
_BASE = "main"
_FLAT_BRANCH = f"orchestrator/issue-{ISSUE}"
_TRACKED = "tracked.txt"
_NOTES = "notes.txt"
_EDITS = "operator edits\n"
_PUBLISHED = "base\n"
_EDITED_BODY = "the requirements, edited since the approval"
_SWITCHED_NOTE = "switched-checkout-note.txt"
_RESET = ("reset", "--hard")
_ADD_WORKTREE = ("worktree", "add", "-q", "-b")

# What every fetch of the issue's branch answers here: it landed.
_LANDED = MagicMock(returncode=0, stdout="", stderr="")


def _approved(github: FakeGitHubClient, issue, **fields) -> dict:
    """Seed `issue`'s record of `fields` on its pull request, under the approval the hop entered on; the record.

    The approval records the requirements as they stand, so an edit to the
    body after it is the drift the unwind answers.
    """
    github.seed_state(ISSUE, pr_number=PR_NUMBER, **fields)
    _verified.verifies_the_approval(github, issue)
    return github.pinned_data(ISSUE)


def _published_clone(clone: Path) -> None:
    """Initialize `clone` with the one commit its pull request's head stands on."""
    clone.mkdir()
    _run_git("init", "-q", "-b", _BASE, cwd=clone)
    (clone / _TRACKED).write_text(_PUBLISHED)
    _run_git("add", ".", cwd=clone)
    _run_git("commit", "-qm", "base", cwd=clone)


def _switched_after(step: tuple[str, ...], through, checkout: Path, *, noted: bool = True):
    """`through`, switching `checkout` onto the flat branch -- with a note, where `noted` -- behind the first `step`."""

    def wrapper(*args, **kwargs):
        answer = through(*args, **kwargs)
        called = args[:len(step)]
        switched = _run_git("branch", "--list", _FLAT_BRANCH, cwd=checkout).stdout.strip()
        if called == step and not switched:
            _run_git("checkout", "-q", "-b", _FLAT_BRANCH, cwd=checkout)
            if noted:
                (checkout / _SWITCHED_NOTE).write_text("operator work on the switched checkout\n")
        return answer
    return wrapper


def _head_of(checkout: Path) -> str:
    """The commit `checkout` stands on."""
    return _run_git("rev-parse", "HEAD", cwd=checkout).stdout.strip()


class DriftCheckoutTest(unittest.TestCase):
    """A drift unwind over the tree at the issue's path, against a pull request on its current branch."""

    def setUp(self) -> None:
        root = Path(self.enterContext(tempfile.TemporaryDirectory(prefix="orch-docs-drift-")))
        self.enterContext(patch.object(config, "WORKTREES_DIR", root / "worktrees"))
        self.enterContext(patch.object(branch_transport, "_authed_fetch", return_value=_LANDED))
        clone = root / "clone"
        _published_clone(clone)
        self.spec = config.RepoSpec("acme/widget", clone, _BASE)
        self.branch = naming._branch_name(self.spec, ISSUE)
        _run_git("update-ref", f"refs/remotes/origin/{self.branch}", "HEAD", cwd=clone)
        self.checkout = paths._worktree_path(self.spec, ISSUE)
        self.checkout.parent.mkdir(parents=True)
        self.gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=DOCUMENTING)
        self.gh.add_issue(self.issue)
        self.gh.add_pr(FakePR(number=PR_NUMBER, head_branch=self.branch))

    def test_the_issue_s_own_checkout_is_reset(self) -> None:
        self._worked_on(self.branch)
        _approved(self.gh, self.issue, branch=self.branch)
        self.issue.body = _EDITED_BODY

        handler._handle_documenting(self.gh, self.spec, self.issue)

        self.assertEqual((self.checkout / _TRACKED).read_text(), _PUBLISHED)
        self.assertFalse((self.checkout / _NOTES).exists())
        self.assertEqual(self.gh.workflow_label(self.issue), "workflow:validating")

    def test_a_flat_checkout_announces_nothing(self) -> None:
        before = self._worked_on(_FLAT_BRANCH)
        recorded = _approved(self.gh, self.issue, branch=self.branch)
        self.issue.body = _EDITED_BODY

        self.assertRaises(naming.BranchRefused, handler._handle_documenting, self.gh, self.spec, self.issue)

        self._assert_kept(before, recorded)
        self.assertEqual(self.gh.posted_comments, [])

    def test_a_switch_during_the_fetch_resets_nothing(self) -> None:
        # Switched while the issue's branch is fetched -- over an operator's
        # work the reset would discard, or over a tree already in sync and
        # clean, which would otherwise complete the unwind and hand the
        # switched tree back to review: refused, with the label and the
        # pending unwind as they were.
        for worked in (True, False):
            with self.subTest(worked=worked):
                self.setUp()
                if worked:
                    before = self._worked_on(self.branch)
                else:
                    clone = self.spec.target_root
                    _run_git(*_ADD_WORKTREE, self.branch, str(self.checkout), _BASE, cwd=clone)
                recorded = _approved(self.gh, self.issue, branch=self.branch, docs_drift_unwind_pending=True)
                fetched = _switched_after((), MagicMock(return_value=_LANDED), self.checkout, noted=worked)
                with patch.object(branch_transport, "_authed_fetch", side_effect=fetched):
                    self.assertRaises(naming.BranchRefused, handler._handle_documenting, self.gh, self.spec, self.issue)

                if worked:
                    self._assert_kept(before, recorded)
                self.assertEqual(self.gh.workflow_label(self.issue), DOCUMENTING)
                self.assertEqual(self.gh.pinned_data(ISSUE), recorded)

    def test_a_switch_during_the_reset_cleans_nothing(self) -> None:
        # The tree is switched onto the flat branch, with a note of its own,
        # while the reset runs. The clean behind it would delete that note, so
        # the checkout is proven again first: nothing is cleaned or handed
        # back, and the unwind is still pending for the restored checkout.
        self._worked_on(self.branch)
        recorded = _approved(self.gh, self.issue, branch=self.branch, docs_drift_unwind_pending=True)
        hardened = _switched_after(_RESET, commands._git_hardened, self.checkout)

        with patch.object(commands, "_git_hardened", side_effect=hardened):
            self.assertRaises(naming.BranchRefused, handler._handle_documenting, self.gh, self.spec, self.issue)

        self.assertTrue((self.checkout / _SWITCHED_NOTE).exists())
        self.assertEqual(self.gh.workflow_label(self.issue), DOCUMENTING)
        self.assertEqual(self.gh.pinned_data(ISSUE), recorded)

    def _worked_on(self, branch: str) -> str:
        """Stand a worktree on a new `branch` at the issue's path, worked on by an operator; its head."""
        added = (*_ADD_WORKTREE, branch)
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
