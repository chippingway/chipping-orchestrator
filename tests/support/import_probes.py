# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One clean-interpreter import per target, read back by every guard that asks.

A package guard asks two things about the same import. Whether the module
loads at all in an interpreter no earlier import has populated, which is the
only place a cycle between two owners shows up: a suite that has already
imported half a tree resolves the other half off what the first half left
behind. And what that load planted in `sys.modules`, which is what a layering
or import-cost assertion is read off. Both answers come out of the same run, so
one recording carries the return code, the standard error, and the planted set
rather than a subprocess being spent per question.

The recording is cached per target, because a clean interpreter's answer for a
module cannot vary inside a run and a guard sweeping a tree asks after most of
its modules several times. The cache holds for one environment only -- this
interpreter, importing the named target and nothing else. A probe that blocks
an import root, stages two imports in an order, or exits on what it found is a
different question asked in a different environment, and stays on the separate
run its own guard's script gives it.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from functools import cache

# The package under test, which is the prefix a layering or cost assertion
# reads the planted set against.
_ORCHESTRATOR = "orchestrator"

# `sys.modules` in full rather than narrowed to one prefix: an entrypoint guard
# holds a launch path to its own chain *and* to the optional dependency group
# it must not cost, and both are answered off the one recorded set.
_PROBE_SCRIPT = """
import sys
import {module}
print(*sorted(sys.modules))
"""


@dataclass(frozen=True)
class ImportProbe:
    """What one clean interpreter reported for a single `import module`."""

    returncode: int
    stderr: str
    modules: frozenset[str]

    @property
    def orchestrator_modules(self) -> frozenset[str]:
        """The planted modules that belong to the package under test."""
        return frozenset(
            name for name in self.modules
            if name == _ORCHESTRATOR or name.startswith(f"{_ORCHESTRATOR}.")
        )


@cache
def probe_import(module: str) -> ImportProbe:
    """Import `module` in a fresh interpreter and record what it reported.

    An import that fails is recorded rather than raised on, so the guard
    asking whether the module imports standalone is the one that reports the
    traceback -- and reports it as a failed assertion against the module it
    named, instead of as an error raised out of a helper.
    """
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE_SCRIPT.format(module=module)],
        capture_output=True,
        text=True,
        check=False,
    )
    return ImportProbe(
        returncode=completed.returncode,
        stderr=completed.stderr,
        modules=frozenset(completed.stdout.split()),
    )
