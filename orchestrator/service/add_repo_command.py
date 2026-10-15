# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""``add-repo`` on the command line: its options and how it answers.

``add_command`` puts ``add-repo`` on the parser ``orchestrator/cli.py``
chooses commands from, beside the setup commands ``commands`` puts there, with
the options it takes and the function that runs it. That function reads the
options into the answers ``add_repo.add_repo`` takes -- the core an
onboarding calls in process for each repository after the first -- and
answers 0 once the entry is written, or 1 with the core's refusal printed
alone on stderr.

A service reads ``REPOS`` only as it starts, so one already running goes on
managing the repositories it started with. Once the entry is written, the
installed service is asked whether it is active, through the ``systemd``
adapter ``init`` asks it through, and where it is the command says to
restart it. A manager that cannot be asked counts as no service running.

Nothing here imports ``orchestrator.config``, so ``add-repo`` answers on a
host whose settings would stop an import.
"""
from __future__ import annotations

import argparse
import dataclasses
import sys

from orchestrator.service import paths, systemd
from orchestrator.service.add_repo import COMMAND, AddRepoAnswers, AddRepoRefusal, add_repo
from orchestrator.service.unit_file import UNIT_NAME
from orchestrator.service.validation import FieldError

_ADDED = "Added {0} to REPOS in {1}\n"
_RESTART = (
    f"{UNIT_NAME} is running with the repositories it started with; restart "
    "it to manage {0} too: chipping-orchestrator restart\n"
)


def add_command(commands: argparse._SubParsersAction) -> None:
    """Put ``add-repo``, with its options, beneath ``commands``."""
    parser = commands.add_parser(
        COMMAND,
        help="Add a repository to the installed package's .env, without prompts.",
        description=(
            "Add the repository a local clone names to REPOS in "
            "~/.config/chipping-orchestrator/.env, editing the REPOS line in "
            "place and keeping every other line as it is. It refuses a missing "
            ".env and a repository REPOS already lists, and never writes a "
            "token; store one with set-token, and restart a running service "
            "for it to manage the repository."
        ),
    )
    parser.add_argument(
        "--clone", metavar="PATH", required=True, help="top of a local clone of the repository to add",
    )
    parser.add_argument(
        "--repo", metavar="OWNER/NAME", help="GitHub repository (default: the one the clone's GitHub remote names)",
    )
    parser.add_argument(
        "--base-branch",
        metavar="BRANCH",
        help="branch pull requests target (default: the remote's default branch, else the clone's current one)",
    )
    parser.add_argument(
        "--remote",
        metavar="NAME",
        help=(
            "the clone's remote that points at the repository (default: origin when it points at GitHub, "
            "else the only remote that does)"
        ),
    )
    parser.add_argument(
        "--parallel",
        metavar="N",
        help="issues of the repository run at once, written behind the remote (default: MAX_PARALLEL_ISSUES_PER_REPO)",
    )
    parser.set_defaults(dispatch=_add_repo)


def _add_repo(arguments: argparse.Namespace) -> int:
    """Run ``add-repo`` with the options given, and answer with its status."""
    answers = AddRepoAnswers(**{
        field.name: getattr(arguments, field.name)
        for field in dataclasses.fields(AddRepoAnswers)
    })
    try:
        entry = add_repo(answers)
    except (AddRepoRefusal, FieldError) as refused:
        sys.stderr.write(f"{refused}\n")
        return 1
    sys.stdout.write(_ADDED.format(entry.render(), paths.settings_file()))
    if systemd.systemctl("is-active", UNIT_NAME).succeeded:
        sys.stdout.write(_RESTART.format(entry.repository))
    return 0
