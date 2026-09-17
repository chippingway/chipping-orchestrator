# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One interpreter per probed target, reused by every guard that asks for it.

The suite's package guards sweep whole trees -- two hundred owners under
`orchestrator/observability` alone -- and each asks after most of its modules
more than once: whether the module imports in an interpreter nothing else has
populated, and what that import planted. Taking the recording once per target
and reading it back afterwards is what holds a sweep to one interpreter per
module instead of one per question, and none of the guards observes it: drop
the memo and every one of them still passes, at twice the launches. This is
where it is observed instead, together with the recorded fields the guards
divide between them -- the return code and traceback one asserts on, the
planted set the others are read off.
"""
from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from tests.support import import_probes as _probes

# Names no module answers on, so a recording that escaped this module could
# not be read back by a guard as some real owner's.
_TARGET = "orchestrator.probe_target"

_OTHER_TARGET = "orchestrator.probe_target_sibling"

# A planted set spanning what the projection has to divide: the root package,
# a module beneath it, a third-party root, and a name that merely starts with
# the package's letters -- a sibling of `orchestrator` rather than a part of
# it, and what a prefix test written as a bare string match would swallow.
_PLANTED = ("json", "orchestrator", _TARGET, "orchestratorish", "sys")

_UNDER_TEST = frozenset(("orchestrator", _TARGET))

_PLANTED_LINE = " ".join(_PLANTED)

# What the probe script's `print` leaves on stdout.
_STDOUT = f"{_PLANTED_LINE}\n"

_TRACEBACK = "Traceback (most recent call last):\nModuleNotFoundError: nope\n"


class _Launcher:
    """Answer every launch with one canned result, and record the scripts."""

    def __init__(
        self, returncode: int = 0, stdout: str = "", stderr: str = "",
    ) -> None:
        self._returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.scripts: list[str] = []

    def __call__(self, args, **kwargs) -> subprocess.CompletedProcess[str]:
        self.scripts.append(args[-1])
        return subprocess.CompletedProcess(
            args=args,
            returncode=self._returncode,
            stdout=self._stdout,
            stderr=self._stderr,
        )


def _launching(launcher: _Launcher):
    """Answer the producer's own `subprocess.run` with `launcher`."""
    return patch.object(_probes.subprocess, "run", launcher)


def _imports(script: str) -> list[str]:
    """The import statements one probe script is built out of."""
    return [
        line for line in script.splitlines()
        if line.startswith("import ")
    ]


class _ProbeCase(unittest.TestCase):
    """Leave the process-wide memo as empty as it was found.

    A canned recording left in it would be handed to the next guard that named
    the same target, and the real recordings already in it answer for modules
    this case never launched. Dropping it either side is what keeps the two
    apart.
    """

    def setUp(self) -> None:
        _probes.probe_import.cache_clear()
        self.addCleanup(_probes.probe_import.cache_clear)


class ProbeReuseTest(_ProbeCase):
    """A target is launched once, and every other target on its own."""

    def test_an_identical_target_is_launched_once(self) -> None:
        launcher = _Launcher(stdout=_STDOUT)
        with _launching(launcher):
            first = _probes.probe_import(_TARGET)
            second = _probes.probe_import(_TARGET)
        self.assertEqual(len(launcher.scripts), 1)
        self.assertIs(first, second)

    def test_each_target_is_launched_on_its_own(self) -> None:
        # One target per script as well as per launch: a batch would answer
        # for a module in an interpreter the targets ahead of it had already
        # populated, which is the state the recording exists to rule out.
        launcher = _Launcher()
        targets = (_TARGET, _OTHER_TARGET)
        with _launching(launcher):
            for target in targets:
                _probes.probe_import(target)
        self.assertEqual(len(launcher.scripts), len(targets))
        for target, script in zip(targets, launcher.scripts, strict=True):
            with self.subTest(target=target):
                self.assertEqual(
                    _imports(script),
                    ["import sys", f"import {target}"],
                )


class ProbeRecordingTest(_ProbeCase):
    """The recording carries what the interpreter reported, failure included."""

    def test_a_successful_run_is_recorded_whole(self) -> None:
        launcher = _Launcher(stdout=_STDOUT)
        with _launching(launcher):
            probe = _probes.probe_import(_TARGET)
        self.assertEqual(
            probe,
            _probes.ImportProbe(
                returncode=0, stderr="", modules=frozenset(_PLANTED),
            ),
        )
        self.assertEqual(probe.orchestrator_modules, _UNDER_TEST)

    def test_a_failed_import_is_recorded_not_raised(self) -> None:
        # The return code and the traceback belong to the guard that asks
        # whether the module imports standalone: raising here would report the
        # failure against whichever guard happened to name the target first.
        launcher = _Launcher(returncode=1, stderr=_TRACEBACK)
        with _launching(launcher):
            probe = _probes.probe_import(_TARGET)
        self.assertEqual(
            probe,
            _probes.ImportProbe(
                returncode=1, stderr=_TRACEBACK, modules=frozenset(),
            ),
        )


if __name__ == "__main__":
    unittest.main()
