# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What both launch forms answer before reading any configuration."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import unittest
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import NamedTuple

from orchestrator import __version__

_LaunchForm = tuple[str, list[str] | None]
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PACKAGE = "orchestrator"
_CONSOLE_SCRIPT = "chipping-orchestrator"
_RUN = "run"
_LAUNCH_TIMEOUT_SECONDS = 60
_MISSING_SCRIPT_REASON = f"{_CONSOLE_SCRIPT} is not installed; run `env -u VIRTUAL_ENV -u CONDA_PREFIX poetry sync`"
# A host that configures nothing, and one whose `REPOS` a run aborts on.
_UNCONFIGURED_HOSTS = ({}, {"REPOS": "not-a-repository-entry"})
_NOTHING = r"\A\Z"
_COMMAND_LISTING = rf"(?ms)\Ausage: {_CONSOLE_SCRIPT} .*^commands:$.*^ +{_RUN} +Run the polling process"
_VERSION_LINE = f"{_CONSOLE_SCRIPT} {__version__}"
_USAGE_ERROR = 2


class _Answer(NamedTuple):
    """A command line that runs nothing, and the exit and output it is answered with.

    Each stream is a pattern searched for in what the launch printed there, and
    `_NOTHING` matches only a stream left empty.
    """

    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str = _NOTHING


def _refused(*args: str) -> _Answer:
    """A `run` flag given before any command, answered with the `run` form meaning it."""
    run_form = re.escape(" ".join((_CONSOLE_SCRIPT, _RUN, *args)))
    return _Answer(
        args,
        _USAGE_ERROR,
        _NOTHING,
        rf"(?m)^{_CONSOLE_SCRIPT}: error: {args[0]} is accepted only after the run command: {run_form}\n\Z",
    )


_ANSWERS = (
    _Answer((), 0, _COMMAND_LISTING),
    _Answer(("--help",), 0, _COMMAND_LISTING),
    _Answer(("--version",), 0, rf"\A{re.escape(_VERSION_LINE)}\n\Z"),
    _Answer(
        (_RUN, "--help"),
        0,
        rf"(?s)\Ausage: {_CONSOLE_SCRIPT} {_RUN} .*--once.*--cleanup-terminal-artifacts.*--log-level",
    ),
    _refused("--once"),
    _refused("--cleanup-terminal-artifacts"),
    _refused("--log-level", "DEBUG"),
)


def _launch_forms() -> tuple[_LaunchForm, ...]:
    console_script = shutil.which(
        _CONSOLE_SCRIPT,
        path=str(Path(sys.executable).parent),
    )
    return (
        (_CONSOLE_SCRIPT, [console_script] if console_script else None),
        (f"python -m {_PACKAGE}", [sys.executable, "-m", _PACKAGE]),
    )


def _launch_unconfigured(
    command: list[str],
    args: tuple[str, ...],
    settings: dict[str, str],
    home: Path,
) -> subprocess.CompletedProcess:
    """Launch one form with `args` on a host configured with `settings`.

    The environment is the search path, a home of the run's own, and those
    settings alone, so no repository, token, allowlist, or user-location `.env`
    of the operator's configures it; the documented dotenv opt-out keeps the
    checkout's own `.env` out as well.
    """
    return subprocess.run(
        [*command, *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=_LAUNCH_TIMEOUT_SECONDS,
        env={
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(home),
            "ORCHESTRATOR_SKIP_DOTENV": "1",
            **settings,
        },
    )


class UnconfiguredLaunchTest(unittest.TestCase):
    """Every supported launch form reaches the same argument parser, and
    answers each command line that runs nothing before any configuration is
    read: on a host that configures no repository, and on one whose `REPOS` a
    run aborts on. A bare launch, like `--help`, prints the help listing every
    command; `--version` prints the distribution's; `run --help` lists the
    polling flags; and a polling flag given before any command is a usage
    error naming the `run` form that means it.

    Only those are spared that validation: a launch that goes on to run is
    stopped by the same `REPOS`, as `test_entrypoints` shows.
    """

    def test_each_answer_needs_no_configuration(self) -> None:
        for (form_name, command), settings, answer in product(
            _launch_forms(), _UNCONFIGURED_HOSTS, _ANSWERS,
        ):
            with self.subTest(form=form_name, settings=settings, args=answer.args):
                if command is None:
                    self.skipTest(_MISSING_SCRIPT_REASON)
                self._assert_answered(command, settings, answer)

    def _assert_answered(
        self,
        command: list[str],
        settings: dict[str, str],
        answer: _Answer,
    ) -> None:
        with TemporaryDirectory() as home:
            completed = _launch_unconfigured(command, answer.args, settings, Path(home))

        self.assertEqual(completed.returncode, answer.returncode, completed.stderr)
        self.assertRegex(completed.stdout, answer.stdout)
        self.assertRegex(completed.stderr, answer.stderr)


if __name__ == "__main__":
    unittest.main()
