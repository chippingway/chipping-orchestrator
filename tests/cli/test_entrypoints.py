# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Launch-form coverage for the console script and module entry point."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
import unittest
from importlib import import_module
from pathlib import Path

from orchestrator import cli

_LaunchForm = tuple[str, list[str] | None]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = "orchestrator"
_MODULE_LAUNCH = f"{_PACKAGE}.__main__"
_CONSOLE_SCRIPT = "chipping-orchestrator"
_ENTRY_POINT = "orchestrator.cli:main"
_HELP_FLAG = "--help"
_ONCE_FLAG = "--once"
_HELP_TIMEOUT_SECONDS = 60
_MISSING_SCRIPT_REASON = f"{_CONSOLE_SCRIPT} is not installed; run `uv sync`"


def _console_script() -> str | None:
    return shutil.which(
        _CONSOLE_SCRIPT,
        path=str(Path(sys.executable).parent),
    )


def _launch_forms() -> tuple[_LaunchForm, ...]:
    console_script = _console_script()
    return (
        (_CONSOLE_SCRIPT, [console_script] if console_script else None),
        (f"python -m {_PACKAGE}", [sys.executable, "-m", _PACKAGE]),
    )


def _run_help(command: list[str]) -> subprocess.CompletedProcess:
    # `orchestrator.config` resolves `.env` at import, so pin the documented
    # opt-out to keep the subprocess independent of the operator's file.
    return subprocess.run(
        [*command, _HELP_FLAG],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=_HELP_TIMEOUT_SECONDS,
        env={**os.environ, "ORCHESTRATOR_SKIP_DOTENV": "1"},
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


class LaunchFormHelpTest(unittest.TestCase):
    """Every supported launch form reaches the same argument parser."""

    def test_launch_forms_print_usage(self) -> None:
        for form_name, command in _launch_forms():
            with self.subTest(form=form_name):
                if command is None:
                    self.skipTest(_MISSING_SCRIPT_REASON)
                completed = _run_help(command)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertIn(_ONCE_FLAG, completed.stdout)


if __name__ == "__main__":
    unittest.main()
