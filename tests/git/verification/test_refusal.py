# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed refusals: unknown HEAD baselines and skipped later commands."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.git.verification import probes, runner
from tests.git.verification import command_helpers

VERIFY_HEAD_CHANGED = "head_changed"
VERIFY_FAILED = "failed"
VERIFY_OK = "ok"
PASSING_COMMAND = "true"
HEAD_SHA = "_head_sha"
SKIPPED_MARKER = "third_command_ran.txt"


class UnreadableHeadBaselineTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """An unreadable HEAD baseline is compared as "", not waived.

    `_head_sha` returns "" for an uninitialized repo or a failed
    `git rev-parse`, so HEAD stability cannot be proven from it. A command
    that then produces a HEAD is indistinguishable from a missing baseline
    unless the empty snapshot is carried into the comparison, so the runner
    accepts only an unchanged "" and refuses anything else.
    """

    def test_head_after_empty_baseline_refuses(self) -> None:
        with patch.object(probes, HEAD_SHA, side_effect=("", "cafe1234")):
            run = runner._run_verify_commands(
                self.worktree, (PASSING_COMMAND,), 60,
            )

        self.assertEqual(run.status, VERIFY_HEAD_CHANGED)
        self.assertEqual(run.head_before, "")
        self.assertEqual(run.head_after, "cafe1234")

    def test_empty_baseline_that_stays_empty_passes(self) -> None:
        with patch.object(probes, HEAD_SHA, side_effect=("", "")):
            run = runner._run_verify_commands(
                self.worktree, (PASSING_COMMAND,), 60,
            )

        self.assertEqual(run.status, VERIFY_OK)


class FailFastSequencingTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """The first refusal ends the run; later commands never execute."""

    def test_later_commands_skipped_on_refusal(self) -> None:
        # The gate is "everything passed", and the operator only needs the
        # first failure to triage -- so a command after the failing one must
        # not touch the worktree the park comment describes.
        marker = self.worktree / SKIPPED_MARKER
        run = runner._run_verify_commands(
            self.worktree,
            (PASSING_COMMAND, "sh -c 'exit 4'", f"touch {marker}"),
            60,
        )

        self.assertEqual(run.status, VERIFY_FAILED)
        self.assertEqual(run.exit_code, 4)
        self.assertFalse(
            marker.exists(),
            f"command after the refusal still ran; {marker} was created",
        )


class UnreadableTreeIdentityTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """An unreadable tree identity refuses fail-closed before commands execute."""

    def test_unreadable_tree_refuses_fail_closed(self) -> None:
        marker = self.worktree / SKIPPED_MARKER
        with patch.object(probes, "_tree_sha", return_value=""):
            run = runner._run_verify_commands(
                self.worktree,
                (f"touch {marker}",),
                60,
                context_revision="ctx-rev-99",
            )

        self.assertEqual(run.status, VERIFY_FAILED)
        self.assertEqual(run.output, "unreadable tree identity")
        self.assertIsNone(run.tree_identity)
        self.assertEqual(run.configured_commands, (f"touch {marker}",))
        self.assertEqual(run.attempted_commands, ())
        self.assertEqual(run.context_revision, "ctx-rev-99")
        self.assertFalse(run.is_reusable)
        self.assertFalse(
            marker.exists(),
            f"command ran despite unreadable tree identity; {marker} was created",
        )


if __name__ == "__main__":
    unittest.main()
