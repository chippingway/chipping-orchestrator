# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The `run` command's options: which launch mode a run is, and how loud.

This owner imports no configuration, directly or through another owner, and
that is why it stands apart from `startup`: every other owner under `runtime/`
resolves and validates the settings as it is imported, so a command line read
there could only be answered on a host whose configuration already holds up.
Read here, `run --help` and a refused command line answer on a host nobody has
configured yet, or one whose `REPOS` would abort the run itself.

The flags belong to `run` alone, and `orchestrator/cli.py` puts them on that
command's parser. The parser the commands are chosen from gets a hidden twin of
each, because the launch lines and units written for v0.13.0 and earlier give
the flag with no command at all: the twin answers one with the `run` form that
means it, where argparse alone would report only "unrecognized arguments".
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass

COMMAND = "run"

_LOG_LEVEL_FLAG = "--log-level"

# The two launch modes, each with the help it is listed under.
_MODES = (
    ("--once", "Run a single tick and exit."),
    (
        "--cleanup-terminal-artifacts",
        (
            "Reclaim the worktrees and branches of finished issues, then "
            "exit. Polls no issue and writes no workflow state: no label, no "
            "pinned state, no comment. It does delete the orchestrator-owned "
            "branches it proved reclaimable, in the local clone and on the "
            "remote. Defers entirely while another orchestrator process is "
            "live on this host."
        ),
    ),
)


@dataclass(frozen=True)
class PollingOptions:
    """Parsed command-line options: which mode a run is, and how loud."""

    once: bool
    cleanup_terminal_artifacts: bool
    log_level: str


class _MisplacedRunFlag(argparse.Action):
    """A `run` flag given before any command, refused with the form meaning it."""

    def __call__(self, parser, namespace, flag_values, option_string=None):
        flag = self.option_strings[0]
        run_form = " ".join((parser.prog, COMMAND, flag, *flag_values))
        parser.error(f"{option_string} is accepted only after the {COMMAND} command: {run_form}")


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """Put the launch modes and the log level on the `run` command's parser."""
    # Exclusive rather than ordered: each flag names a whole run that ends on
    # its own, so a command line asking for both is a mistake worth reporting
    # instead of one whose meaning an operator has to look up.
    modes = parser.add_mutually_exclusive_group()
    for flag, mode_help in _MODES:
        modes.add_argument(flag, action="store_true", help=mode_help)
    parser.add_argument(_LOG_LEVEL_FLAG, default="INFO")


def refuse_before_command(parser: argparse.ArgumentParser) -> None:
    """Refuse every `run` flag on the parser the commands are chosen from."""
    for flag, _mode_help in _MODES:
        _add_misplaced(parser, flag, 0)
    _add_misplaced(parser, _LOG_LEVEL_FLAG, 1)


def polling_options(arguments: argparse.Namespace) -> PollingOptions:
    """Read the launch mode and log level off a parsed `run` command line."""
    return PollingOptions(
        once=arguments.once,
        cleanup_terminal_artifacts=arguments.cleanup_terminal_artifacts,
        log_level=arguments.log_level,
    )


def _add_misplaced(parser: argparse.ArgumentParser, flag: str, value_count: int) -> None:
    # Suppressed both ways: the twin is in no help listing, and it leaves no
    # attribute that could shadow the one the `run` parser sets.
    parser.add_argument(
        flag,
        action=_MisplacedRunFlag,
        nargs=value_count,
        default=argparse.SUPPRESS,
        help=argparse.SUPPRESS,
    )
