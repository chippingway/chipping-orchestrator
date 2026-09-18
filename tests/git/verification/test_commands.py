# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Sequencing and captured output of a real `VERIFY_COMMANDS` run."""

from __future__ import annotations

import shlex
import unittest

from orchestrator.git.verification import runner
from tests.git.verification import command_helpers

VERIFY_FAILED = "failed"
VERIFY_OK = "ok"
VERIFY_NOT_RUN = "not_run"
OUTPUT_PAYLOAD_SIZE = 10000
OUTPUT_BUDGET = 4096
PASSING_COMMAND = "true"


class RunVerifyCommandsTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """Run each command in order and report transcripts, outcomes, and bounds."""

    def test_empty_commands_produces_not_run_result(self) -> None:
        run = runner._run_verify_commands(self.worktree, (), 60)
        self.assertEqual(run.status, VERIFY_NOT_RUN)
        self.assertIsNone(run.command)
        self.assertEqual(run.configured_commands, ())
        self.assertEqual(run.attempted_commands, ())
        self.assertFalse(run.is_reusable)
        self.assertTrue(bool(run.commit))
        self.assertTrue(bool(run.tree_identity))

    def test_all_commands_pass_transcript(self) -> None:
        cmds = (PASSING_COMMAND, "echo hello", "echo world")
        run = runner._run_verify_commands(
            self.worktree, cmds, 60, context_revision="rev-12345",
        )
        self._assert_successful_run(run, cmds)
        self._assert_command_transcripts(run.attempted_commands)

    def test_nonzero_names_first_failed_command(self) -> None:
        cmds = (PASSING_COMMAND, "sh -c 'echo boom 1>&2; exit 3'", PASSING_COMMAND)
        run = runner._run_verify_commands(self.worktree, cmds, 60)
        self.assertEqual(run.status, VERIFY_FAILED)
        self.assertEqual(run.command, cmds[1])
        self.assertEqual(run.exit_code, 3)
        self.assertIn("boom", run.output)
        self.assertEqual(len(run.attempted_commands), 2)
        self.assertEqual(run.attempted_commands[0].status, VERIFY_OK)
        self.assertEqual(run.attempted_commands[1].status, VERIFY_FAILED)
        self.assertFalse(run.is_reusable)

    def test_output_truncated_and_redacted(self) -> None:
        prefix = "X" * OUTPUT_PAYLOAD_SIZE
        payload = f"{prefix}super_secret_token_123TAIL"
        cmd = f"sh -c 'printf %s {shlex.quote(payload)}; exit 1'"
        with unittest.mock.patch.dict("os.environ", {"TEST_SECRET": "super_secret_token_123"}):
            run = runner._run_verify_commands(self.worktree, (cmd,), 60)
        self.assertEqual(run.status, VERIFY_FAILED)
        self._assert_redacted_bounded(run.output)
        self.assertEqual(len(run.attempted_commands), 1)
        self._assert_redacted_bounded(run.attempted_commands[0].output)

    def _assert_successful_run(
        self, run: runner._models.VerifyResult, cmds: tuple[str, ...],
    ) -> None:
        self.assertEqual(run.status, VERIFY_OK)
        self.assertEqual(run.configured_commands, cmds)
        self.assertEqual(len(run.attempted_commands), 3)
        self.assertEqual(run.context_revision, "rev-12345")
        self.assertTrue(run.is_reusable)
        self.assertTrue(bool(run.commit))
        self.assertTrue(bool(run.tree_identity))

    def _assert_command_transcripts(
        self, attempted: tuple[runner._models.VerifyCommandOutcome, ...],
    ) -> None:
        self.assertEqual(attempted[0].command, PASSING_COMMAND)
        self.assertEqual(attempted[0].status, VERIFY_OK)
        self.assertEqual(attempted[1].command, "echo hello")
        self.assertIn("hello", attempted[1].output)
        self.assertEqual(attempted[2].command, "echo world")
        self.assertIn("world", attempted[2].output)

    def _assert_redacted_bounded(self, output_text: str) -> None:
        self.assertNotIn("super_secret_token_123", output_text)
        self.assertIn("***", output_text)
        self.assertIn("TAIL", output_text)
        self.assertLessEqual(len(output_text), OUTPUT_BUDGET)


if __name__ == "__main__":
    unittest.main()
