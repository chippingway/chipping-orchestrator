# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Per-issue worktree removal and local branch deletion."""

from __future__ import annotations

import contextlib
import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator.git import commands, locks
from orchestrator.git.worktrees import cleanup
from orchestrator.git.worktrees.models import ProbeAnswer
from tests.git.worktrees.lifecycle_test_support import (
    ISSUE_BRANCH,
    ISSUE_NUMBER,
    REV_PARSE,
    WORKTREE_REMOVE_FORCE,
    _git_result,
    _GitArgs,
    _GitRecorder,
    _worktree_fixture,
)

GIT_HELPER = "_git"
LOCK_HELPER = "_target_root_lock"
GIT_BRANCH = "branch"
DELETE_FLAG = "-D"
GIT_FAILURE_STDERR = "fatal: is a worktree"
GIT_MISSING_MESSAGE = "git not found"
QUESTION_PREFIX = "question "


def _failing_delete(*args: str, cwd: Path):
    """Report the local branch as present, then fail the delete itself."""
    if args[0] == REV_PARSE:
        return _git_result()
    return _git_result(returncode=1, stderr=GIT_FAILURE_STDERR)


class _LockProbe:
    """Record the target roots locked and the git argv each hold covered."""

    def __init__(self, recorder: _GitRecorder) -> None:
        self.roots: list[Path] = []
        self.holds: list[list[_GitArgs]] = []
        self._recorder = recorder

    @contextlib.contextmanager
    def __call__(self, target_root: Path):
        self.roots.append(target_root)
        entered = len(self._recorder.calls)
        yield
        self.holds.append(
            [args for args, _cwd in self._recorder.calls[entered:]],
        )


class IssueWorktreeRemovalTest(unittest.TestCase):
    """The checkout has to come down before its branch can be deleted, so
    every terminal path starts here.
    """

    def test_absent_worktree_skips_the_removal(self) -> None:
        # A prior tick, an operator, or a partial cleanup may already have
        # taken the checkout down; asking git to remove it would fail loudly.
        with _worktree_fixture() as fixture:
            cleanup._remove_issue_worktree(fixture.spec, ISSUE_NUMBER)
            self.assertEqual(fixture.git.calls, [])

    def test_an_unproven_checkout_is_left(self) -> None:
        # The removal is forced, so a tree not proven this issue's own -- one
        # on a flat or foreign branch, or one whose identity would not read --
        # keeps every file in it, and git is never asked to remove it.
        for identity in (ProbeAnswer.REFUTED, ProbeAnswer.UNREADABLE):
            with (
                self.subTest(identity=identity),
                _worktree_fixture(checkout_identity=identity) as fixture,
            ):
                planted = fixture.plant_issue_worktree()
                with self.assertLogs(cleanup.log, level="WARNING"):
                    cleanup._remove_issue_worktree(fixture.spec, ISSUE_NUMBER)
                self.assertEqual(fixture.git.calls, [])
                self.assertTrue(planted.exists())

    def test_present_worktree_is_force_removed(self) -> None:
        # The parent clone owns the worktree registration, so the removal
        # runs there rather than inside the agent-writable checkout.
        with _worktree_fixture() as fixture:
            planted = fixture.plant_issue_worktree()
            cleanup._remove_issue_worktree(fixture.spec, ISSUE_NUMBER)
            args, cwd = fixture.git.calls[0]
            self.assertEqual(args, (*WORKTREE_REMOVE_FORCE, str(planted)))
            self.assertEqual(cwd, fixture.spec.target_root)

    def test_failed_removal_logs_the_prefix(self) -> None:
        with _worktree_fixture() as fixture:
            fixture.plant_issue_worktree()
            failure = _git_result(returncode=1, stderr=GIT_FAILURE_STDERR)
            with (
                patch.object(commands, GIT_HELPER, return_value=failure),
                self.assertLogs(cleanup.log, level="WARNING") as logs,
            ):
                cleanup._remove_issue_worktree(
                    fixture.spec, ISSUE_NUMBER, log_prefix=QUESTION_PREFIX,
                )
                logged = "\n".join(logs.output)
            self.assertIn(QUESTION_PREFIX, logged)
            self.assertIn(GIT_FAILURE_STDERR, logged)

    def test_swallows_a_raising_removal(self) -> None:
        # `_git` can raise rather than return non-zero (missing binary,
        # missing target root). The caller has already written its terminal
        # state, so the raise must not escape.
        with _worktree_fixture() as fixture:
            fixture.plant_issue_worktree()
            with (
                patch.object(
                    commands,
                    GIT_HELPER,
                    side_effect=OSError(GIT_MISSING_MESSAGE),
                ),
                self.assertLogs(cleanup.log, level="ERROR"),
            ):
                cleanup._remove_issue_worktree(fixture.spec, ISSUE_NUMBER)


class LocalBranchDeletionTest(unittest.TestCase):
    """Dropping the per-issue branch once nothing has it checked out."""

    def test_absent_branch_skips_the_delete(self) -> None:
        with _worktree_fixture(local_branch_present=False) as fixture:
            cleanup._delete_local_issue_branch(
                fixture.spec, ISSUE_NUMBER, ISSUE_BRANCH,
            )
            self.assertEqual(
                [args[0] for args, _cwd in fixture.git.calls], [REV_PARSE],
            )

    def test_probe_names_the_fully_qualified_head(self) -> None:
        # A bare `--verify <branch>` also resolves a tag or a remote-tracking
        # ref of the same name, which would send `branch -D` after a local
        # head that does not exist.
        with _worktree_fixture() as fixture:
            cleanup._delete_local_issue_branch(
                fixture.spec, ISSUE_NUMBER, ISSUE_BRANCH,
            )
            self.assertIn(
                f"refs/heads/{ISSUE_BRANCH}", fixture.git.calls[0][0],
            )

    def test_present_branch_is_deleted(self) -> None:
        with _worktree_fixture() as fixture:
            cleanup._delete_local_issue_branch(
                fixture.spec, ISSUE_NUMBER, ISSUE_BRANCH,
            )
            args, cwd = fixture.git.calls[-1]
            self.assertEqual(args, (GIT_BRANCH, DELETE_FLAG, ISSUE_BRANCH))
            self.assertEqual(cwd, fixture.spec.target_root)

    def test_failed_delete_is_logged_with_the_branch(self) -> None:
        with _worktree_fixture() as fixture:
            with (
                patch.object(commands, GIT_HELPER, _failing_delete),
                self.assertLogs(cleanup.log, level="WARNING") as logs,
            ):
                cleanup._delete_local_issue_branch(
                    fixture.spec, ISSUE_NUMBER, ISSUE_BRANCH,
                )
                logged = "\n".join(logs.output)
            self.assertIn(ISSUE_BRANCH, logged)
            self.assertIn(GIT_FAILURE_STDERR, logged)

    def test_swallows_a_raising_delete(self) -> None:
        with (
            _worktree_fixture() as fixture,
            patch.object(
                commands,
                GIT_HELPER,
                side_effect=OSError(GIT_MISSING_MESSAGE),
            ),
            self.assertLogs(cleanup.log, level="ERROR"),
        ):
            cleanup._delete_local_issue_branch(
                fixture.spec, ISSUE_NUMBER, ISSUE_BRANCH,
            )


class TargetRootLockTest(unittest.TestCase):
    """Both steps write the parent clone's `.git/config` and `.git/refs`, so
    they take the same per-target_root lock a concurrent `_ensure_worktree`
    does. The branch probe has to share the delete's hold: a worker that
    slipped in between could check the branch back out before `branch -D`
    lands.
    """

    def test_removal_runs_under_the_lock(self) -> None:
        with _worktree_fixture() as fixture:
            planted = fixture.plant_issue_worktree()
            probe = _LockProbe(fixture.git)
            with patch.object(locks, LOCK_HELPER, probe):
                cleanup._remove_issue_worktree(fixture.spec, ISSUE_NUMBER)
            self.assertEqual(probe.roots, [fixture.spec.target_root])
            self.assertEqual(
                probe.holds, [[(*WORKTREE_REMOVE_FORCE, str(planted))]],
            )

    def test_branch_probe_and_delete_share_a_hold(self) -> None:
        with _worktree_fixture() as fixture:
            probe = _LockProbe(fixture.git)
            with patch.object(locks, LOCK_HELPER, probe):
                cleanup._delete_local_issue_branch(
                    fixture.spec, ISSUE_NUMBER, ISSUE_BRANCH,
                )
            self.assertEqual(probe.roots, [fixture.spec.target_root])
            self.assertEqual(
                [args[0] for args in probe.holds[0]], [REV_PARSE, GIT_BRANCH],
            )


if __name__ == "__main__":
    unittest.main()
