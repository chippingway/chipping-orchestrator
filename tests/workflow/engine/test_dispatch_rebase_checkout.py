# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A missing checkout under an unanswered rebase, over a real repository.

The refresh walks only the checkouts that exist, and the stage handler that
would recreate a missing one rebuilds it from the local branch -- which, for a
rebase interrupted before its push, is the replay no push has published. What
these pin is the order that leaves: the dispatcher restores the checkout and
runs nothing behind it, and the next refresh is what reaches the recovery,
which publishes the replay under its anchor lease without an agent.

Only the agent spawn is answered by a double on the dispatch path. A hold that
let the tick through would reach the real `validating` handler, recreate the
checkout onto the replay, and spawn the reviewer over it.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from orchestrator.git import branch_transport
from orchestrator.git.base_sync import refresh as _refresh
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import dispatch, usage as _usage
from orchestrator.workflow.state import WorkflowLabel
from tests.git.base_sync.gate_reads_support import _gate_base_reads
from tests.git.base_sync.recovery_git_support import (
    _local_fetch,
    _LocalLeasePush,
)
from tests.git.worktrees import real_git_test_support as _real_git
from tests.support.fakes import FakeGitHubClient, FakePR, FakePRRef, make_issue

ISSUE = 7

PR_NUMBER = 42

VALIDATING = WorkflowLabel.VALIDATING

ANCHOR_KEY = "pending_auto_base_rebase_push_sha"


def _committed(repo, where, filename: str) -> str:
    """Commit one new file where asked, and name the commit it made."""
    (where / filename).write_text(f"{filename}\n")
    _real_git._run_git("add", filename, cwd=where)
    _real_git._run_git(
        "commit", "-m", filename,
        cwd=where, env_extra=_real_git._author_env(),
    )
    return repo.head_of(where)


class RestoredCheckoutTest(unittest.TestCase):
    """An interrupted rebase whose checkout is gone before the next tick."""

    def setUp(self) -> None:
        self._repo = _real_git._RealGitWorktreeRepo()
        self._repo.prepare(self)
        self.spec = self._repo.spec
        self._branch = _worktree_paths._branch_name(self.spec, ISSUE)
        self.checkout = _worktree_paths._worktree_path(self.spec, ISSUE)
        self._rebases_and_loses_the_checkout()
        self.gh = self._interrupted_issue()
        self.agent = MagicMock()
        self.push = _LocalLeasePush()
        for owner, name, replacement in (
            (_usage, "_run_agent_tracked", self.agent),
            (branch_transport, "_authed_fetch", _local_fetch),
            (branch_transport, "_push_branch", self.push),
        ):
            patcher = patch.object(owner, name, replacement)
            patcher.start()
            self.addCleanup(patcher.stop)
        _gate_base_reads(self)

    def test_the_restore_runs_nothing_behind_it(self) -> None:
        dispatch._process_issue(self.gh, self.spec, self.issue)

        self.agent.assert_not_called()
        # The checkout is back, on exactly what the local branch still names.
        self.assertEqual(self._repo.head_of(self.checkout), self._replay)
        self.assertEqual(self.gh.pinned_data(ISSUE)[ANCHOR_KEY], self._anchor)

    def test_the_next_refresh_publishes_the_replay(self) -> None:
        dispatch._process_issue(self.gh, self.spec, self.issue)

        _refresh._sync_worktree_with_base(
            self.gh, self.spec, self.checkout, ISSUE,
        )

        self.assertEqual(self.push.leases, [self._anchor])
        self.assertEqual(self._remote_head(), self._replay)
        self.assertIsNone(self.gh.pinned_data(ISSUE).get(ANCHOR_KEY))
        self.agent.assert_not_called()

    def test_without_an_anchor_the_handler_is_reached(self) -> None:
        # What says the stop above is the anchor's rather than anything else
        # this world could trip a dispatch on.
        state = self.gh.read_pinned_state(self.issue)
        state.set(ANCHOR_KEY, None)
        self.gh.write_pinned_state(self.issue, state)
        reached = MagicMock()

        with patch.object(dispatch, "_call_handler", reached):
            dispatch._process_issue(self.gh, self.spec, self.issue)

        reached.assert_called_once()

    def _rebases_and_loses_the_checkout(self) -> None:
        """Publish the branch, replay it onto an advanced base, lose the tree.

        The checkout is removed the way an operator's cleanup removes one,
        which unregisters it and keeps its branch: the local ref is left
        standing on the replay, and nothing on the remote has it.
        """
        target = self.spec.target_root
        self.checkout.parent.mkdir(parents=True, exist_ok=True)
        _real_git._run_git(
            "worktree", "add", "-b", self._branch, str(self.checkout),
            f"origin/{_real_git.BASE_BRANCH}", cwd=target,
        )
        self._anchor = _committed(self._repo, self.checkout, "feature.py")
        _real_git._run_git("push", "origin", self._branch, cwd=self.checkout)
        _committed(self._repo, target, "sibling.py")
        _real_git._run_git("push", "origin", _real_git.BASE_BRANCH, cwd=target)
        _real_git._run_git("fetch", "origin", cwd=self.checkout)
        _real_git._run_git(
            "rebase", f"origin/{_real_git.BASE_BRANCH}",
            cwd=self.checkout, env_extra=_real_git._author_env(),
        )
        self._replay = self._repo.head_of(self.checkout)
        _real_git._run_git(
            "worktree", "remove", "--force", str(self.checkout), cwd=target,
        )

    def _interrupted_issue(self) -> FakeGitHubClient:
        """The pinned comment and pull request that crash left behind."""
        gh = FakeGitHubClient()
        self.issue = make_issue(ISSUE, label=str(VALIDATING))
        gh.add_issue(self.issue)
        gh.seed_state(
            ISSUE,
            pr_number=PR_NUMBER,
            branch=self._branch,
            pending_auto_base_rebase_push_sha=self._anchor,
            pending_auto_base_rebase_rewrite_sha=self._replay,
            pending_auto_base_rebase_rewrite_pr=PR_NUMBER,
            pending_auto_base_rebase_rewrite_stage=str(VALIDATING),
        )
        gh.add_pr(FakePR(
            number=PR_NUMBER,
            head_branch=self._branch,
            head=FakePRRef(sha=self._anchor),
        ))
        return gh

    def _remote_head(self) -> str:
        return _real_git._run_git(
            "rev-parse", f"refs/heads/{self._branch}",
            cwd=self.spec.target_root.parent / "remote.git",
        ).strip()


if __name__ == "__main__":
    unittest.main()
