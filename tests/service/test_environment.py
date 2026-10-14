# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The environment a service set up from a shell runs with."""
from __future__ import annotations

import os
import unittest

from orchestrator.service.environment import captured_path, service_environment

_PATH = "PATH"
_SYSTEM = "/usr/bin"
_AGENTS = "/opt/agents"


def _path(*entries: str) -> str:
    """``entries`` joined the way a ``PATH`` is."""
    return os.pathsep.join(entries)


class CapturedPathTest(unittest.TestCase):
    """Only the absolute entries of a shell's PATH are kept, in its order."""

    def test_empty_and_relative_entries_are_dropped(self) -> None:
        for shell_path, captured in (
            (_path(_AGENTS, _SYSTEM), _path(_AGENTS, _SYSTEM)),
            (_path(_AGENTS, "", "bin", "./tools", "~/.local/bin", _SYSTEM), _path(_AGENTS, _SYSTEM)),
            (_path("bin", ""), ""),
            ("", ""),
        ):
            with self.subTest(shell_path=shell_path):
                self.assertEqual(captured_path(shell_path), captured)


class ServiceEnvironmentTest(unittest.TestCase):
    """HOME, USER, and the captured PATH cross from the shell, and nothing else does."""

    def test_only_home_user_and_path_cross(self) -> None:
        shell = {
            "HOME": "/home/alice",
            "USER": "alice",
            _PATH: _path(_SYSTEM, "bin"),
            "GITHUB_TOKEN": "ghp_exported",
            "REPOS": "acme/api|/home/alice/api|main",
            "ALLOWED_ISSUE_AUTHORS": "alice",
            "CLAUDE_BIN": "/opt/claude",
            "ORCHESTRATOR_SKIP_DOTENV": "1",
            "ORCHESTRATOR_TOKEN_FILE": "/home/alice/token",
            "PYTHONPATH": "/home/alice/lib",
        }

        service = service_environment(shell)

        self.assertEqual(service, {"HOME": "/home/alice", "USER": "alice", _PATH: _SYSTEM})
        self.assertEqual(service_environment(service), service)

    def test_path_set_where_the_shell_has_none(self) -> None:
        self.assertEqual(service_environment({}), {_PATH: ""})
