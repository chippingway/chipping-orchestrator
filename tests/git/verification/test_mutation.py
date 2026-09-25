# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Worktree, HEAD, and tree mutations a verify command leaves behind, seen through a real run."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.agents import processes
from orchestrator.git.verification import probes, process, runner
from tests.git.verification import command_helpers

VERIFY_HEAD_CHANGED = "head_changed"
VERIFY_TREE_CHANGED = "tree_changed"
VERIFY_DIRTY = "dirty"
VERIFY_OK = "ok"
PASSING_COMMAND = "true"
LEFTOVER_FILE = "leftover.txt"
GIT_COMMAND = "git"
WORKTREE_FLAG = "-C"
HEAD = "HEAD"
TREE_OF_HEAD = "HEAD^{tree}"


def _git(worktree, *args: str) -> str:
    return subprocess.run(
        [GIT_COMMAND, WORKTREE_FLAG, str(worktree), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _rev_parse(worktree, revision: str) -> str:
    return _git(worktree, "rev-parse", revision)


def _commit_second(worktree) -> tuple[str, str]:
    """Commit a second file on top of the seed; the first and second commit ids."""
    first = _rev_parse(worktree, HEAD)
    (worktree / "second.txt").write_text("second\n")
    _git(worktree, "add", ".")
    _git(worktree, "commit", "-q", "-m", "second")
    return first, _rev_parse(worktree, HEAD)


class _ReadThenMove:
    """A `_head_sha` that moves HEAD to `target` right after reading `moved_from`."""

    def __init__(self, read_head, moved_from: str, target: str):
        self.read_head = read_head
        self.moved_from = moved_from
        self.target = target

    def __call__(self, worktree):
        sha = self.read_head(worktree)
        if sha == self.moved_from:
            _git(worktree, "reset", "-q", "--soft", self.target)
        return sha


class VerifyCommandMutationTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """Report verify-time commits, tree changes, dirty output, and process registration."""

    def test_commit_command_reports_head_change(self) -> None:
        # Regression: a verify command that runs `git commit` leaves
        # `git status --porcelain` clean and exits 0, so the previous
        # dirty+exit-code-only gate accepted it as "ok". The squash-on-
        # approval + force-push that followed would then publish the
        # unreviewed verify-created commit to the PR branch. Snapshotting
        # HEAD before the loop and refusing any command that moves it
        # closes that hole.
        head_before = _rev_parse(self.worktree, HEAD)

        # Stage and commit a new file inside the verify command itself --
        # exactly the dangerous shape (a verify rule that auto-fixes and
        # commits its own fix).
        cmd = (
            "sh -c 'echo VERIFY_AUTO_FIXED > autofix.txt && "
            "git add autofix.txt && "
            'git commit -q -m "chore: verify-time auto-fix"\''
        )
        run = runner._run_verify_commands(self.worktree, (cmd,), 60)
        self.assertEqual(run.status, VERIFY_HEAD_CHANGED)
        self.assertEqual(run.command, cmd)
        self.assertEqual(run.head_before, head_before)
        self.assertNotEqual(run.head_after, head_before)
        # And the worktree was clean on detection (not the dirty branch).
        self.assertEqual(run.dirty_files, ())
        self.assertEqual(
            [ran.status for ran in run.attempted_commands], [VERIFY_HEAD_CHANGED],
        )
        self.assertFalse(run.is_reusable)

    def test_dirty_result_keeps_command_output(self) -> None:
        # Regression: previously the dirty check ran once at the end of
        # the loop, so a dirty failure always blamed `commands[-1]` and
        # discarded every command's captured output. The fix checks
        # dirtiness AFTER EACH command so the actual command that left
        # the worktree dirty is named, with its own stdout/stderr
        # preserved for the park comment.
        cmds = (
            PASSING_COMMAND,  # clean, exit 0
            "sh -c 'echo BUILD_LOG_LINE; touch leftover.txt'",  # leaves untracked file
            PASSING_COMMAND,  # should never run
        )
        run = runner._run_verify_commands(self.worktree, cmds, 60)
        self.assertEqual(run.status, VERIFY_DIRTY)
        # Named command is the SECOND command (the one that left the
        # tree dirty), NOT `commands[-1]`.
        self.assertEqual(run.command, cmds[1])
        self.assertEqual(run.exit_code, 0)
        # The dirty file lands in `dirty_files`.
        self.assertIn(LEFTOVER_FILE, run.dirty_files)
        # The command's stdout is preserved for the park comment so the
        # operator can triage what the command actually did.
        self.assertIn("BUILD_LOG_LINE", run.output)
        # The transcript ends at the refusal: the third command never ran.
        self.assertEqual(
            [(ran.command, ran.status) for ran in run.attempted_commands],
            [(cmds[0], VERIFY_OK), (cmds[1], VERIFY_DIRTY)],
        )
        self.assertFalse(run.is_reusable)

    def test_running_command_registered_for_shutdown(self) -> None:
        # The shutdown sweep (`agents.processes.terminate_all_running`) only reaches
        # process groups registered in `processes._running_procs`. A verify
        # command must be registered for the lifetime of its run -- otherwise
        # the watchdog's `os._exit` leaves a slow command running and
        # mutating the worktree after the orchestrator has stopped -- and
        # cleared in the `finally` afterward so a finished command does not
        # leak into the registry. The spawn is faked so the registry can be
        # inspected mid-run deterministically, while the git readings around
        # it run against the real worktree.
        proc = MagicMock()
        proc.pid = 4242
        proc.returncode = 0
        seen: dict[str, bool] = {}

        proc.communicate.side_effect = command_helpers.RegisteredCommunicate(proc, seen)
        with patch.object(process, "_spawn_verify_command", return_value=proc):
            run = runner._run_verify_commands(self.worktree, (PASSING_COMMAND,), 60)

        self.assertEqual(run.status, VERIFY_OK)
        self.assertTrue(
            seen.get("during"),
            "verify child not registered during the run",
        )
        with processes._running_procs_lock:
            self.assertNotIn(proc, processes._running_procs)


class VerifyIdentityReadingTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """Record HEAD and tree exactly as read, bound to the commit the run tested."""

    def test_unread_head_after_is_kept_as_read(self) -> None:
        # A HEAD that could not be read after the command is recorded as the
        # "" the read returned, not papered over with the baseline.
        run, _ = self._run_with_after_reading("_head_sha", "")
        self.assertEqual(
            (run.status, run.head_after, run.tree_after), (VERIFY_HEAD_CHANGED, "", ""),
        )

    def test_tree_read_apart_under_same_head(self) -> None:
        # HEAD staying put while its tree reads differently -- or not at all
        # -- is a tree change, not a HEAD that moved.
        for after in ("", "other-tree"):
            with self.subTest(tree_after=after):
                run, (head, _) = self._run_with_after_reading("_tree_sha", after)
                self.assertEqual(
                    (run.status, run.head_after, run.tree_after),
                    (VERIFY_TREE_CHANGED, head, after),
                )

    def test_baseline_tree_comes_from_the_read_commit(self) -> None:
        # HEAD moving between the two baseline reads must not pair one
        # commit with another commit's tree: the tree is resolved from the
        # commit id just read, and the moved HEAD then fails the clean check.
        first, second = _commit_second(self.worktree)
        mover = _ReadThenMove(probes._head_sha, moved_from=second, target=first)
        with patch.object(probes, "_head_sha", side_effect=mover):
            run = runner._run_verify_commands(self.worktree, (PASSING_COMMAND,), 60)

        self.assertEqual(
            (run.commit, run.tree_identity),
            (second, _rev_parse(self.worktree, f"{second}^{{tree}}")),
        )
        self.assertEqual((run.status, run.attempted_commands), (VERIFY_DIRTY, ()))
        self.assertFalse(run.is_reusable)

    def test_planted_replacement_keeps_recorded_tree(self) -> None:
        # `refs/replace` has a plain read serve the first commit's tree under
        # the second commit's id; the recorded tree is the second's own.
        first, second = _commit_second(self.worktree)
        real_tree = _rev_parse(self.worktree, TREE_OF_HEAD)
        _git(self.worktree, "replace", second, first)
        self.assertNotEqual(_rev_parse(self.worktree, TREE_OF_HEAD), real_tree)

        run = runner._run_verify_commands(self.worktree, (PASSING_COMMAND,), 60)

        self.assertEqual(run.status, VERIFY_OK)
        self.assertEqual((run.commit, run.tree_identity), (second, real_tree))
        self.assertTrue(run.is_reusable)

    def _run_with_after_reading(self, probe: str, after: str):
        baseline = (_rev_parse(self.worktree, HEAD), _rev_parse(self.worktree, TREE_OF_HEAD))
        before = baseline[0] if probe == "_head_sha" else baseline[1]
        with patch.object(probes, probe, side_effect=(before, after)):
            run = runner._run_verify_commands(self.worktree, (PASSING_COMMAND,), 60)
        self.assertEqual((run.head_before, run.tree_before), baseline)
        self.assertEqual([ran.status for ran in run.attempted_commands], [run.status])
        self.assertFalse(run.is_reusable)
        return run, baseline


if __name__ == "__main__":
    unittest.main()
