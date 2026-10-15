# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commands that manage the systemd user service, on the command line.

``add_commands`` puts each of them on the parser ``orchestrator/cli.py``
chooses commands from, beside the setup commands ``commands`` puts there, with
the function that runs it, in the order a service is managed: ``init``,
``start``, ``stop``, ``restart``, ``status``, and ``remove``. None takes an
option. ``init`` hands this process's environment and standard input to
``installation.init``, ``start`` and ``restart`` hand its environment to
``starting.launch``, and ``stop``, ``status``, and ``remove`` read nothing of
it; each core answers with the exit status itself.

Nothing here imports ``orchestrator.config``, and neither does any core it
calls, so every service command answers on a host with no configuration at
all.
"""
from __future__ import annotations

import argparse
import os
import sys
from functools import partial

from orchestrator.service import lifecycle, removal, starting
from orchestrator.service.installation import COMMAND as INIT, init
from orchestrator.service.unit_file import UNIT_NAME


def add_commands(commands: argparse._SubParsersAction) -> None:
    """Put each service command beneath ``commands``."""
    parser = commands.add_parser(
        INIT,
        help="Install or refresh the systemd user service, and enable it without starting it.",
        description=(
            "Check the setup as check does, GitHub included, then write "
            f"~/.config/systemd/user/{UNIT_NAME} for this "
            "interpreter and the absolute entries of this shell's PATH, have "
            "the user manager reload its units and enable it, and enable linger "
            "so it runs with nobody logged in. The service is never started or "
            "restarted; run init again to refresh the unit, which leaves .env "
            "and the token files as they are. It needs an existing .env: write "
            "one first with set-token and configure."
        ),
    )
    parser.set_defaults(dispatch=_init)
    for command, summary, description, dispatch in _LIFECYCLE:
        commands.add_parser(command, help=summary, description=description).set_defaults(dispatch=dispatch)


def _init(arguments: argparse.Namespace) -> int:
    """Run ``init`` for the service set up from this environment, and answer with its status."""
    return init(os.environ, sys.stdin)


def _launch(command: str, arguments: argparse.Namespace) -> int:
    """Run ``start`` or ``restart`` for the service set up from this environment, and answer with its status."""
    return starting.launch(command, os.environ)


def _stop(arguments: argparse.Namespace) -> int:
    """Run ``stop``, and answer with its status."""
    return lifecycle.stop()


def _status(arguments: argparse.Namespace) -> int:
    """Run ``status``, and answer with its status."""
    return lifecycle.status()


def _remove(arguments: argparse.Namespace) -> int:
    """Run ``remove``, and answer with its status."""
    return removal.remove()


# Each command after `init`: its name, its line in the command listing, its
# own help, and what runs it.
_LAUNCHED = (
    "First check the setup as check --local does, with no GitHub call, in the "
    "environment and directory the installed service would get -- what its "
    "unit and drop-ins set over what the user manager's ManagerEnvironment=, "
    "DefaultEnvironment=, and environment.d hand it -- asking systemd nothing "
    "if that finds a problem or they cannot be read as systemd would assemble "
    "them; then have the user manager reload its units and {0} the service, "
    "watch it for 5 seconds, and report it active, or print the last lines of "
    "its journal and exit 1."
)
_LIFECYCLE = (
    (
        starting.START,
        "Check the setup locally, then start the service and confirm it stays active.",
        f"Start {UNIT_NAME}. {_LAUNCHED.format('start')}",
        partial(_launch, starting.START),
    ),
    (
        lifecycle.STOP,
        "Stop the service, which stays enabled.",
        (
            f"Have the user manager stop {UNIT_NAME}, which ends the poller as a "
            "signal does. The service stays enabled, so it starts again with "
            "the user manager, as at boot."
        ),
        _stop,
    ),
    (
        starting.RESTART,
        "Check the setup locally, then restart the service and confirm it stays active.",
        (
            f"Restart {UNIT_NAME}, as after editing .env. "
            f"{_LAUNCHED.format('restart')} A problem the check finds leaves a running service running."
        ),
        partial(_launch, starting.RESTART),
    ),
    (
        lifecycle.STATUS,
        "Show the installed version, configuration, and unit, and the service's state.",
        (
            "Print the package version, the configuration file, and the unit "
            f"file, then systemctl --user status --no-pager {UNIT_NAME}, and exit "
            "with its status."
        ),
        _status,
    ),
    (
        removal.COMMAND,
        "Stop, disable, and delete the service's unit, keeping everything else.",
        (
            f"Stop and disable {UNIT_NAME}, delete its unit, and have the user "
            "manager reload its units and forget a failure. The configuration, "
            "the token files, the logs, the worktrees, and linger are kept. "
            "Without an installed unit it does nothing."
        ),
        _remove,
    ),
)
