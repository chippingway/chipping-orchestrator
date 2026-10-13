# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Launch-form coverage for the console script and module entry point."""
from __future__ import annotations

import os
import subprocess
import sys
import tomllib
import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

from orchestrator import cli

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = "orchestrator"
_MODULE_LAUNCH = f"{_PACKAGE}.__main__"
_CONSOLE_SCRIPT = "chipping-orchestrator"
_ENTRY_POINT = "orchestrator.cli:main"
_RUN = "run"
_ONCE_FLAG = "--once"
_LAUNCH_TIMEOUT_SECONDS = 60
_ALLOWLIST_ENV = "ALLOWED_ISSUE_AUTHORS"
_MISSING_ALLOWLIST = (
    "ALLOWED_ISSUE_AUTHORS must contain at least one GitHub login. "
    "Configure it before starting the orchestrator, for example: "
    "ALLOWED_ISSUE_AUTHORS=alice,bob"
)
# Unset, then empty, whitespace-only, comma-only, and emptied by the `@`
# normalization: every value that names nobody once it is parsed.
_EMPTY_ALLOWLISTS = (None, "", "   ", " , ,", " @ , @@ ")
_REPOS_ENV = "REPOS"
_TRUSTED_AUTHOR = "operator"
# One entry that is not `owner/name|target_root|base_branch`, which the
# configuration refuses while it is resolved.
_MALFORMED_REPOS = "not-a-repository-entry"
_MALFORMED_REPOS_ERROR = "orchestrator: REPOS entry #1 is malformed"


def _run_once(
    allowed_authors: str | None,
    scratch: Path,
    repos: str | None = None,
) -> subprocess.CompletedProcess:
    """Launch one `run --once` through the module form, allowlist as given.

    No token and a checkout root of the run's own, so that a launch which ever
    got past the allowlist would still fail before reaching GitHub or the
    operator's host rather than tick against either. `repos`, where given,
    is the run's `REPOS`; otherwise it inherits whatever the caller's has.
    """
    environment = {
        name: env_value
        for name, env_value in os.environ.items()
        if name != _ALLOWLIST_ENV
    }
    environment.update({
        "ORCHESTRATOR_SKIP_DOTENV": "1",
        "GITHUB_TOKEN": "",
        "ORCHESTRATOR_TOKEN_FILE": str(scratch / "token"),
        "WORKTREES_DIR": str(scratch / "worktrees"),
    })
    if allowed_authors is not None:
        environment[_ALLOWLIST_ENV] = allowed_authors
    if repos is not None:
        environment[_REPOS_ENV] = repos
    return subprocess.run(
        [sys.executable, "-m", _PACKAGE, _RUN, _ONCE_FLAG],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=_LAUNCH_TIMEOUT_SECONDS,
        env=environment,
    )


class EntryPointTargetTest(unittest.TestCase):
    """Both launch forms name the one composition point.

    The `chipping-orchestrator` console script is the canonical launch command,
    so its declared target has to keep resolving to the CLI's `main` even when
    the project is not installed into the environment; `python -m orchestrator`
    is the form `run.sh` starts and reaches the same function.
    """

    def test_declared_console_target_is_cli_main(self) -> None:
        manifest = tomllib.loads(
            (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        )
        declared_scripts = manifest["project"]["scripts"]
        declared_target = declared_scripts[_CONSOLE_SCRIPT]
        module_name, attribute_name = declared_target.split(":")

        self.assertEqual(declared_scripts, {_CONSOLE_SCRIPT: _ENTRY_POINT})
        self.assertEqual(declared_target, _ENTRY_POINT)
        self.assertIs(
            getattr(import_module(module_name), attribute_name),
            cli.main,
        )

    def test_module_launch_form_runs_the_same_main(self) -> None:
        self.assertIs(import_module(_MODULE_LAUNCH).main, cli.main)


class MalformedRepositoryLaunchTest(unittest.TestCase):
    """A launch that goes on to run meets the configuration first: a `REPOS`
    the configuration refuses stops it with status 1 on the error naming the
    entry, printing nothing to stdout. The command lines that run nothing
    answer on that same host, as `test_unconfigured_launch` shows.
    """

    def test_malformed_repos_stops_a_run(self) -> None:
        with TemporaryDirectory() as scratch:
            completed = _run_once(_TRUSTED_AUTHOR, Path(scratch), repos=_MALFORMED_REPOS)

        self.assertEqual(completed.returncode, 1, completed.stderr)
        self.assertTrue(
            completed.stderr.startswith(_MALFORMED_REPOS_ERROR), completed.stderr,
        )
        self.assertEqual(completed.stdout, "")


class EmptyAllowlistLaunchTest(unittest.TestCase):
    """A launch whose author allowlist names nobody exits with status 1 on
    the error that says how to configure it, printing nothing to stdout.
    """

    def test_each_empty_spelling_stops_the_launch(self) -> None:
        for allowed_authors in _EMPTY_ALLOWLISTS:
            with self.subTest(allowed_authors=allowed_authors), TemporaryDirectory() as scratch:
                completed = _run_once(allowed_authors, Path(scratch))

                self.assertEqual(completed.returncode, 1, completed.stderr)
                self.assertEqual(completed.stderr.splitlines()[-1:], [_MISSING_ALLOWLIST])
                self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
