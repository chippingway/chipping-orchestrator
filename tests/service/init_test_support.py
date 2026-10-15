# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the `init` tests share: a configured home, a fake systemd, and the check stood in for.

`init` asks systemd through `systemd.run_command`, the seam a fake stands in
for here, answering each command line from a table and recording it. The
check it runs starts an interpreter of its own, which a process running from
this checkout would refuse as a source checkout, so `checks.problems` is
stood in for too, reporting what the case says and recording that it was
asked in the same timeline as the commands, so a test reads back what ran
and in which order.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TextIO
from unittest.mock import patch

from orchestrator.service import checks, systemd
from orchestrator.service.installation import init

USER = "alice"
ENCODING = "utf-8"
UNIT = "chipping-orchestrator.service"
SETTINGS_FILE = Path(".config", "chipping-orchestrator", ".env")
UNIT_DIR = Path(".config", "systemd", "user")
TOKEN_FILE = Path(".config", "acme", "api", "token")
# An interpreter whose path holds a blank and a `%`, both of which the unit
# carries quoted.
INTERPRETER = "/opt/python 3%/bin/python3"

# Each command `init` runs, as its argv.
SYSTEMCTL = ("systemctl", "--user")
PROBE = (*SYSTEMCTL, "show", "--property=Version")
RELOAD = (*SYSTEMCTL, "daemon-reload")
ENABLE = (*SYSTEMCTL, "enable", UNIT)
SHOW_LINGER = ("loginctl", "show-user", USER, "--property=Linger")
ENABLE_LINGER = ("loginctl", "--no-ask-password", "enable-linger", USER)
IS_ACTIVE = (*SYSTEMCTL, "is-active", UNIT)
# Where the check and an onboarding ran, in the same timeline.
CHECKED = ("check",)
ONBOARDED = ("onboarding",)
# Each command a first `init` runs in a home where linger is off, the check in
# its place among them.
FIRST_INSTALL = (PROBE, CHECKED, RELOAD, ENABLE, SHOW_LINGER, ENABLE_LINGER, IS_ACTIVE)

# The unit `init` writes, but for its two quoted values.
UNIT_TEXT = """\
# Written by chipping-orchestrator init, which rewrites this file each time it
# runs; keep a local change in a drop-in: systemctl --user edit chipping-orchestrator.service
[Unit]
Description=chipping-orchestrator
StartLimitIntervalSec=0

[Service]
Type=simple
WorkingDirectory=%h
ExecStart={interpreter} -m orchestrator run
Environment={environment}
Restart=on-failure
RestartSec=30
SuccessExitStatus=130 143

[Install]
WantedBy=default.target
"""

DONE = systemd.Completed(0, "", "")
INACTIVE = systemd.Completed(3, "inactive\n", "")
ACTIVE = systemd.Completed(0, "active\n", "")
LINGERING = systemd.Completed(0, "Linger=yes\n", "")
NOT_LINGERING = systemd.Completed(0, "Linger=no\n", "")

_SETTINGS = "REPOS=acme/api|/home/alice/src/api|main\nALLOWED_ISSUE_AUTHORS=alice\n"
_SHELL_PATH = os.pathsep.join(("/opt/agent tools/bin", 'rel"ative', r'/srv/a"b\c%h', "/usr/bin"))
_TOKEN = "stand-in-token\n"


class _Terminal(io.StringIO):
    """Standard input as a terminal gives it."""

    def isatty(self) -> bool:
        return True


class FakeSystemd:
    """Stands in for ``systemd.run_command``: answers each argv from a table, recording it.

    A command the table does not name succeeds, saying nothing. A list in the
    table answers one call with each of its entries in turn, the last one
    every call after that. ``bounds`` holds the timeout each command was last
    run with.
    """

    def __init__(self, timeline: list[tuple[str, ...]]) -> None:
        self.answers: dict[tuple[str, ...], systemd.Completed | list[systemd.Completed]] = {
            SHOW_LINGER: NOT_LINGERING,
            IS_ACTIVE: INACTIVE,
        }
        self.bounds: dict[tuple[str, ...], float] = {}
        self._timeline = timeline

    def __call__(self, argv: Sequence[str], timeout: float = 0) -> systemd.Completed:
        command = tuple(argv)
        self._timeline.append(command)
        self.bounds[command] = timeout
        answer = self.answers.get(command, DONE)
        if isinstance(answer, list):
            return answer.pop(0) if len(answer) > 1 else answer[0]
        return answer


class InitCase(unittest.TestCase):
    """A home holding an installed `.env` and a token, with systemd and the check faked.

    The shell names alice and a `PATH` whose entries hold a blank, a quote, a
    backslash, and a `%` beside a relative entry, the interpreter is
    ``INTERPRETER``, and the package is answered for as an installed one. The
    user manager answers, linger is off, the service is not running, and the
    check finds nothing until a test says otherwise.
    """

    def setUp(self) -> None:
        self._scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self.home = self._scratch / "home"
        self.home.mkdir()
        self.enterContext(patch.dict(os.environ, HOME=str(self.home)))
        self.enterContext(patch.object(sys, "executable", INTERPRETER))
        self.shell = {"HOME": str(self.home), "USER": USER, "PATH": _SHELL_PATH}
        self._package_root = self._scratch
        self._settings_file = self.home / SETTINGS_FILE
        self._token_file = self.home / TOKEN_FILE
        for path, text in ((self._settings_file, _SETTINGS), (self._token_file, _TOKEN)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding=ENCODING)
        self.unit_file = self.home / UNIT_DIR / UNIT
        self.timeline: list[tuple[str, ...]] = []
        self.systemd = FakeSystemd(self.timeline)
        self.enterContext(patch.object(systemd, "run_command", self.systemd))
        self.problems: list[str] = []
        self.enterContext(patch.object(checks, "problems", self._check))

    def run_init(self, *, terminal: bool = False, **chosen: object) -> tuple[int, str, str]:
        """Run ``init`` from the case's shell; answer its status, stdout, and stderr."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        stdin = _Terminal() if terminal else io.StringIO()
        with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
            status = init(self.shell, stdin, package_root=self._package_root, **chosen)
        return status, stdout.getvalue(), stderr.getvalue()

    def refused(self, *, kept: bool = True, **chosen: object) -> str:
        """What ``init`` refused with, once no unit is found written and, if ``kept``, the setup kept."""
        status, stdout, stderr = self.run_init(**chosen)
        self.assertEqual((status, stdout), (1, ""), stderr)
        self.assertFalse(self.unit_file.exists())
        if kept:
            self.assert_setup_kept()
        return stderr.removesuffix("\n")

    def written_unit(self) -> str:
        """What the installed unit holds."""
        return self.unit_file.read_text(encoding=ENCODING)

    def assert_setup_kept(self) -> None:
        """The `.env` and the token file are exactly as the case wrote them."""
        self.assertEqual(self._settings_file.read_text(encoding=ENCODING), _SETTINGS)
        self.assertEqual(self._token_file.read_text(encoding=ENCODING), _TOKEN)

    def onboard(self, shell: Mapping[str, str], stdin: TextIO, package_root: Path) -> None:
        """Stand in for an onboarding at ``stdin``: record it, and write the case's `.env`."""
        handed = (shell, stdin.isatty(), package_root)
        self.assertEqual(handed, (self.shell, True, self._package_root))
        self.timeline.append(ONBOARDED)
        self._settings_file.write_text(_SETTINGS, encoding=ENCODING)

    def _check(self, shell: object, *, reach_github: bool) -> list[str]:
        """Record that the check ran, GitHub included, and report the case's problems."""
        self.assertTrue(reach_github, "init ran the local check alone")
        self.timeline.append(CHECKED)
        return list(self.problems)
