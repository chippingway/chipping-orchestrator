# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a polling run is built from: options, clients, and the scheduler."""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from orchestrator import config
from orchestrator.runtime import startup
from tests.runtime import polling_test_support as _support

_GITHUB_CLIENT_ATTR = "GitHubClient"
_DEFAULT_SPECS_ATTR = "default_repo_specs"
_GLOBAL_CAP_ATTR = "MAX_PARALLEL_ISSUES_GLOBAL"
_PER_REPO_CAP_ATTR = "MAX_PARALLEL_ISSUES_PER_REPO"
_GLOBAL_CAP = 4
_PER_REPO_CAP = 3
_LEVEL_FLAG = "--log-level"
_DEBUG_LEVEL = "DEBUG"
_DEFAULT_LEVEL = "INFO"
_PROCESS_ARGV = ("chipping-orchestrator",)
_ONCE_FLAG = _support.ONCE_ARGS[0]
_CLEANUP_FLAG = "--cleanup-terminal-artifacts"


class OptionParsingTest(unittest.TestCase):
    """The launch mode and the log level are the whole command line, and an
    absent `argv` is the process's own.

    Two modes and neither is the default: a bare launch polls forever, and each
    flag is a run that ends on its own -- one tick, or one artifact
    reclamation.
    """

    def test_flags_and_defaults(self) -> None:
        for argv, expected in (
            ([], (False, False, _DEFAULT_LEVEL)),
            ([_ONCE_FLAG], (True, False, _DEFAULT_LEVEL)),
            ([_CLEANUP_FLAG], (False, True, _DEFAULT_LEVEL)),
            ([_LEVEL_FLAG, _DEBUG_LEVEL], (False, False, _DEBUG_LEVEL)),
            (
                [_ONCE_FLAG, _LEVEL_FLAG, _DEBUG_LEVEL],
                (True, False, _DEBUG_LEVEL),
            ),
        ):
            with self.subTest(argv=argv):
                options = startup.parse_options(argv)
                self.assertEqual(
                    (
                        options.once,
                        options.cleanup_terminal_artifacts,
                        options.log_level,
                    ),
                    expected,
                )

    def test_the_two_modes_are_exclusive(self) -> None:
        # Each flag names a whole run that ends on its own, so a command line
        # asking for both is refused rather than silently resolved to one.
        with (
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit),
        ):
            startup.parse_options([_ONCE_FLAG, _CLEANUP_FLAG])

    def test_absent_argv_reads_the_process_argv(self) -> None:
        with patch.object(sys, "argv", [*_PROCESS_ARGV, *_support.ONCE_ARGS]):
            options = startup.parse_options(None)

        self.assertTrue(options.once)


class ClientConnectionTest(unittest.TestCase):
    """One client per configured spec, each paired with the spec it was built
    for and each bootstrapped once. Re-running the label bootstrap per tick
    would burn API calls on a no-op, so it belongs to the connect.

    The read-only connect is the same pairing without that one write. A run
    that will not tick has no business creating or renaming a repository's
    labels, so a maintenance-only launch leaves even a repository that has
    never been driven exactly as it found it.
    """

    def test_one_bootstrapped_client_per_spec(self) -> None:
        clients = self.connect(startup.connect_clients)
        for github_client in clients.by_slug.values():
            github_client.ensure_workflow_labels.assert_called_once_with()

    def test_read_only_connect_writes_nothing(self) -> None:
        clients = self.connect(startup.connect_read_only_clients)
        for github_client in clients.by_slug.values():
            github_client.ensure_workflow_labels.assert_not_called()

    def connect(self, connect_clients) -> _support.ClientFactory:
        """Run one connect over two configured repositories, and hand back
        the clients it built for them."""
        specs = _support.repo_specs([_support.ALPHA_REPO, _support.BETA_REPO])
        clients = _support.ClientFactory()

        with (
            patch.object(config, _DEFAULT_SPECS_ATTR, return_value=specs),
            patch.object(startup, _GITHUB_CLIENT_ATTR, side_effect=clients),
        ):
            connected = connect_clients()

        self.assertEqual(
            [(spec.slug, github_client.slug) for spec, github_client in connected],
            [
                (_support.ALPHA_REPO, _support.ALPHA_REPO),
                (_support.BETA_REPO, _support.BETA_REPO),
            ],
        )
        return clients


class SchedulerConstructionTest(unittest.TestCase):
    """The host-wide and per-repo ceilings come off the configuration at
    build time, so a run is bounded by the environment it was started in.
    """

    def test_caps_come_from_the_configuration(self) -> None:
        with (
            patch.object(config, _GLOBAL_CAP_ATTR, _GLOBAL_CAP),
            patch.object(config, _PER_REPO_CAP_ATTR, _PER_REPO_CAP),
        ):
            scheduler = startup.create_scheduler()

        self.addCleanup(scheduler.shutdown)
        self.assertEqual(
            (scheduler.global_cap, scheduler.per_repo_cap),
            (_GLOBAL_CAP, _PER_REPO_CAP),
        )


if __name__ == "__main__":
    unittest.main()
