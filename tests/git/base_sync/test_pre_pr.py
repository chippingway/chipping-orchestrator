# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.config import models as _config_models
from orchestrator.git.base_sync import pre_pr
from tests.git.base_sync.sync_test_support import _git_result, _patch_base_sync

ISSUE = 7
SLUG = "acme/widget"
BASE_BRANCH = "main"
BASE_REF = "origin/main"
BEHIND = 3

REBASE_COMMAND = "rebase"
ABORT_FLAG = "--abort"
GIT_FAILURE_EXIT_CODE = 128
CONFLICTED_STDOUT = "src/feature.py\n\ntests/foo.py\n"
REBASE_MERGE_DIR = "rebase-merge"
REBASE_APPLY_DIR = "rebase-apply"

_SPEC = _config_models.RepoSpec(
    slug=SLUG,
    target_root=Path("/tmp/pre-pr-target"),
    base_branch=BASE_BRANCH,
)
_WORKTREE = Path("/tmp/pre-pr-wt")


class RebaseBaseIntoWorktreeTest(unittest.TestCase):
    """The hardened rebase and the conflicted-path list it reports."""

    def test_clean_rebase_reports_no_conflicts(self) -> None:
        hardened = MagicMock(return_value=_git_result())
        with _patch_base_sync(hardened=hardened):
            outcome = pre_pr._rebase_base_into_worktree(_SPEC, _WORKTREE)
        self.assertEqual(outcome, (True, []))
        # The rebase targets the spec's remote-tracking base ref, and the
        # unmerged-path diff is not run when there is nothing to read.
        self.assertEqual(
            [recorded.args for recorded in hardened.call_args_list],
            [(REBASE_COMMAND, BASE_REF)],
        )

    def test_conflicted_rebase_lists_unmerged_paths(self) -> None:
        hardened = MagicMock(
            side_effect=[
                _git_result(returncode=1),
                _git_result(stdout=CONFLICTED_STDOUT),
            ],
        )
        with _patch_base_sync(hardened=hardened):
            succeeded, conflicted = pre_pr._rebase_base_into_worktree(
                _SPEC, _WORKTREE,
            )
        self.assertFalse(succeeded)
        # Blank lines are dropped, so an empty list keeps its meaning:
        # the rebase failed for a reason no agent can resolve.
        self.assertEqual(conflicted, ["src/feature.py", "tests/foo.py"])

    def test_non_conflict_failure_reports_empty_list(self) -> None:
        hardened = MagicMock(
            side_effect=[_git_result(returncode=1), _git_result()],
        )
        with _patch_base_sync(hardened=hardened):
            outcome = pre_pr._rebase_base_into_worktree(_SPEC, _WORKTREE)
        self.assertEqual(outcome, (False, []))

    def test_merge_alias_forwards_to_the_rebase(self) -> None:
        rebase = MagicMock(return_value=(True, []))
        with _patch_base_sync(rebase=rebase):
            outcome = pre_pr._merge_base_into_worktree(_SPEC, _WORKTREE)
        self.assertEqual(outcome, (True, []))
        rebase.assert_called_once_with(_SPEC, _WORKTREE)


class RebaseInProgressTest(unittest.TestCase):
    """Whether a worktree still sits mid-rebase, per git's own state dirs."""

    def setUp(self) -> None:
        self.worktree = Path(tempfile.mkdtemp(prefix="orch-pre-pr-"))
        self.addCleanup(shutil.rmtree, str(self.worktree), ignore_errors=True)

    def test_relative_state_path_joins_the_worktree(self) -> None:
        # `git rev-parse --git-path` answers relative to the worktree for a
        # linked checkout, so the probe has to join before it stats.
        (self.worktree / REBASE_MERGE_DIR).mkdir()
        self.assertTrue(self._probe(REBASE_MERGE_DIR))

    def test_absolute_state_path_is_used_as_given(self) -> None:
        state_dir = self.worktree / REBASE_APPLY_DIR
        state_dir.mkdir()
        self.assertTrue(self._probe(str(state_dir)))

    def test_missing_state_dir_reports_no_rebase(self) -> None:
        self.assertFalse(self._probe(REBASE_MERGE_DIR))

    def test_unreadable_git_path_reports_no_rebase(self) -> None:
        for git_path_result in (
            _git_result(returncode=GIT_FAILURE_EXIT_CODE),
            _git_result(stdout="\n"),
        ):
            with self.subTest(returncode=git_path_result.returncode), _patch_base_sync(
                hardened=MagicMock(return_value=git_path_result),
            ):
                self.assertFalse(
                    pre_pr._rebase_in_progress(self.worktree),
                )

    def _probe(self, git_path_stdout: str) -> bool:
        with _patch_base_sync(
            hardened=MagicMock(
                return_value=_git_result(stdout=f"{git_path_stdout}\n"),
            ),
        ):
            return pre_pr._rebase_in_progress(self.worktree)


class SyncPrePrWorktreeTest(unittest.TestCase):
    """The local-only rebase: nothing is pushed, so failure just aborts."""

    def test_clean_rebase_issues_no_abort(self) -> None:
        rebase = MagicMock(return_value=(True, []))
        hardened = MagicMock(return_value=_git_result())
        with _patch_base_sync(rebase=rebase, hardened=hardened):
            pre_pr._sync_pre_pr_worktree(_SPEC, _WORKTREE, ISSUE, BEHIND)
        rebase.assert_called_once()
        hardened.assert_not_called()

    def test_failed_rebase_aborts_once(self) -> None:
        # Both failure shapes -- conflicted paths and a bare failure --
        # put the worktree back on its original SHA with one abort.
        for conflicted_files in ([], ["a.py", "b.py"]):
            with self.subTest(conflicted=len(conflicted_files)):
                hardened = MagicMock(return_value=_git_result())
                with _patch_base_sync(
                    rebase=MagicMock(return_value=(False, conflicted_files)),
                    hardened=hardened,
                ):
                    pre_pr._sync_pre_pr_worktree(
                        _SPEC, _WORKTREE, ISSUE, BEHIND,
                    )
                self.assertEqual(
                    [recorded.args for recorded in hardened.call_args_list],
                    [(REBASE_COMMAND, ABORT_FLAG)],
                )


if __name__ == "__main__":
    unittest.main()
