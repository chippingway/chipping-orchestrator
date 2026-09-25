# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Timeout teardown: process-group kill, partial output, and bounded drains."""

from __future__ import annotations

import subprocess
import time
import unittest
from unittest.mock import MagicMock

from orchestrator.git.verification import process, runner
from tests.git.verification import command_helpers

VERIFY_TIMEOUT = "timeout"
SLEEP_PAST_TIMEOUT = "sleep 5"
MARKER_FILE = "post_timeout_marker.txt"
BACKGROUND_SLACK_SECONDS = 3


class TimeoutVerifyRunTest(
    command_helpers.VerifyCommandsFixtureMixin,
    unittest.TestCase,
):
    """A command that outruns its cap is killed with its whole group."""

    def test_timeout_keeps_partial_output(self) -> None:
        # `sleep 5` against a 1s timeout fires `TimeoutExpired`.
        run = runner._run_verify_commands(
            self.worktree,
            (SLEEP_PAST_TIMEOUT,),
            timeout=1,
        )
        self.assertEqual(run.status, VERIFY_TIMEOUT)
        self.assertEqual(run.command, SLEEP_PAST_TIMEOUT)
        self.assertIsNone(run.exit_code)
        # The cap it was killed under is recorded for the park comment to name.
        self.assertEqual(run.timeout, 1)
        # Nothing is read after the kill, so the after-readings stay unset
        # rather than repeating the baseline.
        self.assertEqual((run.head_before, run.tree_before), (run.commit, run.tree_identity))
        self.assertEqual((run.head_after, run.tree_after), (None, None))
        self.assertEqual([ran.status for ran in run.attempted_commands], [VERIFY_TIMEOUT])
        self.assertFalse(run.is_reusable)

    def test_timeout_kills_full_process_group(self) -> None:
        # `subprocess.run(..., shell=True, timeout=...)` only SIGKILLs the
        # shell, leaving its background descendants (`& subshells`,
        # `make -j` workers, pytest-xdist forkers...) alive to keep
        # mutating the worktree after `_run_verify_commands` has returned
        # `verify_timeout` and the orchestrator has parked the issue. Each
        # command gets its own process group via `start_new_session=True`
        # and the group is `killpg`ed on timeout. Verified by having the
        # verify command spawn a background process that would touch a
        # sentinel file AFTER the timeout fires -- with the group-kill it
        # never gets to.
        marker = self.worktree / MARKER_FILE
        # Background subshell sleeps 2s then touches the marker. Parent
        # shell sleeps 10s so the 1s timeout definitely fires. If the
        # group-kill works, the background subshell dies before its
        # sleep finishes and the marker is never created.
        cmd = f"(sleep 2 && touch {marker}) & sleep 10"
        run = runner._run_verify_commands(self.worktree, (cmd,), timeout=1)
        self.assertEqual(run.status, VERIFY_TIMEOUT)
        # Wait well past when the background touch would have fired.
        # 3s gives the background its full 2s + 1s of slack.

        time.sleep(BACKGROUND_SLACK_SECONDS)
        self.assertFalse(
            marker.exists(),
            f"background process survived timeout-kill; {marker} was created",
        )


class DrainVerifyOutputTest(unittest.TestCase):
    """`_drain_verify_output` reads a killed verify shell's buffered output.

    The first bounded drain covers the normal case; if it wedges -- a
    descendant that escaped the group is still holding the pipe fd open -- it
    escalates to `proc.kill()` and one more bounded drain, then gives up with
    empty output. Popen is faked so the wedged path is deterministic.
    """

    def test_first_drain_returns_without_extra_kill(self) -> None:
        proc = MagicMock()
        proc.communicate.return_value = ("out", "err")
        self.assertEqual(process._drain_verify_output(proc), ("out", "err"))
        proc.kill.assert_not_called()

    def test_wedged_drain_kills_then_returns_output(self) -> None:
        proc = MagicMock()
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd="verify", timeout=5),
            ("late-out", "late-err"),
        ]
        self.assertEqual(
            process._drain_verify_output(proc),
            ("late-out", "late-err"),
        )
        proc.kill.assert_called_once()

    def test_both_drains_time_out_returns_empty(self) -> None:
        proc = MagicMock()
        proc.communicate.side_effect = subprocess.TimeoutExpired(
            cmd="verify",
            timeout=5,
        )
        self.assertEqual(process._drain_verify_output(proc), ("", ""))
        proc.kill.assert_called_once()


if __name__ == "__main__":
    unittest.main()
