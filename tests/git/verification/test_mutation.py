# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Worktree mutations a verify command leaves behind, seen through a real run."""

from __future__ import annotations

import subprocess
import unittest
from unittest.mock import MagicMock, patch

from orchestrator.agents import processes
from orchestrator.git.verification import probes, process, runner, status as _worktree_status
from tests.git.verification import command_helpers

VERIFY_HEAD_CHANGED = "head_changed"
VERIFY_DIRTY = "dirty"
VERIFY_OK = "ok"
PASSING_COMMAND = "true"
LEFTOVER_FILE = "leftover.txt"
GIT_COMMAND = "git"
WORKTREE_FLAG = "-C"


class VerifyCommandMutationTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """Report verify-time commits, dirty output, and process registration."""

    def test_commit_command_reports_head_change(self) -> None:
        head_before = subprocess.run(
            [GIT_COMMAND, WORKTREE_FLAG, str(self.worktree), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        cmd = (
            "sh -c 'echo VERIFY_AUTO_FIXED > autofix.txt && "
            "git add autofix.txt && "
            'git commit -q -m "chore: verify-time auto-fix"\''
        )
        run = runner._run_verify_commands(self.worktree, (cmd,), 60)
        self._assert_commit_head_change(run, cmd, head_before)

    def test_dirty_result_keeps_command_output(self) -> None:
        cmds = (
            PASSING_COMMAND,
            "sh -c 'echo BUILD_LOG_LINE; touch leftover.txt'",
            PASSING_COMMAND,
        )
        run = runner._run_verify_commands(self.worktree, cmds, 60)
        self._assert_dirty_run(run, cmds)

    def test_tree_mutation_refuses_fail_closed(self) -> None:
        with patch.object(probes, "_tree_sha", side_effect=("tree1", "tree2")):
            run = runner._run_verify_commands(
                self.worktree, (PASSING_COMMAND,), 60,
            )

        self.assertEqual(run.status, VERIFY_HEAD_CHANGED)
        self.assertEqual(len(run.attempted_commands), 1)
        self.assertEqual(run.attempted_commands[0].status, VERIFY_HEAD_CHANGED)
        self.assertFalse(run.is_reusable)

    def test_running_command_registered_for_shutdown(self) -> None:
        proc = MagicMock()
        proc.pid = 4242
        proc.returncode = 0
        seen: dict[str, bool] = {}

        proc.communicate.side_effect = command_helpers.RegisteredCommunicate(proc, seen)
        with (
            patch.object(process.subprocess, "Popen", return_value=proc),
            patch.object(_worktree_status, "_worktree_dirty_files", return_value=[]),
            patch.object(probes, "_head_sha", return_value="sha"),
            patch.object(probes, "_tree_sha", return_value="treesha"),
        ):
            run = runner._run_verify_commands(self.worktree, (PASSING_COMMAND,), 60)

        self.assertEqual(run.status, VERIFY_OK)
        self.assertTrue(
            seen.get("during"),
            "verify child not registered during the run",
        )
        with processes._running_procs_lock:
            self.assertNotIn(proc, processes._running_procs)

    def _assert_commit_head_change(
        self, run: runner._models.VerifyResult, cmd: str, head_before: str,
    ) -> None:
        self.assertEqual(run.status, VERIFY_HEAD_CHANGED)
        self.assertEqual(run.command, cmd)
        self.assertEqual(run.head_before, head_before)
        self.assertNotEqual(run.head_after, head_before)
        self.assertEqual(run.dirty_files, ())
        self.assertEqual(len(run.attempted_commands), 1)
        self.assertEqual(run.attempted_commands[0].status, VERIFY_HEAD_CHANGED)
        self.assertFalse(run.is_reusable)

    def _assert_dirty_run(
        self, run: runner._models.VerifyResult, cmds: tuple[str, ...],
    ) -> None:
        self.assertEqual(run.status, VERIFY_DIRTY)
        self.assertEqual(run.command, cmds[1])
        self.assertEqual(run.exit_code, 0)
        self.assertIn(LEFTOVER_FILE, run.dirty_files)
        self.assertIn("BUILD_LOG_LINE", run.output)
        self.assertEqual(len(run.attempted_commands), 2)
        self.assertEqual(run.attempted_commands[0].status, VERIFY_OK)
        self.assertEqual(run.attempted_commands[1].status, VERIFY_DIRTY)
        self.assertFalse(run.is_reusable)


if __name__ == "__main__":
    unittest.main()
