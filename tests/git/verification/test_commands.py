# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Sequencing, captured output, and the recorded transcript of a real `VERIFY_COMMANDS` run."""

from __future__ import annotations

import shlex
import subprocess
import unittest
from types import MappingProxyType
from unittest.mock import patch

from orchestrator.git.verification import models, output, process, runner
from tests.git.verification import command_helpers

VERIFY_FAILED = "failed"
VERIFY_OK = "ok"
VERIFY_NOT_RUN = "not_run"
OUTPUT_PAYLOAD_SIZE = 10000
OUTPUT_BUDGET = 4096
PASSING_COMMAND = "true"
TIMEOUT_SECONDS = 60
_EMOJI = "\U0001F642"  # four UTF-8 bytes
_ACCENTED = "\u00e9"  # two UTF-8 bytes
_EMOJI_BUDGET = _EMOJI * (OUTPUT_BUDGET // 4)
_EMOJI_AFTER_CUT = _EMOJI * (OUTPUT_BUDGET // 4 - 1)
_ACCENTED_BUDGET = _ACCENTED * (OUTPUT_BUDGET // 2)
_ACCENTED_AFTER_CUT = _ACCENTED * (OUTPUT_BUDGET // 2 - 1)

# Captured text, and the tail the budget keeps of it. Two trailing bytes past
# a budget of four-byte characters put the cut inside the first of them.
_MULTIBYTE_CASES = MappingProxyType({
    "four-byte characters": (_EMOJI * OUTPUT_BUDGET, _EMOJI_BUDGET),
    "cut inside a four-byte character": (f"{_EMOJI_BUDGET}ab", f"{_EMOJI_AFTER_CUT}ab"),
    "cut inside a two-byte character": (f"{_ACCENTED_BUDGET}!", f"{_ACCENTED_AFTER_CUT}!"),
    "exactly the budget": (_ACCENTED_BUDGET, _ACCENTED_BUDGET),
})


def _rev_parse(worktree, revision: str) -> str:
    return subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", revision],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class RunVerifyCommandsTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """Run each command in order and record transcripts, outcomes, and bounds."""

    def test_empty_commands_record_not_run(self) -> None:
        with patch.object(process, "_spawn_verify_command") as spawn:
            run = runner._run_verify_commands(self.worktree, (), TIMEOUT_SECONDS)
            spawn.assert_not_called()

        self.assertEqual(run.status, VERIFY_NOT_RUN)
        self.assertEqual(
            (run.configured_commands, run.attempted_commands, run.timeout),
            ((), (), TIMEOUT_SECONDS),
        )
        self.assertEqual(
            run.context_revision, models._context_revision((), TIMEOUT_SECONDS),
        )
        # Nothing was tested, so the result names no commit, no tree, and
        # nothing a later reader could take as passing evidence.
        for unset in (run.commit, run.tree_identity, run.command):
            self.assertIsNone(unset)
        self.assertFalse(run.is_reusable)

    def test_passing_run_records_its_transcript(self) -> None:
        cmds = (PASSING_COMMAND, "echo hello", "echo world")
        run = runner._run_verify_commands(self.worktree, cmds, TIMEOUT_SECONDS)

        self.assertEqual(run.status, VERIFY_OK)
        self.assertEqual(
            (run.commit, run.tree_identity),
            (_rev_parse(self.worktree, "HEAD"), _rev_parse(self.worktree, "HEAD^{tree}")),
        )
        self.assertEqual((run.configured_commands, run.timeout), (cmds, TIMEOUT_SECONDS))
        self.assertEqual(
            run.context_revision, models._context_revision(cmds, TIMEOUT_SECONDS),
        )
        self._assert_transcript(run, cmds, ("", "hello", "world"))
        # A passing run names no refusal.
        self.assertEqual((run.command, run.head_after), (None, None))
        self.assertTrue(run.is_reusable)

    def test_nonzero_names_first_failed_command(self) -> None:
        cmds = (PASSING_COMMAND, "sh -c 'echo boom 1>&2; exit 3'", PASSING_COMMAND)
        run = runner._run_verify_commands(self.worktree, cmds, TIMEOUT_SECONDS)
        self.assertEqual(run.status, VERIFY_FAILED)
        self.assertEqual(run.command, cmds[1])
        self.assertEqual(run.exit_code, 3)
        self.assertIn("boom", run.output)
        self.assertEqual(run.configured_commands, cmds)
        self.assertEqual(
            [(ran.command, ran.status) for ran in run.attempted_commands],
            [(cmds[0], VERIFY_OK), (cmds[1], VERIFY_FAILED)],
        )
        self.assertFalse(run.is_reusable)

    def test_output_truncated_and_redacted(self) -> None:
        prefix = "X" * OUTPUT_PAYLOAD_SIZE
        payload = f"{prefix}super_secret_token_123TAIL"
        cmd = f"sh -c 'printf %s {shlex.quote(payload)}; exit 1'"
        with patch.dict("os.environ", {"TEST_SECRET": "super_secret_token_123"}):
            run = runner._run_verify_commands(self.worktree, (cmd,), TIMEOUT_SECONDS)
        self.assertEqual(run.status, VERIFY_FAILED)
        self.assertEqual(len(run.attempted_commands), 1)
        for output_text in (run.output, run.attempted_commands[0].output):
            self.assertNotIn("super_secret_token_123", output_text)
            self.assertIn("***", output_text)
            self.assertIn("TAIL", output_text)
            self.assertLessEqual(len(output_text.encode()), OUTPUT_BUDGET)

    def _assert_transcript(
        self,
        run: models.VerifyResult,
        cmds: tuple[str, ...],
        printed: tuple[str, ...],
    ) -> None:
        ran_commands = tuple(ran.command for ran in run.attempted_commands)
        self.assertEqual(ran_commands, cmds)
        baseline = (run.commit, run.commit, run.tree_identity, run.tree_identity)
        for ran, text in zip(run.attempted_commands, printed, strict=True):
            with self.subTest(command=ran.command):
                self.assertEqual((ran.status, ran.exit_code), (VERIFY_OK, 0))
                self.assertIn(text, ran.output)
                self.assertEqual(
                    (ran.head_before, ran.head_after, ran.tree_before, ran.tree_after),
                    baseline,
                )



class OutputByteBudgetTest(unittest.TestCase):
    """The output budget counts UTF-8 bytes and cuts only between characters."""

    def test_multibyte_output_fits_the_byte_budget(self) -> None:
        for case, (captured, tail) in _MULTIBYTE_CASES.items():
            with self.subTest(case=case):
                kept = output._truncate_verify_output(captured)
                self.assertEqual(kept, tail)
                self.assertLessEqual(len(kept.encode()), OUTPUT_BUDGET)


if __name__ == "__main__":
    unittest.main()
