# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How a call to systemd ends, bounded, and what the manager and logind answers mean."""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from orchestrator.service import systemd
from tests.service import init_test_support as _support

_EXITED = 3
# Long enough that a command still running at the bound is plainly cut short.
_LONG_SLEEP_SECONDS = "30"
_BOUND_SECONDS = 0.2
_NO_BUS = "Failed to connect to bus: No medium found"
_NO_SYSTEMCTL = "systemctl cannot be run (no such file)"
_SAYS_AND_EXITS = ("sh", "-c", "echo out; echo first >&2; echo last >&2; exit 3")


class RunCommandTest(unittest.TestCase):
    """A command runs to its exit with its output captured, or is answered as never finishing.

    Real commands stand in for systemd here: what is under test is how a run
    ends, which the binary does not change.
    """

    def test_an_exit_carries_its_status_and_output(self) -> None:
        ended = systemd.run_command(_SAYS_AND_EXITS)

        self.assertEqual(ended, systemd.Completed(_EXITED, "out\n", "first\nlast\n"))
        self.assertFalse(ended.succeeded)
        self.assertEqual(ended.reason(), "last")
        self.assertEqual(systemd.Completed(_EXITED, "", "").reason(), "exit status 3")

    def test_standard_input_is_closed(self) -> None:
        ended = systemd.run_command(("cat",))

        self.assertEqual(ended, _support.DONE)

    def test_a_command_still_running_is_cut_short(self) -> None:
        started = time.monotonic()

        ended = systemd.run_command(("sleep", _LONG_SLEEP_SECONDS), timeout=_BOUND_SECONDS)

        self.assertLess(time.monotonic() - started, float(_LONG_SLEEP_SECONDS) / 2)
        self.assertEqual(ended, systemd.Completed(None, "", "sleep did not finish within 0.2 seconds"))

    def test_a_command_that_cannot_run_is_answered(self) -> None:
        ended = systemd.run_command(("chipping-orchestrator-no-such-systemctl", "--user"))

        self.assertIsNone(ended.status)
        self.assertTrue(
            ended.reason().startswith("chipping-orchestrator-no-such-systemctl cannot be run ("),
            ended.reason(),
        )


class ManagerAnswersTest(unittest.TestCase):
    """Whether the user manager answers, and whether logind lingers the user, read off each command."""

    def setUp(self) -> None:
        self.timeline: list[tuple[str, ...]] = []
        self.systemd = _support.FakeSystemd(self.timeline)
        self.enterContext(patch.object(systemd, "run_command", self.systemd))

    def test_the_manager_is_reached_where_it_answers(self) -> None:
        for answer, problem in (
            (_support.DONE, None),
            (systemd.Completed(1, "", f"{_NO_BUS}\n"), _NO_BUS),
            (systemd.Completed(None, "", _NO_SYSTEMCTL), _NO_SYSTEMCTL),
        ):
            with self.subTest(answer=answer):
                self.systemd.answers[_support.PROBE] = answer
                self.assertEqual(systemd.manager_problem(), problem)
        self.assertEqual(set(self.timeline), {_support.PROBE})

    def test_linger_is_on_only_where_logind_says_so(self) -> None:
        for answer, lingering in (
            (_support.LINGERING, True),
            (_support.NOT_LINGERING, False),
            (systemd.Completed(1, "", "Failed to get user: User ID 1000 is not logged in or lingering\n"), False),
            (systemd.Completed(None, "", "loginctl cannot be run (no such file)"), False),
        ):
            with self.subTest(answer=answer):
                self.systemd.answers[_support.SHOW_LINGER] = answer
                self.assertIs(systemd.linger_enabled(_support.USER), lingering)
        self.assertEqual(set(self.timeline), {_support.SHOW_LINGER})


if __name__ == "__main__":
    unittest.main()
