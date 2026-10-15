# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the lifecycle tests share: an installed service in a set-up home, with systemd, the check, and waiting faked.

The home holds what a running setup leaves -- the `.env`, a token, a log, and
a worktree -- and the unit `init` writes, whose `PATH` is not the shell's.
systemd is answered by the fake the `init` tests use, the user manager
answering and a launched service staying active until a test says otherwise.
The check is stood in for, reporting what the case says, and so are the pause
between the questions asked of a launched service and the clock the watch is
measured by: a fake clock a pause moves on, and that a command a test makes
slow moves on too, up to the bound it was run with -- past which it is
answered as one that did not finish, as a real command is. The check and each
pause are recorded in the same timeline as the commands -- the check with the
`PATH` it was handed, the pause with how long it would have waited -- so a
test reads back what ran, in which order, and on which `PATH`; the whole
environment and the directory the check was handed are kept beside it. The
directories outside the home that systemd reads drop-ins from are read under a
scratch root, so no drop-in on the host running the tests reaches them.
"""
from __future__ import annotations

import io
import os
import sys
import tempfile
import unittest
from collections.abc import Callable, Mapping, Sequence
from functools import partial
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import checks, starting, systemd, unit_environment, unit_file
from tests.service import init_test_support as _init

ENCODING = _init.ENCODING
UNIT = _init.UNIT
# The `PATH` the unit records, holding a blank, a quote, a backslash, and a
# `%`, each of which it carries escaped, and the shell's own, which no
# lifecycle command checks the agents on.
UNIT_SEARCH_PATH = r'/opt/agent tools/bin:/srv/a"b\c%h:/usr/bin'
_SHELL_PATH = "/home/alice/.local/bin:/usr/bin"

# The two launches, by the command that names each.
START_COMMAND = "start"
RESTART_COMMAND = "restart"

# Each command a lifecycle command runs, as its argv, and where the check ran
# and a launched service was waited on.
PROBE = _init.PROBE
RELOAD = _init.RELOAD
IS_ACTIVE = _init.IS_ACTIVE
START = (*_init.SYSTEMCTL, START_COMMAND, UNIT)
RESTART = (*_init.SYSTEMCTL, RESTART_COMMAND, UNIT)
STOP = (*_init.SYSTEMCTL, "stop", UNIT)
STATUS = (*_init.SYSTEMCTL, "status", "--no-pager", UNIT)
DISABLE = (*_init.SYSTEMCTL, "disable", UNIT)
IS_FAILED = (*_init.SYSTEMCTL, "is-failed", UNIT)
RESET_FAILED = (*_init.SYSTEMCTL, "reset-failed", UNIT)
JOURNAL = ("journalctl", "--user-unit", UNIT, "--lines=20", "--no-pager", "--quiet")
CHECKED = ("check", UNIT_SEARCH_PATH)
# Where `systemctl --user edit` writes the unit's drop-in.
OVERRIDE = f"~/.config/systemd/user/{UNIT}.d/override.conf"
PAUSED = ("pause", "1")

# What `run_command` answers a command still running at its bound with.
_UNFINISHED = "{0} did not finish within {1:g} seconds"

# Past the 90 seconds systemd gives a unit to stop.
STOP_BOUND = 120

DONE = _init.DONE
ACTIVE = _init.ACTIVE
NO_BUS = systemd.Completed(1, "", "Failed to connect to bus: No medium found\n")

_SETUP = (
    (_init.SETTINGS_FILE, "REPOS=acme/api|/home/alice/src/api|main\nALLOWED_ISSUE_AUTHORS=alice\n"),
    (_init.TOKEN_FILE, "stand-in-token\n"),
    (Path(".local", "state", "chipping-orchestrator", "logs", "orchestrator.log"), "a logged line\n"),
    (Path("src", "wt-orchestrator", "acme__api", "issue-7", "change.py"), "work in progress\n"),
)


# What the check is handed: the environment, and the directory it runs in.
Checked = tuple[dict[str, str], str | None]


def service_check(directory: str | None = None, **assigned: str) -> Checked:
    """What a case's check is handed: its environment, and the directory it runs in, the home by default.

    The environment is the shell's `HOME` and `USER`, the unit's `PATH`, and
    ``assigned``.
    """
    home = os.environ["HOME"]
    return {"HOME": home, "USER": _init.USER, "PATH": UNIT_SEARCH_PATH, **assigned}, directory or home


class FakeClock:
    """The time a launch's watch is measured by, which only a pause or a slow command moves on.

    Each pause is recorded in the timeline it is given.
    """

    def __init__(self, timeline: list[tuple[str, ...]]) -> None:
        self.now: float = 0
        self._timeline = timeline

    def __call__(self) -> float:
        return self.now

    def pause(self, seconds: float) -> None:
        """Wait ``seconds``: record the pause, and move the clock on by them."""
        self._timeline.append(("pause", format(seconds, "g")))
        self.now += seconds


class TimedSystemd(_init.FakeSystemd):
    """The fake systemd, each command ``delays`` names taking that long on ``clock``.

    One taking at least the bound it is run with is cut short there and
    answered as a command that did not finish, the way ``run_command``
    answers one.
    """

    def __init__(self, timeline: list[tuple[str, ...]], clock: FakeClock) -> None:
        super().__init__(timeline)
        self.clock = clock
        self.delays: dict[tuple[str, ...], float] = {}

    # A command run without a bound of its own gets the 30 seconds
    # `run_command` gives it.
    def __call__(self, argv: Sequence[str], timeout: float = 30) -> systemd.Completed:
        answer = super().__call__(argv, timeout)
        delay = self.delays.get(tuple(argv), 0)
        self.clock.now += min(delay, timeout)
        if delay < timeout:
            return answer
        return systemd.Completed(None, "", _UNFINISHED.format(argv[0], timeout))


class LifecycleCase(unittest.TestCase):
    """A home set up and its service installed by `init`, with systemd and the check faked."""

    def setUp(self) -> None:
        scratch = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        self._home = scratch / "home"
        self._root = scratch / "root"
        self.enterContext(patch.dict(os.environ, HOME=str(self._home)))
        self.enterContext(patch.object(unit_environment, "SYSTEM_ROOT", self._root))
        self._shell = {"HOME": str(self._home), "USER": _init.USER, "PATH": _SHELL_PATH}
        self.settings_file = self._home / _init.SETTINGS_FILE
        self.unit_file = self._home / _init.UNIT_DIR / UNIT
        for path, text in (
            *_SETUP,
            (self.unit_file, unit_file.render_unit(_init.INTERPRETER, UNIT_SEARCH_PATH)),
        ):
            located = self._home / path
            located.parent.mkdir(parents=True, exist_ok=True)
            located.write_text(text, encoding=ENCODING)
        self.timeline: list[tuple[str, ...]] = []
        self.systemd = TimedSystemd(self.timeline, FakeClock(self.timeline))
        self.systemd.answers[IS_ACTIVE] = ACTIVE
        self.enterContext(patch.object(systemd, "run_command", self.systemd))
        self.problems: list[str] = []
        self.checked: list[Checked] = []
        self.enterContext(patch.object(checks, "service_problems", self._check))

    def answered(self, command: Callable[[], int]) -> tuple[int, str, str]:
        """Run ``command``; answer its status, stdout, and stderr."""
        stdout = io.StringIO()
        stderr = io.StringIO()
        with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
            status = command()
        return status, stdout.getvalue(), stderr.getvalue()

    def launched(self, command: str) -> tuple[int, str, str]:
        """Run ``start`` or ``restart`` from the case's shell, on the fake clock."""
        clock = self.systemd.clock
        launch = partial(starting.launch, pause=clock.pause, clock=clock)
        return self.answered(partial(launch, command, self._shell))

    def write_drop_in(self, located: str, text: str) -> Path:
        """Write ``text`` as the drop-in at ``located``, under the home where it starts with ``~``, else the root."""
        anchor = self._home if located.startswith("~") else self._root
        drop_in = anchor / located.lstrip("~/")
        drop_in.parent.mkdir(parents=True, exist_ok=True)
        drop_in.write_text(text, encoding=ENCODING)
        return drop_in

    def setup_files(self) -> dict[Path, bytes]:
        """Every file in the home but the unit, by path, with what it holds."""
        return {
            path: path.read_bytes()
            for path in sorted(self._home.rglob("*"))
            if path.is_file() and path != self.unit_file
        }

    def _check(
        self,
        service: Mapping[str, str],
        *,
        reach_github: bool,
        working_directory: str | None = None,
    ) -> list[str]:
        """Record the environment and directory the local check was handed, and report the case's problems."""
        self.assertFalse(reach_github, "a lifecycle command asked GitHub")
        self.timeline.append(("check", service["PATH"]))
        self.checked.append((dict(service), working_directory))
        return list(self.problems)
