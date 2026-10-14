# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What `init` refuses, each with exit status 1 and before it writes anything.

Each refusal is its message alone on stderr, leaves no unit written and the
`.env` and the token as they were, and asks systemd nothing past what it took
to refuse.
"""
from __future__ import annotations

import sys
from unittest.mock import patch

from orchestrator.service import paths
from orchestrator.service.systemd import Completed
from tests.service import init_test_support as _support
from tests.support.checkouts import make_checkout

_LEGACY_UNIT = "orchestrator.service"


class HostRefusalTest(_support.InitCase):
    """What about the host stops `init` before it reads anything of the setup."""

    def test_a_source_checkout_is_refused_first(self) -> None:
        self._package_root = make_checkout(self._scratch / "source")
        legacy = self.home / _support.UNIT_DIR / _LEGACY_UNIT
        legacy.parent.mkdir(parents=True)
        legacy.touch()

        self.assertEqual(self.refused(), paths.source_checkout_refusal("init", self._package_root))
        self.assertEqual(self.timeline, [])

    def test_the_hand_written_unit_goes_first(self) -> None:
        legacy = self.home / _support.UNIT_DIR / _LEGACY_UNIT
        legacy.parent.mkdir(parents=True)
        legacy.write_text("[Service]\n", encoding=_support.ENCODING)

        self.assertEqual(self.refused(), (
            f"{legacy} is a hand-written unit for the same poller, and init installs no "
            "second service beside it, since the two would poll at once; stop, disable, "
            "and delete it first -- systemctl --user stop orchestrator.service, "
            f"systemctl --user disable orchestrator.service, rm {legacy}, and systemctl "
            "--user daemon-reload -- and run init again"
        ))
        self.assertEqual(self.timeline, [])
        self.assertEqual(legacy.read_text(encoding=_support.ENCODING), "[Service]\n")

    def test_an_uncarried_interpreter_is_refused(self) -> None:
        interpreter = '/opt/py"thon/bin/python3'

        with patch.object(sys, "executable", interpreter):
            refused = self.refused()

        self.assertEqual(refused, (
            f"the interpreter {interpreter!r} holds a quote, a backslash, or a '$', "
            "which systemd refuses or rewrites in the command it starts the service "
            "with; install the package under a path without one"
        ))
        self.assertEqual(self.timeline, [])

    def test_an_unreachable_user_manager_is_refused(self) -> None:
        self.systemd.answers[_support.PROBE] = Completed(
            1, "", "Failed to connect to bus: No medium found\n",
        )

        self.assertEqual(self.refused(), (
            "systemctl --user cannot reach a systemd user manager (Failed to connect "
            "to bus: No medium found), and init installs a systemd user service; run "
            "init as the service's user, in a login session that has a manager -- an "
            "ssh or desktop login rather than su or sudo -- and try again"
        ))
        self.assertEqual(self.timeline, [_support.PROBE])


class SetupRefusalTest(_support.InitCase):
    """What about the setup stops `init`: no `.env` to install for, or a failed check."""

    def test_no_env_without_a_terminal_is_refused(self) -> None:
        self._settings_file.unlink()

        refused = self.refused(onboard=self.onboard, kept=False)

        self.assertEqual(refused, (
            f"no configuration exists at {self._settings_file}, and init installs the "
            "service only for one; write it without prompts -- store each repository's "
            "token with chipping-orchestrator set-token OWNER/NAME, then run "
            "chipping-orchestrator configure --clone PATH --authors LOGINS -- and run "
            "init again"
        ))
        self.assertEqual(self.timeline, [_support.PROBE])
        self.assertFalse(self._settings_file.exists())

    def test_no_env_at_a_terminal_without_onboarding(self) -> None:
        self._settings_file.unlink()

        self.assertIn("chipping-orchestrator set-token OWNER/NAME", self.refused(terminal=True, kept=False))
        self.assertFalse(self._settings_file.exists())

    def test_a_failed_check_installs_nothing(self) -> None:
        problem = "acme/api: no GitHub token in /home/alice/.config/acme/api/token"
        self.problems.append(problem)

        self.assertEqual(self.refused().splitlines(), [
            problem,
            "init installed nothing: the service would not run until the problems above are repaired",
        ])
        self.assertEqual(self.timeline, [_support.PROBE, _support.CHECKED])


class FailedEnableTest(_support.InitCase):
    """A manager that will not reload its units exits 1, leaving the written unit for the next `init`."""

    def test_a_refused_reload_stops_before_enabling(self) -> None:
        self.systemd.answers[_support.RELOAD] = Completed(1, "", "Failed to reload daemon: Access denied\n")

        status, stdout, stderr = self.run_init()

        self.assertEqual(status, 1)
        self.assertEqual(stdout.splitlines()[1:], [f"Wrote {self.unit_file}"])
        self.assertEqual(stderr, (
            "systemctl --user daemon-reload failed (Failed to reload daemon: Access denied); "
            f"{self.unit_file} is written, so run init again once the user manager takes it\n"
        ))
        self.assertEqual(self.timeline, [_support.PROBE, _support.CHECKED, _support.RELOAD])
        self.assertTrue(self.unit_file.exists())
