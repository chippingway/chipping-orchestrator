# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""`configure` on the command line of an installed package never configured."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

from orchestrator.service import paths
from orchestrator.service.repos_entry import writable_field
from orchestrator.service.validation import validate_logins
from tests.service import configure_test_support as _support
from tests.service.service_test_support import refusal
from tests.support.installed_package import installed_copy

_REPO_ROOT = Path(__file__).resolve().parents[2]
_COMMAND = "configure"
_UNTRUSTED = "alice bob"
# A name git allows for a branch that a `REPOS` entry, split on `;`, cannot carry.
_SPLIT_BRANCH = "release;2.x"
_RUN_TIMEOUT_SECONDS = 60

# The command line as a launch form runs it, failing if that loaded the
# configuration: the state a first setup starts in is one where it exits.
_CONFIGURE_UNCONFIGURED = """
import sys
from orchestrator.cli import main

status = main(sys.argv[1:])
if "orchestrator.config" in sys.modules:
    sys.exit("configure imported orchestrator.config")
sys.exit(status)
"""

# What the configuration resolves from the `.env` `configure` wrote.
_READ_CONFIGURATION = """
from orchestrator import config

(spec,) = config.default_repo_specs()
print(spec.slug, spec.target_root, spec.base_branch, spec.remote_name)
print(*config.ALLOWED_ISSUE_AUTHORS)
print(*config.HITL_HANDLES)
print(config.DEV_AGENT, config.REVIEW_AGENT, config.DECOMPOSE_AGENT)
print(config.LOG_DIR)
"""


class ConfigureCommandTest(_support.ConfigureCase):
    """`configure` launched from an installed package on a host never configured.

    The package is a copy laid out the way a wheel installs it, launched from
    an unrelated directory with the case's home, its token, and its agents
    first on the PATH. Each launch is a fresh interpreter, so nothing an
    earlier import resolved stands in for what the command loads.
    """

    def setUp(self) -> None:
        super().setUp()
        self._launch = self._scratch / "launch"
        self._launch.mkdir()
        inherited = os.environ.get("PATH", os.defpath)
        self._environment = {
            "HOME": str(self._home),
            "PATH": os.pathsep.join((str(self._bin), inherited)),
            "PYTHONPATH": str(installed_copy(self._scratch / "site-packages")),
            "GITHUB_TOKEN": _support.TOKEN,
            **_support.HERMETIC_GIT,
        }

    def test_written_once_and_read_back(self) -> None:
        configured = self._configure("alice,bob")
        self.assertEqual(
            (configured.returncode, configured.stdout, configured.stderr),
            (0, f"Wrote {self._settings_file}\n", ""),
        )
        written = self._settings_file.read_text(encoding=_support.ENCODING)
        self.assertNotIn(_support.TOKEN, written)

        read = self._run(_READ_CONFIGURATION)
        again = self._configure("bob")

        self.assertEqual((read.returncode, read.stderr), (0, ""))
        self.assertEqual(read.stdout.splitlines(), [
            f"{_support.ACME} {self._clone} {_support.TRUNK} {_support.ORIGIN}",
            "alice bob",
            "alice bob",
            "claude codex claude",
            str(self._log_dir),
        ])
        self.assertEqual(
            (again.returncode, again.stdout, again.stderr),
            (1, "", f"{_support.existing_refusal(self._settings_file)}\n"),
        )
        self.assertEqual(self._settings_file.read_text(encoding=_support.ENCODING), written)

    def test_a_refused_answer_names_its_option(self) -> None:
        """A field's validator, and the entry it is written into, alike."""
        for authors, options, expected in (
            (_UNTRUSTED, (), f"--authors: {refusal(validate_logins, _UNTRUSTED)}"),
            (
                _support.AUTHOR,
                ("--base-branch", _SPLIT_BRANCH),
                f"--base-branch: {refusal(writable_field, _SPLIT_BRANCH)}",
            ),
        ):
            with self.subTest(options=options):
                refused = self._configure(authors, *options)

                self.assertEqual(
                    (refused.returncode, refused.stdout, refused.stderr),
                    (1, "", f"{expected}\n"),
                )
                self.assertFalse(self._settings_file.parent.exists())

    def test_a_source_checkout_is_refused(self) -> None:
        self._environment["PYTHONPATH"] = str(_REPO_ROOT)
        expected = paths.source_checkout_refusal(_COMMAND, _REPO_ROOT)

        refused = self._configure(_support.AUTHOR)

        self.assertEqual(
            (refused.returncode, refused.stdout, refused.stderr),
            (1, "", f"{expected}\n"),
        )
        self.assertFalse(self._settings_file.parent.exists())

    def _configure(self, authors: str, *options: str) -> subprocess.CompletedProcess[str]:
        return self._run(
            _CONFIGURE_UNCONFIGURED,
            _COMMAND,
            "--clone",
            str(self._clone),
            "--authors",
            authors,
            *options,
        )

    def _run(self, program: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (sys.executable, "-c", program, *arguments),
            cwd=self._launch,
            env=self._environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=_RUN_TIMEOUT_SECONDS,
        )


if __name__ == "__main__":
    unittest.main()
