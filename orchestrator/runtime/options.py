# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which launch mode a run is, and how loud: the command line and nothing else.

This owner imports no configuration, directly or through another owner, and
that is why it stands apart from `startup`: every other owner under `runtime/`
resolves and validates the settings as it is imported, so a command line read
there could only be answered on a host whose configuration already holds up.
Read here, `--help` and a refused command line answer on a host nobody has
configured yet, or one whose `REPOS` would abort the run itself.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class PollingOptions:
    """Parsed command-line options: which mode a run is, and how loud."""

    once: bool
    cleanup_terminal_artifacts: bool
    log_level: str


def parse_options(argv: list[str] | None) -> PollingOptions:
    """Parse the launch mode and log level a run was started with."""
    parser = argparse.ArgumentParser(
        description="chipping-orchestrator polling loop.",
    )
    # Exclusive rather than ordered: each flag names a whole run that ends on
    # its own, so a command line asking for both is a mistake worth reporting
    # instead of one whose meaning an operator has to look up.
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--once",
        action="store_true",
        help="Run a single tick and exit.",
    )
    modes.add_argument(
        "--cleanup-terminal-artifacts",
        action="store_true",
        help=(
            "Reclaim the worktrees and branches of finished issues, then "
            "exit. Polls no issue and writes no workflow state: no label, no "
            "pinned state, no comment. It does delete the orchestrator-owned "
            "branches it proved reclaimable, in the local clone and on the "
            "remote. Defers entirely while another orchestrator process is "
            "live on this host."
        ),
    )
    parser.add_argument("--log-level", default="INFO")
    parsed_options = parser.parse_args(argv)
    return PollingOptions(
        once=parsed_options.once,
        cleanup_terminal_artifacts=parsed_options.cleanup_terminal_artifacts,
        log_level=parsed_options.log_level,
    )
