# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""``stop`` and ``status`` for the service ``init`` installs, and what every lifecycle command shares.

The lifecycle commands -- ``start`` and ``restart`` in ``starting``, ``stop``
and ``status`` here, and ``remove`` in ``removal`` -- act on the unit ``init``
installed through the calling user's own manager. Each but ``status`` answers
through ``answered``: 0 with its report on stdout, or 1 with the whole reason
it stopped on stderr, raised as a ``ServiceRefusal``. ``require_manager``
refuses where ``systemctl --user`` reaches no user manager, naming the command
and where to run it instead, and ``act`` has the manager run one step,
refusing with the step and the manager's own last word where it fails. Each
such step is bounded by ``STOP_SECONDS`` rather than the adapter's 30, since
one that stops the service waits on systemd, which gives a unit 90 seconds to
stop before killing it, and a poller draining its agents may take most of
them; the other steps never come near either bound.

``stop`` stops the service and leaves it enabled, so the user manager starts
it again the next time it starts. ``status`` prints the package version, the
installed ``.env``, and the unit, each marked where it is missing, then the
output of ``systemctl --user status --no-pager``, and exits with that
command's status, so a script reads the manager's own answer: 3 for a service
that is not running, 4 for no such unit.

Nothing here imports ``orchestrator.config``: a lifecycle command that shows,
stops, or removes an installation reads no setting, so it answers on a host
whose settings would stop an import.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable

from orchestrator import __version__
from orchestrator.service import paths, systemd
from orchestrator.service.unit_file import UNIT_NAME, unit_path

STOP = "stop"
STATUS = "status"

# Past the 90 seconds systemd gives a unit to stop before it kills it.
STOP_SECONDS = 120

_NO_MANAGER = (
    "systemctl --user cannot reach a systemd user manager ({0}), which the "
    "service runs under; run chipping-orchestrator {1} as the service's user, "
    "in a login session that has a manager -- an ssh or desktop login rather "
    "than su or sudo -- and try again"
)
_FAILED = "systemctl --user {0} failed ({1}){2}"
_STOPPED = (
    f"Stopped {UNIT_NAME}; it is still enabled, so it starts again with the "
    "user manager, as at boot: chipping-orchestrator start runs it now\n"
)
_MISSING = " (missing)"


class ServiceRefusal(Exception):
    """Why a lifecycle command stops, the whole diagnostic as its text."""


def answered(steps: Callable[[], str]) -> int:
    """Run ``steps``, printing the report it returns or the refusal it raises, and answer 0 or 1."""
    try:
        report = steps()
    except ServiceRefusal as refused:
        sys.stderr.write(f"{refused}\n")
        return 1
    sys.stdout.write(report)
    return 0


def require_manager(command: str) -> None:
    """Refuse ``command`` where ``systemctl --user`` reaches no user manager."""
    problem = systemd.manager_problem()
    if problem is not None:
        raise ServiceRefusal(_NO_MANAGER.format(problem, command))


def act(*arguments: str, advice: str = "") -> None:
    """Have the user manager run ``systemctl --user`` with ``arguments``, within ``STOP_SECONDS``.

    Where it fails, the refusal names the step and the manager's reason,
    followed by ``advice``.
    """
    done = systemd.systemctl(*arguments, timeout=STOP_SECONDS)
    if not done.succeeded:
        raise ServiceRefusal(_FAILED.format(" ".join(arguments), done.reason(), advice))


def stop() -> int:
    """Run ``stop``, and answer with its status."""
    return answered(_stop)


def _stop() -> str:
    """Stop the service, once the manager answers."""
    require_manager(STOP)
    act(STOP, UNIT_NAME)
    return _STOPPED


def status() -> int:
    """Print what is installed and the service's state, and answer with ``systemctl --user status``'s exit status."""
    sys.stdout.write(f"chipping-orchestrator {__version__}\n")
    for described, path in (("Configuration", paths.settings_file()), ("Unit", unit_path())):
        missing = "" if os.path.lexists(path) else _MISSING
        sys.stdout.write(f"{described}: {path}{missing}\n")
    try:
        require_manager(STATUS)
    except ServiceRefusal as refused:
        sys.stderr.write(f"{refused}\n")
        return 1
    shown = systemd.systemctl(STATUS, "--no-pager", UNIT_NAME)
    if shown.status is None:
        sys.stderr.write(f"{_FAILED.format(STATUS, shown.reason(), '')}\n")
        return 1
    sys.stdout.write(shown.stdout)
    sys.stderr.write(shown.stderr)
    return shown.status
