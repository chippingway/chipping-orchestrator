# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`start` running the real local check, in the environment and directory the installed service would get.

The check is not stood in for here: it starts an interpreter of the
installed copy of the package, as the service would run it, and only systemd
is faked. The unit `init` writes records the shell's `PATH`; a drop-in then
changes what the service would run with, and what the check finds there
decides whether systemd is asked anything at all.
"""
from __future__ import annotations

import io
import os
import shutil
import sys
from functools import partial
from itertools import product
from pathlib import Path
from unittest.mock import patch

from orchestrator.service import paths, starting, systemd, unit_environment, unit_file
from tests.service import check_test_support as _check, lifecycle_test_support as _lifecycle
from tests.support.checkouts import make_checkout

_CLONE = "relative-clone"
_UNSEEN_CLONE = "/no-such-clone"
_BACKSLASH = "\\"
_OVERRIDE = f"{unit_file.UNIT_NAME}.d"
# The user manager's own configuration in the home, and a drop-in beside it.
_CONFIG = Path(".config")
_LAUNCHES = (_lifecycle.START_COMMAND, _lifecycle.RESTART_COMMAND)
_MANAGER_DIRECTIVES = ("DefaultEnvironment", "ManagerEnvironment")

_SETTINGS = _CONFIG / "chipping-orchestrator" / ".env"
_USER_CONF = _CONFIG / "systemd" / "user.conf"
_MANAGER_DROP_IN = _USER_CONF.parent / "user.conf.d" / "90-orchestrator.conf"
# What the check refuses an author allowlist naming nobody with, and what
# `start` adds.
_EMPTY_ALLOWLIST = (
    f"{_check.ALLOWLIST_REFUSAL}\n"
    "chipping-orchestrator {0} left the service as it was: it would not run "
    "until the problems above are repaired\n"
)
# A value continued over a newline and the carriage return after it, which
# systemd reads as one line end, so the allowlist after them is assigned too.
_RUN_ON = f"IGNORED=1 {_BACKSLASH}\n\rALLOWED_ISSUE_AUTHORS=,\n"
# What the check refuses a clone it does not find with, and what `start` adds.
_NO_CLONE = (
    "orchestrator: REPOS target {0} for 'acme/api' does not exist; point it at "
    "a local clone or linked worktree of acme/api\n"
    "chipping-orchestrator start left the service as it was: it would not run "
    "until the problems above are repaired\n"
)


class LaunchCheckCase(_check.CheckCase):
    """A host checked as an installed package, its unit installed, systemd faked and the clock with it.

    `acme/api` is the only repository, its clone named relative to the home,
    where the unit starts the service.
    """

    def setUp(self) -> None:
        super().setUp()
        self.enterContext(patch.dict(os.environ, HOME=str(self.home)))
        self.enterContext(patch.object(unit_environment, "SYSTEM_ROOT", self.root / "system-root"))
        self.enterContext(patch.object(paths, "PACKAGE_ROOT", self._site_packages))
        make_checkout(self.home / _CLONE)
        self.settings["REPOS"] = f"{_check.API}|{_CLONE}|main"
        self.write_settings(self.home / _SETTINGS)
        self.unit = unit_file.unit_path()
        self.unit.parent.mkdir(parents=True)
        rendered = unit_file.render_unit(sys.executable, self.shell["PATH"])
        self.unit.write_text(rendered, encoding=_check.ENCODING)
        self.timeline: list[tuple[str, ...]] = []
        self.systemd = _lifecycle.TimedSystemd(self.timeline, _lifecycle.FakeClock(self.timeline))
        self.systemd.answers[_lifecycle.IS_ACTIVE] = _lifecycle.ACTIVE
        self.enterContext(patch.object(systemd, "run_command", self.systemd))

    def write_drop_in(self, text: str) -> None:
        """Write ``text`` as the drop-in `systemctl --user edit` makes."""
        drop_in = self.unit.parent / _OVERRIDE / "override.conf"
        drop_in.parent.mkdir(exist_ok=True)
        drop_in.write_text(text, encoding=_check.ENCODING)

    def assert_allowlist_refused(self) -> None:
        """Assert both launches refuse an author allowlist naming nobody, asking systemd nothing."""
        for command in _LAUNCHES:
            with self.subTest(command=command):
                self.assertEqual(self.started(command), (1, _EMPTY_ALLOWLIST.format(command)))
                self.assertEqual(self.timeline, [])

    def started(self, command: str = _lifecycle.START_COMMAND) -> tuple[int, str]:
        """Run ``command`` from the case's shell; answer its status and stderr, having asked GitHub nothing."""
        clock = self.systemd.clock
        stdout = io.StringIO()
        stderr = io.StringIO()
        launch = partial(starting.launch, pause=clock.pause, clock=clock)
        with patch.object(sys, "stdout", stdout), patch.object(sys, "stderr", stderr):
            status = launch(command, self.shell)
        self.assertEqual(self.github.requests(), [])
        return status, stderr.getvalue()


class WorkingDirectoryCheckTest(LaunchCheckCase):
    """The check runs where the unit starts the service, so a clone named relative to it is found only there."""

    def test_a_clone_is_found_where_the_service_runs(self) -> None:
        status, stderr = self.started()

        self.assertEqual((status, stderr), (0, ""))
        self.assertIn(_lifecycle.START, self.timeline)

        elsewhere = self.root / "elsewhere"
        elsewhere.mkdir()
        self.write_drop_in(f"[Service]\nWorkingDirectory={elsewhere}\n")
        self.timeline.clear()

        self.assertEqual(self.started(), (1, _NO_CLONE.format(_CLONE)))
        self.assertEqual(self.timeline, [])


class MarkedDropInCheckTest(LaunchCheckCase):
    """A drop-in starting with a byte-order mark overrides a setting as systemd reads it, and is checked so.

    systemd drops the mark only after telling comments, so a comment the mark
    opens is a line, which a trailing backslash continues over the header
    below: the setting after it lands in no section and overrides nothing.
    """

    def test_its_override_is_checked(self) -> None:
        self.write_drop_in(f"﻿[Service]\nEnvironment=REPOS={_check.API}|{_UNSEEN_CLONE}|main\n")

        self.assertEqual(self.started(), (1, _NO_CLONE.format(_UNSEEN_CLONE)))
        self.assertEqual(self.timeline, [])

    def test_a_marked_comment_swallows_the_header(self) -> None:
        self.settings["ALLOWED_ISSUE_AUTHORS"] = ""
        self.write_settings(self.home / _SETTINGS)
        self.write_drop_in(f"\ufeff# comment {_BACKSLASH}\n[Service]\nEnvironment=ALLOWED_ISSUE_AUTHORS=alice\n")

        self.assert_allowlist_refused()


class LineEndCheckTest(LaunchCheckCase):
    """A newline and the carriage return after it end one line, as systemd reads the files, not two.

    So a value continued over them runs on into the next line, in a drop-in
    and in `user.conf` alike, and an author allowlist emptied there is
    checked as the service would get it.
    """

    def test_a_drop_in_s_value_runs_on(self) -> None:
        self.write_drop_in(f"[Service]\nEnvironment={_RUN_ON}")

        self.assert_allowlist_refused()

    def test_a_user_conf_value_runs_on(self) -> None:
        user_conf = self.home / _USER_CONF
        user_conf.parent.mkdir(parents=True, exist_ok=True)
        user_conf.write_text(f"[Manager]\nDefaultEnvironment={_RUN_ON}", encoding=_check.ENCODING)

        self.assert_allowlist_refused()


class HiddenSettingsCheckTest(LaunchCheckCase):
    """An empty author allowlist in `.env` is refused unless what systemd really reads repairs it.

    A hidden drop-in is no drop-in to systemd, so it repairs nothing, and nor
    does one past a malformed section header, where systemd stops reading; an
    `environment.d` file that empties the allowlist again reaches the service
    beneath the unit, and is checked so.
    """

    def test_only_what_systemd_reads_counts(self) -> None:
        self.settings["ALLOWED_ISSUE_AUTHORS"] = ""
        self.write_settings(self.home / _SETTINGS)
        hidden = self.unit.parent / _OVERRIDE / ".disabled.conf"
        hidden.parent.mkdir()
        hidden.write_text("[Service]\nEnvironment=ALLOWED_ISSUE_AUTHORS=alice\n", encoding=_check.ENCODING)

        self.assertEqual(self.started(), (1, _EMPTY_ALLOWLIST.format(_lifecycle.START_COMMAND)))
        self.assertEqual(self.timeline, [])

    def test_a_malformed_header_repairs_nothing(self) -> None:
        self.settings["ALLOWED_ISSUE_AUTHORS"] = ""
        self.write_settings(self.home / _SETTINGS)
        self.write_drop_in("[Manager\n[Service]\nEnvironment=ALLOWED_ISSUE_AUTHORS=alice\n")
        for command in _LAUNCHES:
            with self.subTest(command=command):
                status, stderr = self.started(command)

                self.assertEqual((status, self.timeline), (1, []))
                self.assertIn("malformed section header", stderr)

    def test_the_manager_s_variables_are_checked(self) -> None:
        environment_d = self.home / _CONFIG / "environment.d" / "90-orchestrator.conf"
        environment_d.parent.mkdir(parents=True)
        environment_d.write_text("ALLOWED_ISSUE_AUTHORS=,\n", encoding=_check.ENCODING)

        self.assertEqual(self.started(), (1, _EMPTY_ALLOWLIST.format(_lifecycle.START_COMMAND)))
        self.assertEqual(self.timeline, [])

    def test_the_home_s_manager_drop_in_is_checked(self) -> None:
        drop_in = self.home / _MANAGER_DROP_IN
        drop_in.parent.mkdir(parents=True)
        for directive, command in product(_MANAGER_DIRECTIVES, _LAUNCHES):
            with self.subTest(directive=directive, command=command):
                drop_in.write_text(f"[Manager]\n{directive}=ALLOWED_ISSUE_AUTHORS=,\n", encoding=_check.ENCODING)

                self.assertEqual(self.started(command), (1, _EMPTY_ALLOWLIST.format(command)))
                self.assertEqual(self.timeline, [])


class ManagerSpecifierCheckTest(LaunchCheckCase):
    """A `DefaultEnvironment=` value naming the home by `%h` is checked with the home in its place."""

    def test_the_token_file_it_names_is_found(self) -> None:
        token = self.token_path(_check.API)
        moved = self.home / "tokens" / "api"
        moved.parent.mkdir()
        token.rename(moved)
        user_conf = self.home / _USER_CONF
        user_conf.parent.mkdir(parents=True, exist_ok=True)
        user_conf.write_text(
            "[Manager]\nDefaultEnvironment=ORCHESTRATOR_TOKEN_FILE=%h/tokens/api\n",
            encoding=_check.ENCODING,
        )

        self.assertEqual(self.started(), (0, ""))
        self.assertIn(_lifecycle.START, self.timeline)


class RelativePathCheckTest(LaunchCheckCase):
    """Agents found only through a relative `PATH` entry are refused, though the home holds them.

    The check would find them from the home, where it runs; an agent runs in
    an issue's worktree, where the same entry finds nothing.
    """

    def test_a_relative_entry_asks_systemd_nothing(self) -> None:
        shutil.move(self.agents, self.home / "bin")
        self.write_drop_in(f"[Service]\nEnvironment=PATH={self._tools}{os.pathsep}bin\n")
        for command in _LAUNCHES:
            with self.subTest(command=command):
                status, stderr = self.started(command)

                self.assertEqual((status, self.timeline), (1, []))
                self.assertIn("a PATH with an empty or relative entry", stderr)
