# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`init` installing the systemd user service, and refreshing it when run again."""
from __future__ import annotations

from orchestrator.service.systemd import Completed
from tests.service import init_test_support as _support

# The interpreter's blank kept and its `%` doubled, inside the quotes.
_EXEC_START = '"/opt/python 3%%/bin/python3"'
# The shell's `PATH` with its relative entry dropped, its quote and backslash
# escaped, and its `%` doubled.
_FIRST_PATH = r'"PATH=/opt/agent tools/bin:/srv/a\"b\\c%%h:/usr/bin"'
_NEW_PATH = "/opt/new agents/bin:/usr/bin"
_UNIT_COMMAND = "systemctl --user {0} chipping-orchestrator.service"
_READY = (
    "The service can run: its settings resolve, every repository's token "
    "reaches it, and every agent is on its PATH"
)
_ENABLED = "Enabled chipping-orchestrator.service, which starts with the user manager from now on"
_LINGERING = (
    "Enabled linger for alice: the user manager, and the service with it, "
    "starts at boot and keeps running with nobody logged in"
)
_START = f"{_ENABLED}; init does not start it, so start it with: {_UNIT_COMMAND.format('start')}"


def _unit(environment: str) -> str:
    """The unit ``init`` writes for the case's interpreter with ``environment``."""
    return _support.UNIT_TEXT.format(interpreter=_EXEC_START, environment=environment)


class FirstInstallTest(_support.InitCase):
    """A first `init` checks the setup, writes the unit, enables it, and lingers the user.

    The unit is written for the interpreter running `init` and the absolute
    entries of the shell's `PATH`, each quoted the way systemd reads it back,
    and the service is enabled without being started.
    """

    def test_installs_and_enables_without_starting(self) -> None:
        status, stdout, stderr = self.run_init()

        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(self.written_unit(), _unit(_FIRST_PATH))
        self.assertEqual(tuple(self.timeline), _support.FIRST_INSTALL)
        self.assertEqual(
            stdout.splitlines(),
            [_READY, f"Wrote {self.unit_file}", _LINGERING, _START],
        )
        self.assert_setup_kept()


class RepeatedInitTest(_support.InitCase):
    """Run again, `init` rewrites the unit from the shell it runs in now.

    The `.env` and the token are left as they were, linger already on is not
    enabled again, and a running service is neither started nor restarted:
    `init` says to restart it instead.
    """

    def test_refreshes_the_unit_and_advises_a_restart(self) -> None:
        self.assertEqual(self.run_init()[0], 0)
        self.shell["PATH"] = _NEW_PATH
        self.systemd.answers.update({
            _support.SHOW_LINGER: _support.LINGERING,
            _support.IS_ACTIVE: _support.ACTIVE,
        })
        self.timeline.clear()

        status, stdout, stderr = self.run_init()

        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(self.written_unit(), _unit(f'"PATH={_NEW_PATH}"'))
        self.assertEqual(self.timeline, [
            _support.PROBE,
            _support.CHECKED,
            _support.RELOAD,
            _support.ENABLE,
            _support.SHOW_LINGER,
            _support.IS_ACTIVE,
        ])
        self.assertEqual(stdout.splitlines()[1:], [
            f"Refreshed {self.unit_file}",
            (
                f"{_ENABLED}; it is running as it was started, so restart it to run "
                f"the unit just written: {_UNIT_COMMAND.format('restart')}"
            ),
        ])
        self.assert_setup_kept()


class LingerRefusedTest(_support.InitCase):
    """Linger logind refuses to enable leaves the service installed, with the way to enable it."""

    def test_installs_and_says_how_to_linger(self) -> None:
        self.systemd.answers[_support.ENABLE_LINGER] = Completed(
            1, "", "Could not enable linger: Access denied\n",
        )

        status, stdout, stderr = self.run_init()

        self.assertEqual(status, 0)
        self.assertEqual(stderr, (
            "linger could not be enabled for alice (Could not enable linger: Access denied); "
            "until it is, the service runs only while alice is logged in. "
            "Enable it with: sudo loginctl enable-linger alice\n"
        ))
        self.assertEqual(tuple(self.timeline), _support.FIRST_INSTALL)
        self.assertEqual(stdout.splitlines(), [_READY, f"Wrote {self.unit_file}", _START])
        self.assertEqual(self.written_unit(), _unit(_FIRST_PATH))


class OnboardingSeamTest(_support.InitCase):
    """With no `.env`, a terminal is handed to the onboarding `init` is given.

    What it writes is then checked and installed for, as a `.env` found in
    place is.
    """

    def test_onboarding_at_a_terminal_writes_the_env(self) -> None:
        self._settings_file.unlink()

        status, _, stderr = self.run_init(terminal=True, onboard=self.onboard)

        self.assertEqual((status, stderr), (0, ""))
        self.assertEqual(
            tuple(self.timeline),
            (_support.PROBE, _support.ONBOARDED, *_support.FIRST_INSTALL[1:]),
        )
        self.assertEqual(self.written_unit(), _unit(_FIRST_PATH))
