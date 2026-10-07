# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The workflow's per-tick base refresh: its fetch, its walk, and the gates in front of a route."""
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

from orchestrator.config import models as _config_models
from orchestrator.workflow.engine import base_refresh
from tests.git.base_sync.sync_test_support import _git_result, _patch_base_sync
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.support.writer_claims import held_elsewhere
from tests.workflow.engine.refresh_checkouts_support import (
    AFTER_SHA,
    ONE_PUBLICATION,
    ROUND_BEFORE,
    Checkouts,
    Walked,
    observed,
    pr_of,
    seed_open_pr,
)

ISSUE = 7
SLUG = "acme/widget"
BASE_BRANCH = "main"
LABEL_IMPLEMENTING = "workflow:implementing"
LABEL_VALIDATING = "workflow:validating"

# Multi-remote spec exercised by the per-spec authed-fetch regression.
PRIVATE_SLUG = "acme/widget-private"
PRIVATE_BASE_BRANCH = "cache-main"
PRIVATE_REMOTE = "private"

UP_TO_DATE_STDOUT = "0\n"
TWO_BEHIND_STDOUT = "2\n"
GIT_FAILURE_EXIT_CODE = 128
MISSING_ISSUE_NUMBER = 9999
FETCH_COMMAND = "fetch"

# An issue whose worktree sits beside a held one's, which nothing holds.
FREE_ISSUE = 8


class _ActiveIn:
    """A scheduler whose workers are still running the issues named."""

    def __init__(self, *numbers: int) -> None:
        self.active = set(numbers)

    def is_active(self, _repo: str, issue_number: int) -> bool:
        return issue_number in self.active


class RefreshBaseAndWorktreesTest(unittest.TestCase):
    """Per-tick fetch and worktree discovery. Real-git integration coverage
    lives in ``tests/git/base_sync/test_real_git.py``.
    """

    def setUp(self) -> None:
        self.tmpdir = Path(tempfile.mkdtemp(prefix="orch-refresh-unit-"))
        self.addCleanup(shutil.rmtree, str(self.tmpdir), ignore_errors=True)
        self.target_root = self.tmpdir / "target"
        self.target_root.mkdir()
        self.spec = _config_models.RepoSpec(
            slug=SLUG,
            target_root=self.target_root,
            base_branch=BASE_BRANCH,
        )
        self.gh = FakeGitHubClient()

    def test_returns_early_when_base_fetch_fails(self) -> None:
        fetch_fail = MagicMock(return_value=_git_result(returncode=1, stderr="boom"))
        sync = MagicMock()
        with _patch_base_sync(target_fetch=fetch_fail, sync=sync):
            base_refresh._refresh_base_and_worktrees(self.gh, self.spec)
        sync.assert_not_called()

    def test_returns_early_without_worktree_root(self) -> None:
        fetch_ok = MagicMock(return_value=_git_result())
        sync = MagicMock()
        with _patch_base_sync(
            target_fetch=fetch_ok,
            worktrees_root=MagicMock(return_value=self.tmpdir / "missing"),
            sync=sync,
        ):
            base_refresh._refresh_base_and_worktrees(self.gh, self.spec)
        sync.assert_not_called()

    def test_iterates_only_issue_dirs(self) -> None:
        wt_root = self.tmpdir / "worktrees"
        wt_root.mkdir()
        # Two valid issue worktrees, one decompose dir (skipped), one stray
        # file (skipped), one malformed (skipped).
        (wt_root / "issue-7").mkdir()
        (wt_root / "issue-42").mkdir()
        (wt_root / "decompose-7").mkdir()
        (wt_root / "issue-bogus").mkdir()
        (wt_root / "stray.txt").write_text("x")

        fetch_ok = MagicMock(return_value=_git_result())
        sync = MagicMock()
        with _patch_base_sync(
            target_fetch=fetch_ok,
            worktrees_root=MagicMock(return_value=wt_root),
            sync=sync,
        ):
            base_refresh._refresh_base_and_worktrees(self.gh, self.spec)

        called_numbers = sorted(recorded_call.args[3] for recorded_call in sync.call_args_list)
        self.assertEqual(called_numbers, [7, 42])

    def test_per_worktree_exception_is_swallowed(self) -> None:
        wt_root = self.tmpdir / "worktrees"
        wt_root.mkdir()
        (wt_root / "issue-1").mkdir()
        (wt_root / "issue-2").mkdir()
        fetch_ok = MagicMock(return_value=_git_result())
        sync = MagicMock(side_effect=[RuntimeError("kaboom"), None])
        with _patch_base_sync(
            target_fetch=fetch_ok,
            worktrees_root=MagicMock(return_value=wt_root),
            sync=sync,
        ):
            base_refresh._refresh_base_and_worktrees(self.gh, self.spec)
        # Both worktrees attempted despite the first raising.
        self.assertEqual(sync.call_count, 2)

    def test_a_held_issue_is_passed_over(self) -> None:
        # Another poller holds #7, so the walk neither reads it nor rebases
        # its checkout, and goes on to rebase #8's.
        wt_root = self.tmpdir / "worktrees"
        for number in (ISSUE, FREE_ISSUE):
            (wt_root / f"issue-{number}").mkdir(parents=True)
            self.gh.add_issue(make_issue(number, label=LABEL_IMPLEMENTING))
        spied = patch.object(self.gh, "get_issue", wraps=self.gh.get_issue)
        reads = self.enterContext(spied)
        rebase = MagicMock(return_value=(True, []))

        with held_elsewhere(self.gh.repo_id, ISSUE), _patch_base_sync(
            target_fetch=MagicMock(return_value=_git_result()),
            worktrees_root=MagicMock(return_value=wt_root),
            dirty=MagicMock(return_value=[]),
            git=MagicMock(return_value=_git_result(stdout=TWO_BEHIND_STDOUT)),
            rebase=rebase,
        ):
            base_refresh._refresh_base_and_worktrees(self.gh, self.spec)

        self.assertEqual(reads.call_args_list, [call(FREE_ISSUE)])
        rebase.assert_called_once()
        self.assertEqual(rebase.call_args.args[1], wt_root / f"issue-{FREE_ISSUE}")

    def test_base_fetch_uses_per_spec_authed_helper(self) -> None:
        # The base refresh must go through `_authed_target_fetch` (which
        # resolves the per-spec token and uses the spec's `remote_name`
        # for refs/remotes/<remote_name>/<branch>), NOT plain
        # `_git("fetch", ...)`. Without this, a multi-remote spec where
        # `remote_name != origin` falls back to the ambient git
        # credential helper -- which fails under systemd with
        # `terminal prompts disabled`.
        private_spec = _config_models.RepoSpec(
            slug=PRIVATE_SLUG,
            target_root=self.target_root,
            base_branch=PRIVATE_BASE_BRANCH,
            remote_name=PRIVATE_REMOTE,
        )
        fetch = MagicMock(return_value=_git_result())
        plain_git = MagicMock(return_value=_git_result())

        with _patch_base_sync(
            target_fetch=fetch,
            git=plain_git,
            worktrees_root=MagicMock(return_value=self.tmpdir / "missing"),
        ):
            base_refresh._refresh_base_and_worktrees(self.gh, private_spec)

        self.assertEqual(
            fetch.call_args_list,
            [call(private_spec, PRIVATE_BASE_BRANCH)],
            "base refresh must route through `_authed_target_fetch` with the spec's base branch",
        )
        # No plain-git fetch was issued -- otherwise the multi-remote
        # token-selection regression resurfaces.
        for call_args in plain_git.call_args_list:
            args = call_args.args
            self.assertNotEqual(
                args[0] if args else "",
                FETCH_COMMAND,
                f'plain `_git("fetch", ...)` leaked: {args!r}',
            )


class ActiveIssueRefreshTest(unittest.TestCase):
    """An issue the scheduler's worker is still running is left to that worker."""

    def setUp(self) -> None:
        self.spec = _config_models.RepoSpec(
            slug=SLUG, target_root=Path("/tmp/refresh-target"), base_branch=BASE_BRANCH,
        )
        self.gh = FakeGitHubClient()
        for number in (ISSUE, FREE_ISSUE):
            seed_open_pr(self.gh, number)
        self.checkouts = Checkouts(self, ISSUE, FREE_ISSUE)
        self.scheduler = _ActiveIn(ISSUE)

    def test_an_active_issue_waits_for_its_worker(self) -> None:
        # While the worker runs #7 the walk neither reads it nor rewrites its
        # pull request, and publishes #8's all the same; the walk after the
        # worker exits publishes #7 and leaves #8, already carried over, alone.
        record = self.gh.pinned_data(ISSUE)
        spied = patch.object(self.gh, "get_issue", wraps=self.gh.get_issue)
        reads = self.enterContext(spied)

        self._walked()

        self.assertEqual(reads.call_args_list, [call(FREE_ISSUE)])
        self.assertEqual(self.gh.pinned_data(ISSUE), record)
        self.assertEqual(observed(self.gh, self.checkouts), Walked(
            rebased=[FREE_ISSUE],
            published={FREE_ISSUE: ONE_PUBLICATION},
            relabelled=[(FREE_ISSUE, LABEL_VALIDATING)],
            noticed=[pr_of(FREE_ISSUE)],
            announced={FREE_ISSUE: [AFTER_SHA]},
            rounds={ISSUE: ROUND_BEFORE, FREE_ISSUE: 0},
        ))

        self.scheduler.active.clear()
        self._walked()

        self.assertEqual(observed(self.gh, self.checkouts), Walked(
            rebased=[FREE_ISSUE, ISSUE],
            published={FREE_ISSUE: ONE_PUBLICATION, ISSUE: ONE_PUBLICATION},
            relabelled=[(FREE_ISSUE, LABEL_VALIDATING), (ISSUE, LABEL_VALIDATING)],
            noticed=[pr_of(FREE_ISSUE), pr_of(ISSUE)],
            announced={FREE_ISSUE: [AFTER_SHA], ISSUE: [AFTER_SHA]},
            rounds={ISSUE: 0, FREE_ISSUE: 0},
        ))

    def _walked(self) -> None:
        """One refresh over both checkouts, asking the scheduler before each."""
        with self.checkouts.walked():
            base_refresh._refresh_base_and_worktrees(self.gh, self.spec, scheduler=self.scheduler)


class SyncWorktreeWithBaseTest(unittest.TestCase):
    """The per-worktree gates that end a sync before any rewrite runs."""

    def setUp(self) -> None:
        self.spec = _config_models.RepoSpec(
            slug=SLUG,
            target_root=Path("/tmp/refresh-target"),
            base_branch=BASE_BRANCH,
        )
        self.wt = Path("/tmp/refresh-wt")
        self.gh = FakeGitHubClient()
        self.gh.add_issue(make_issue(ISSUE, label=LABEL_IMPLEMENTING))

    def test_skips_dirty_worktree(self) -> None:
        rebase = MagicMock()
        with _patch_base_sync(
            dirty=MagicMock(return_value=["a.py"]),
            rebase=rebase,
        ):
            base_refresh._sync_worktree_with_base(self.gh, self.spec, self.wt, ISSUE)
        rebase.assert_not_called()

    def test_skips_when_already_up_to_date(self) -> None:
        rebase = MagicMock()
        git_mock = MagicMock(return_value=_git_result(stdout=UP_TO_DATE_STDOUT))
        with _patch_base_sync(
            dirty=MagicMock(return_value=[]),
            git=git_mock,
            rebase=rebase,
        ):
            base_refresh._sync_worktree_with_base(self.gh, self.spec, self.wt, ISSUE)
        rebase.assert_not_called()

    def test_skips_when_rev_list_fails(self) -> None:
        rebase = MagicMock()
        git_mock = MagicMock(return_value=_git_result(returncode=GIT_FAILURE_EXIT_CODE))
        with _patch_base_sync(
            dirty=MagicMock(return_value=[]),
            git=git_mock,
            rebase=rebase,
        ):
            base_refresh._sync_worktree_with_base(self.gh, self.spec, self.wt, ISSUE)
        rebase.assert_not_called()

    def test_missing_issue_is_swallowed(self) -> None:
        # An orphan worktree (issue deleted on GitHub side, or fetch error)
        # must not crash the refresh -- skip silently.
        rebase = MagicMock()
        with _patch_base_sync(rebase=rebase):
            base_refresh._sync_worktree_with_base(
                self.gh, self.spec, self.wt, MISSING_ISSUE_NUMBER,
            )
        rebase.assert_not_called()


if __name__ == "__main__":
    unittest.main()
