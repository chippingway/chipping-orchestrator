# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The setup commands on the command line: their options and how they answer.

``add_commands`` puts each setup command on the parser ``orchestrator/cli.py``
chooses commands from, with the options it takes and the function that runs
it. That function reads the options into the answers the command's core takes
-- the same core an onboarding calls in process -- and answers with an exit
status: 0 once the core has done its work, or 1 with the core's refusal
printed alone on stderr, the way every command and prompt words it.

``configure`` checks its agents against the ``PATH`` the command runs with.

Nothing here imports ``orchestrator.config``, and neither does any core it
calls, so a setup command answers on a host with no configuration at all.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from typing import NamedTuple

from orchestrator.service.configure import (
    COMMAND as CONFIGURE,
    DEFAULT_DECOMPOSE_AGENT,
    DEFAULT_DEV_AGENT,
    DEFAULT_REVIEW_AGENT,
    ConfigureAnswers,
    ConfigureRefusal,
    configure,
)
from orchestrator.service.validation import FieldError

_LOGINS = "LOGINS"
_AGENT = "AGENT"
_AGENT_CHOICE = "claude, codex, or agy (default: %(default)s)"


class _Option(NamedTuple):
    """One option of a setup command, and how it is listed in the help."""

    flag: str
    metavar: str
    summary: str
    default: str | None = None
    required: bool = False


# The two required options have no default: the clone, and the authors, who
# decide whose issues and comments the orchestrator trusts.
_CONFIGURE_OPTIONS = (
    _Option("--clone", "PATH", "top of a local clone of the repository to manage", required=True),
    _Option(
        "--authors",
        _LOGINS,
        "comma-separated GitHub logins whose issues and comments the orchestrator acts on",
        required=True,
    ),
    _Option("--repo", "OWNER/NAME", "GitHub repository (default: the one the clone's GitHub remote names)"),
    _Option(
        "--base-branch",
        "BRANCH",
        "branch pull requests target (default: that remote's default branch, else the clone's current one)",
    ),
    _Option(
        "--notify",
        _LOGINS,
        "comma-separated GitHub logins to mention when a human is needed (default: the authors)",
    ),
    _Option("--dev-agent", _AGENT, f"agent that implements: {_AGENT_CHOICE}", DEFAULT_DEV_AGENT),
    _Option("--review-agent", _AGENT, f"agent that reviews: {_AGENT_CHOICE}", DEFAULT_REVIEW_AGENT),
    _Option("--decompose-agent", _AGENT, f"agent that decomposes: {_AGENT_CHOICE}", DEFAULT_DECOMPOSE_AGENT),
)


def add_commands(commands: argparse._SubParsersAction) -> None:
    """Put each setup command, with its options, beneath ``commands``."""
    parser = commands.add_parser(
        CONFIGURE,
        help="Write the installed package's .env for one repository, without prompts.",
        description=(
            "Write ~/.config/chipping-orchestrator/.env from the basic template "
            "for the repository a local clone names. It refuses to overwrite an "
            "existing .env and never writes a token into it."
        ),
    )
    for option in _CONFIGURE_OPTIONS:
        parser.add_argument(
            option.flag,
            metavar=option.metavar,
            help=option.summary,
            default=option.default,
            required=option.required,
        )
    parser.set_defaults(dispatch=_configure)


def _configure(arguments: argparse.Namespace) -> int:
    """Run ``configure`` with the options given, and answer with its status."""
    answers = ConfigureAnswers(**{
        field.name: getattr(arguments, field.name)
        for field in dataclasses.fields(ConfigureAnswers)
    })
    try:
        written = configure(answers, search_path=os.environ.get("PATH", os.defpath))
    except (ConfigureRefusal, FieldError) as refused:
        sys.stderr.write(f"{refused}\n")
        return 1
    sys.stdout.write(f"Wrote {written}\n")
    return 0
