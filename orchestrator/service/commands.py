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
``set-token`` takes the repository alone and hands it, with standard input,
to ``tokens.set_token``, which reads, proves, and keeps the token and answers
with the status itself.

A ``set-token`` command line may carry the token anywhere -- as a further
argument, an option's value, a value handed to a flag that takes none, or in
front of the command -- and every refusal argparse writes quotes what it
refused, into whatever log the command line ran under. ``parser_class`` is
how ``orchestrator/cli.py`` builds its parser for a command line, and for one
naming ``set-token`` it is a class whose every refusal, in that parser and
each built beneath it, gives the usage and the form the command takes and
prints back none of what it was given.

Nothing here imports ``orchestrator.config``, and neither does any core it
calls, so a setup command answers on a host with no configuration at all.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import sys
from collections.abc import Sequence
from typing import NamedTuple, NoReturn

from orchestrator.service.configure import (
    COMMAND as CONFIGURE,
    DEFAULT_DECOMPOSE_AGENT,
    DEFAULT_DEV_AGENT,
    DEFAULT_REVIEW_AGENT,
    ConfigureAnswers,
    ConfigureRefusal,
    configure,
)
from orchestrator.service.tokens import set_token
from orchestrator.service.validation import FieldError

_SET_TOKEN = "set-token"
_UNQUOTED_REFUSAL = (
    f"error: this {_SET_TOKEN} command line is not printed back, in case it holds "
    f"the token: {_SET_TOKEN} takes OWNER/NAME alone, and reads the token from "
    "standard input, piped in, redirected from a file, or typed at the prompt\n"
)
_USAGE_ERROR = 2

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


class _UnquotingParser(argparse.ArgumentParser):
    """A parser whose every refusal leaves out what the command line said.

    Each parser beneath it is built from the same class, so a refusal raised
    while a command reads its own arguments is held to it as well. Help and
    the version still print: neither quotes the command line.
    """

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(_USAGE_ERROR, f"{self.prog}: {_UNQUOTED_REFUSAL}")


def parser_class(command_line: Sequence[str]) -> type[argparse.ArgumentParser]:
    """The class ``command_line`` is parsed with: one quoting none of it for ``set-token``."""
    return _UnquotingParser if _SET_TOKEN in command_line else argparse.ArgumentParser


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
    token_parser = commands.add_parser(
        _SET_TOKEN,
        help="Verify a repository's GitHub token from standard input and save it.",
        description=(
            "Read the GitHub token for OWNER/NAME from standard input, at a "
            "hidden prompt on a terminal, prove it reads the repository with "
            "one read-only GitHub call, and write it to "
            "~/.config/OWNER/NAME/token, replacing any token there. The file "
            "is owner-only in an owner-only directory, and .env is not touched."
        ),
    )
    token_parser.add_argument(
        "repository", metavar="OWNER/NAME", help="the GitHub repository the token is for",
    )
    token_parser.set_defaults(dispatch=_set_token)


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


def _set_token(arguments: argparse.Namespace) -> int:
    """Run ``set-token`` for the repository given, and answer with its status."""
    return set_token(arguments.repository, sys.stdin)
