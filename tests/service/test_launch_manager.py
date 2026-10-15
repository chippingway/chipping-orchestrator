# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What the user manager holds besides the files a launch checks: the `HOME` it hands, and the definition it loaded.

As in `test_launch_check`, the check is the real one, run from the installed
copy of the package, and only systemd is faked.
"""
from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import systemd
from tests.service import (
    check_test_support as _check,
    lifecycle_test_support as _lifecycle,
    test_launch_check as _launch,
)

_CONFIG = Path(".config")
_LAUNCHES = (_lifecycle.START_COMMAND, _lifecycle.RESTART_COMMAND)
_JOBS = (_lifecycle.START, _lifecycle.RESTART)
# A drop-in as the manager loaded it before it was repaired, and as it is now.
_STALE = "[Service]\nEnvironment=ALLOWED_ISSUE_AUTHORS=,\n"
_REPAIRED = "[Service]\nEnvironment=ALLOWED_ISSUE_AUTHORS=alice\n"
_RESTARTING = systemd.Completed(3, "activating\n", "")


class _CachingSystemd(_lifecycle.TimedSystemd):
    """The fake systemd as a manager holding the definition it last loaded, until a reload loads the files.

    It starts out holding a drop-in emptying the author allowlist, which the
    files on disk repair; while it holds that one, the service it launches is
    answered as restarting rather than active.
    """

    def __init__(
        self,
        timeline: list[tuple[str, ...]],
        clock: _lifecycle.FakeClock,
        write_drop_in: Callable[[str], None],
    ) -> None:
        super().__init__(timeline, clock)
        write_drop_in(_REPAIRED)
        self._loaded = _STALE

    def __call__(self, argv: Sequence[str], timeout: float = 30) -> systemd.Completed:
        if tuple(argv) == _lifecycle.RELOAD:
            self._loaded = _REPAIRED
        self.answers[_lifecycle.IS_ACTIVE] = _lifecycle.ACTIVE if self._loaded == _REPAIRED else _RESTARTING
        return super().__call__(argv, timeout)


class InheritedHomeCheckTest(_launch.LaunchCheckCase):
    """A `HOME` the manager's `environment.d` sets is the one the service, and the check, reads `.env` under.

    The service inherits it as it is, so a home holding no `.env` is refused
    for want of `REPOS`, the real home's `.env` notwithstanding.
    """

    def test_the_inherited_home_is_checked(self) -> None:
        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        environment_d = self.home / _CONFIG / "environment.d" / "90-home.conf"
        environment_d.parent.mkdir(parents=True)
        environment_d.write_text(f"HOME={elsewhere}\n", encoding=_check.ENCODING)

        status, stderr = self.started(_lifecycle.RESTART_COMMAND)

        self.assertEqual((status, self.timeline), (1, []))
        self.assertIn("REPOS", stderr)


class ReloadedDefinitionTest(_launch.LaunchCheckCase):
    """A launch has the manager load the definition just checked before it launches it.

    The fake manager keeps the definition it loaded before the drop-in was
    repaired -- one emptying the author allowlist, under which the service
    never stays up -- until it is told to reload; the files on disk are valid.
    """

    def test_the_checked_definition_is_launched(self) -> None:
        for command, job in zip(_LAUNCHES, _JOBS, strict=True):
            with self.subTest(command=command):
                self.timeline.clear()
                clock = _lifecycle.FakeClock(self.timeline)
                manager = _CachingSystemd(self.timeline, clock, self.write_drop_in)
                self.systemd = manager
                self.enterContext(patch.object(systemd, "run_command", manager))

                self.assertEqual(self.started(command)[0], 0)
                reloaded = self.timeline.index(_lifecycle.RELOAD)
                self.assertLess(reloaded, self.timeline.index(job))
