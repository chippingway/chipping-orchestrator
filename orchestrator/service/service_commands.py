# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The commands that manage the systemd user service, on the command line.

``add_commands`` puts each of them on the parser ``orchestrator/cli.py``
chooses commands from, beside the setup commands ``commands`` puts there, with
the function that runs it. ``init`` takes no options: it hands this process's
environment and standard input to ``installation.init``, which answers with
the exit status itself.

Nothing here imports ``orchestrator.config``, and neither does the core it
calls, so ``init`` answers on a host with no configuration at all.
"""
from __future__ import annotations

import argparse
import os
import sys

from orchestrator.service.installation import COMMAND as INIT, init


def add_commands(commands: argparse._SubParsersAction) -> None:
    """Put each service command beneath ``commands``."""
    parser = commands.add_parser(
        INIT,
        help="Install or refresh the systemd user service, and enable it without starting it.",
        description=(
            "Check the setup as check does, GitHub included, then write "
            "~/.config/systemd/user/chipping-orchestrator.service for this "
            "interpreter and the absolute entries of this shell's PATH, have "
            "the user manager reload its units and enable it, and enable linger "
            "so it runs with nobody logged in. The service is never started or "
            "restarted; run init again to refresh the unit, which leaves .env "
            "and the token files as they are. It needs an existing .env: write "
            "one first with set-token and configure."
        ),
    )
    parser.set_defaults(dispatch=_init)


def _init(arguments: argparse.Namespace) -> int:
    """Run ``init`` for the service set up from this environment, and answer with its status."""
    return init(os.environ, sys.stdin)
