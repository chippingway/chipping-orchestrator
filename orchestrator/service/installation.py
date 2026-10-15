# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""``init``: the systemd user service installed or refreshed, and enabled without starting it.

``init`` installs ``unit_file``'s unit for the setup an installed package
reads, asking ``systemd`` for everything it needs from the user manager and
logind. Every refusal comes before anything is written, in this order, each
one exiting 1 with its message on stderr:

- the package runs from its own source checkout, which reads a ``.env`` no
  installed service reads: the refusal every setup command gives it;
- the hand-written ``orchestrator.service`` is installed, so a second service
  would poll beside it: the operator stops, disables, and deletes it first;
- the interpreter running ``init``, or the ``PATH`` captured from the shell,
  is a value the unit cannot carry;
- ``systemctl --user`` reaches no user manager to install the service into;
- no installed ``.env`` exists. With a terminal, ``onboard`` is where one is
  written instead -- the one place an onboarding meets this command -- and
  otherwise the refusal names ``set-token`` and ``configure``, which write the
  tokens and the file without prompts;
- the full ``check``, GitHub calls included, finds a problem, each printed as
  ``check`` prints it.

Then the unit is written whole, replacing any unit there, the manager reloads
its units, and the service is enabled -- never started, nor restarted when it
runs already. A manager that will not reload or enable it exits 1 too, the
unit left written for the next ``init`` to take up. A user manager runs only while its user is logged in unless
logind lingers it, so linger is enabled where ``loginctl show-user`` does not
report it already; where logind refuses, ``init`` still succeeds, saying the
service runs only while the user is logged in until ``sudo loginctl
enable-linger`` is run. ``init`` ends by naming the ``start`` command that
starts the service, or, where it runs already, the ``restart`` that has it run
the unit just written.

Run again, ``init`` finds the ``.env`` in place and leaves it, and the token
files, as they were: it writes the unit afresh, with the interpreter and the
``PATH`` it runs with now, and enables it again. Nothing here imports
``orchestrator.config``; the settings are read in the interpreter ``check``
starts, and only once a ``.env`` exists.
"""
from __future__ import annotations

import getpass
import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TextIO

from orchestrator.service import checks, paths, systemd
from orchestrator.service.environment import captured_path
from orchestrator.service.private_files import private_directory, write_private
from orchestrator.service.unit_file import (
    UNIT_NAME,
    UnitValueError,
    legacy_unit_refusal,
    render_unit,
    unit_path,
)

COMMAND = "init"

# What writes the installed `.env` where none exists, given the shell `init`
# runs from and the terminal it was started at.
Onboarding = Callable[[Mapping[str, str], TextIO], None]

_UNCONFIGURED = (
    "no configuration exists at {0}, and init installs the service only for "
    "one; write it without prompts -- store each repository's token with "
    "chipping-orchestrator set-token OWNER/NAME, then run "
    "chipping-orchestrator configure --clone PATH --authors LOGINS -- and run "
    "init again"
)
_NO_MANAGER = (
    "systemctl --user cannot reach a systemd user manager ({0}), and init "
    "installs a systemd user service; run init as the service's user, in a "
    "login session that has a manager -- an ssh or desktop login rather than "
    "su or sudo -- and try again"
)
_UNCHECKED = "init installed nothing: the service would not run until the problems above are repaired"
_FAILED_STEP = (
    "systemctl --user {0} failed ({1}); {2} is written, so run init again "
    "once the user manager takes it"
)
_ENABLED = f"Enabled {UNIT_NAME}, which starts with the user manager from now on"
_START = f"{_ENABLED}; init does not start it, so start it with: chipping-orchestrator start\n"
_RESTART = (
    f"{_ENABLED}; it is running as it was started, so restart it to run the "
    "unit just written: chipping-orchestrator restart\n"
)
_LINGERING = (
    "Enabled linger for {0}: the user manager, and the service with it, "
    "starts at boot and keeps running with nobody logged in\n"
)
_NOT_LINGERING = (
    "linger could not be enabled for {0} ({1}); until it is, the service runs "
    "only while {0} is logged in. Enable it with: sudo loginctl enable-linger {0}\n"
)


class InitRefusal(Exception):
    """Why ``init`` stops, the whole diagnostic as its text."""


def init(
    shell: Mapping[str, str],
    stdin: TextIO,
    *,
    onboard: Onboarding | None = None,
    package_root: Path = paths.PACKAGE_ROOT,
) -> int:
    """Run ``init`` for the service set up from ``shell``, and answer with its status.

    ``shell`` gives the service its environment, as ``check`` reads it, and
    the unit its ``PATH``. ``onboard`` writes the ``.env`` where none exists
    and ``stdin`` is a terminal; without it, a missing ``.env`` is refused
    there too.
    """
    try:
        _install(shell, stdin, onboard, package_root)
    except InitRefusal as refused:
        sys.stderr.write(f"{refused}\n")
        return 1
    return 0


def _install(
    shell: Mapping[str, str],
    stdin: TextIO,
    onboard: Onboarding | None,
    package_root: Path,
) -> None:
    """Install the unit for ``shell``'s service, every refusal coming before any write."""
    unit_text = _unit_text(shell, package_root)
    _require_settings(shell, stdin, onboard)
    if checks.check(shell, reach_github=True) != 0:
        raise InitRefusal(_UNCHECKED)
    _write_and_enable(unit_text)
    _ensure_linger(shell)
    running = systemd.systemctl("is-active", UNIT_NAME).succeeded
    sys.stdout.write(_RESTART if running else _START)


def _unit_text(shell: Mapping[str, str], package_root: Path) -> str:
    """The unit to install for ``shell``, once nothing about this host refuses one."""
    refusal = paths.source_checkout_refusal(COMMAND, package_root) or legacy_unit_refusal()
    if refusal is not None:
        raise InitRefusal(refusal)
    try:
        unit_text = render_unit(sys.executable, captured_path(shell.get("PATH", "")))
    except UnitValueError as refused:
        raise InitRefusal(str(refused)) from refused
    problem = systemd.manager_problem()
    if problem is not None:
        raise InitRefusal(_NO_MANAGER.format(problem))
    return unit_text


def _require_settings(
    shell: Mapping[str, str],
    stdin: TextIO,
    onboard: Onboarding | None,
) -> None:
    """Make sure the installed ``.env`` exists, handing a terminal to ``onboard`` where it does not."""
    settings_file = paths.settings_file()
    if os.path.lexists(settings_file):
        return
    if onboard is None or not stdin.isatty():
        raise InitRefusal(_UNCONFIGURED.format(settings_file))
    onboard(shell, stdin)


def _write_and_enable(unit_text: str) -> None:
    """Write ``unit_text`` as the unit, then have the manager reload and enable it."""
    unit = unit_path()
    written = "Refreshed" if unit.exists() else "Wrote"
    try:
        private_directory(unit.parent)
    except OSError as error:
        raise InitRefusal(f"{unit.parent} cannot be created ({error})") from error
    try:
        write_private(unit, unit_text, replace=True)
    except OSError as error:
        raise InitRefusal(f"{unit} cannot be written ({error})") from error
    sys.stdout.write(f"{written} {unit}\n")
    for step in (("daemon-reload",), ("enable", UNIT_NAME)):
        done = systemd.systemctl(*step)
        if not done.succeeded:
            raise InitRefusal(_FAILED_STEP.format(" ".join(step), done.reason(), unit))


def _ensure_linger(shell: Mapping[str, str]) -> None:
    """Have logind linger the user's manager, saying how to where it will not."""
    user = shell.get("USER") or getpass.getuser()
    if systemd.linger_enabled(user):
        return
    enabled = systemd.loginctl("--no-ask-password", "enable-linger", user)
    if enabled.succeeded:
        sys.stdout.write(_LINGERING.format(user))
    else:
        sys.stderr.write(_NOT_LINGERING.format(user, enabled.reason()))
