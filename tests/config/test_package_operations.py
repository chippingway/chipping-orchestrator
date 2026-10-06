# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The documented local configuration check in an installed package layout."""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.config import config_test_support as _support

_REPO_ROOT = Path(__file__).resolve().parents[2]
_OPERATIONS_GUIDE = _REPO_ROOT / "docs" / "configuration" / "operations.md"
_CHECK_TIMEOUT_SECONDS = 15
_REPOS_ENV = "REPOS"


def _documented_check() -> str:
    """Read the Python snippet operators run, so its imports cannot drift."""
    section = _OPERATIONS_GUIDE.read_text(encoding="utf-8").split(
        "### Check compatibility and start\n", 1,
    )[1]
    fenced = section.split("```sh\n", 1)[1]
    block = fenced.split("```", 1)[0]
    shell_lines = (line.removesuffix("\\") for line in block.splitlines())
    arguments = shlex.split("\n".join(shell_lines))
    return arguments[arguments.index("-c") + 1]


class InstalledConfigurationCheckTest(unittest.TestCase):
    """The exact guide snippet validates user settings without credentials.

    Copying the package outside any checkout and launching from an unrelated
    directory makes the installed `.env` resolver answer. A fresh interpreter
    per check also exposes any dependency on import-time settings resolution.
    """

    def setUp(self) -> None:
        self._root = Path(self.enterContext(tempfile.TemporaryDirectory())).resolve()
        installed = self._root / "site-packages"
        shutil.copytree(
            _REPO_ROOT / "orchestrator", installed / "orchestrator",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        self._launch = self._root / "launch"
        self._launch.mkdir()
        self._dotenv = self._root / "home" / ".config" / "chipping-orchestrator" / ".env"
        self._dotenv.parent.mkdir(parents=True)
        target = _support.make_checkout(self._root / "target")
        self._settings = {
            _REPOS_ENV: f"owner/project|{target}|main",
            "ALLOWED_ISSUE_AUTHORS": "alice",
            "LOG_DIR": str(self._root / "logs"),
        }
        self._environment = {
            "HOME": str(self._root / "home"),
            "PATH": os.environ.get("PATH", os.defpath),
            "PYTHONPATH": str(installed),
        }

    def test_valid_settings_need_no_credentials(self) -> None:
        completed = self._run_check({})

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "Configuration OK\n")
        self.assertEqual(completed.stderr, "")

    def test_invalid_settings_report_the_problem(self) -> None:
        for overrides, diagnostic in (
            ({_REPOS_ENV: ""}, _REPOS_ENV),
            ({"ALLOWED_ISSUE_AUTHORS": ""}, "ALLOWED_ISSUE_AUTHORS"),
        ):
            with self.subTest(overrides=overrides):
                completed = self._run_check(overrides)

                self.assertEqual(completed.returncode, 1, completed.stderr)
                self.assertIn(diagnostic, completed.stderr)
                self.assertEqual(completed.stdout, "")

    def _run_check(self, overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
        settings = {**self._settings, **overrides}
        self._dotenv.write_text(
            "".join(f"{key}={setting}\n" for key, setting in settings.items()),
            encoding="utf-8",
        )
        return subprocess.run(
            (sys.executable, "-c", _documented_check()),
            cwd=self._launch,
            env=self._environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=_CHECK_TIMEOUT_SECONDS,
        )
