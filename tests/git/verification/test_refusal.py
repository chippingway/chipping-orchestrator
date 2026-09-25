# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fail-closed refusals: unreadable baselines, unproven worktrees, and skipped later commands."""

from __future__ import annotations

import contextlib
import unittest
from unittest.mock import patch

from orchestrator.git.verification import models, probes, runner, status as _worktree_status
from tests.git.verification import command_helpers

VERIFY_DIRTY = "dirty"
VERIFY_FAILED = "failed"
VERIFY_OK = "ok"
PASSING_COMMAND = "true"
SKIPPED_MARKER = "third_command_ran.txt"
LEFTOVER_FILE = "dirty_before.txt"
TIMEOUT_SECONDS = 60
_UNREADABLE_STATUS = _worktree_status._WorktreeStatus(readable=False)


class RefusedBeforeCommandsTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """A baseline that cannot be established refuses before any command runs.

    Evidence names the commit and tree it tested and has to describe content
    that commit holds, so an unreadable HEAD, an unreadable tree, a worktree
    already carrying changes, and a status git could not read all refuse
    before the first command -- a command that cleaned up what was there would
    otherwise pass over content no recorded tree holds.
    """

    def test_unreadable_identity_refuses(self) -> None:
        for probe in ("_head_sha", "_tree_sha"):
            with self.subTest(probe=probe):
                run = self._run_with_marker(patch.object(probes, probe, return_value=""))
                self.assertEqual(run.status, VERIFY_FAILED)
                self.assertIsNone(run.commit)
                self.assertIsNone(run.tree_identity)
                self.assertEqual(run.tree_before, "")
                self.assertIsNone(run.head_after)

    def test_dirty_worktree_refuses(self) -> None:
        (self.worktree / LEFTOVER_FILE).write_text("uncommitted\n")
        run = self._run_with_marker(contextlib.nullcontext())
        self.assertEqual(run.status, VERIFY_DIRTY)
        self.assertEqual(run.dirty_files, (LEFTOVER_FILE,))
        self._assert_names_the_refused_baseline(run)

    def test_unreadable_status_refuses(self) -> None:
        run = self._run_with_marker(patch.object(
            _worktree_status, "_worktree_status", return_value=_UNREADABLE_STATUS,
        ))
        self.assertEqual(run.status, VERIFY_DIRTY)
        self.assertEqual(run.dirty_files, ())
        self._assert_names_the_refused_baseline(run)

    def _assert_names_the_refused_baseline(self, run: models.VerifyResult) -> None:
        self.assertTrue(run.commit and run.tree_identity)
        self.assertEqual((run.head_before, run.tree_before), (run.commit, run.tree_identity))
        self.assertIsNone(run.head_after)

    def _run_with_marker(self, reading) -> models.VerifyResult:
        marker = self.worktree / SKIPPED_MARKER
        commands = (f"touch {marker}",)
        with reading:
            run = runner._run_verify_commands(self.worktree, commands, TIMEOUT_SECONDS)
        self.assertFalse(marker.exists(), f"a command ran; {marker} was created")
        self.assertIsNone(run.command)
        self.assertEqual(run.attempted_commands, ())
        self.assertEqual(run.configured_commands, commands)
        self.assertEqual(run.context_revision, models._context_revision(commands, TIMEOUT_SECONDS))
        self.assertFalse(run.is_reusable)
        return run


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

    def test_unread_status_after_command_refuses(self) -> None:
        # A zero exit passes only on a status read that proved the tree
        # clean; one that failed after the command is not that proof.
        clean = _worktree_status._WorktreeStatus(readable=True)
        with patch.object(
            _worktree_status, "_worktree_status", side_effect=(clean, _UNREADABLE_STATUS),
        ):
            run = runner._run_verify_commands(
                self.worktree, (PASSING_COMMAND, PASSING_COMMAND), TIMEOUT_SECONDS,
            )

        self.assertEqual(run.status, VERIFY_DIRTY)
        self.assertEqual((run.command, run.exit_code), (PASSING_COMMAND, 0))
        self.assertEqual(run.dirty_files, ())
        self.assertEqual([ran.status for ran in run.attempted_commands], [VERIFY_DIRTY])
        self.assertFalse(run.is_reusable)


if __name__ == "__main__":
    unittest.main()
