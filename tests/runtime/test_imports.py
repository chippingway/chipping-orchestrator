# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, clean-process import, and layering checks for the runtime."""
from __future__ import annotations

import subprocess
import sys
import unittest
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

_ORCHESTRATOR = "orchestrator"

_PACKAGE = f"{_ORCHESTRATOR}.runtime"

# The declared inventory. A new owner is a deliberate edit here and a paragraph
# in the package's own map, which is what the inventory check compares the
# directory against.
_MODULES = tuple(
    f"{_PACKAGE}.{owner}"
    for owner in (
        "artifact_records",
        "artifact_schedule",
        "artifacts",
        "exclusion",
        "host_lock",
        "logs",
        "loop",
        "self_update",
        "shutdown",
        "startup",
        "state",
        "ticks",
    )
)

# The composition point above the owners, and the launch forms that reach it.
# An owner that named one of them would put the startup order behind an import
# of the thing being started.
_COMPOSITION_MODULES = (
    f"{_ORCHESTRATOR}.cli",
    f"{_ORCHESTRATOR}.__main__",
    f"{_ORCHESTRATOR}.apps",
)

# The module paths a second polling runtime would take: the entry-point facade
# the owners were reached through, its static inventory and dependency hub, and
# one leaf per responsibility that has an owner here now.
_RETIRED_MODULES = (
    f"{_ORCHESTRATOR}.main",
    f"{_ORCHESTRATOR}._main_api",
    f"{_ORCHESTRATOR}._main_dependencies",
    f"{_ORCHESTRATOR}._main_logging",
    f"{_ORCHESTRATOR}._main_loop",
    f"{_ORCHESTRATOR}._main_self_update",
    f"{_ORCHESTRATOR}._main_setup",
    f"{_ORCHESTRATOR}._main_shutdown",
    f"{_ORCHESTRATOR}._main_ticks",
)

# What `import orchestrator` alone plants, so the surface check can hold the
# initializer to its own chain and nothing besides.
_ROOT_MODULES = (_ORCHESTRATOR,)

_PROBE = """
import sys
import {module}
print(*sorted(sys.modules))
"""


def _planted(module: str) -> frozenset[str]:
    """Names of the modules a fresh `import module` leaves loaded."""
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
    )
    return frozenset(completed.stdout.split())


class RuntimeInventoryTest(unittest.TestCase):
    """The declared owners are the ones on disk, and none is published above."""

    def test_declared_modules_are_the_ones_on_disk(self) -> None:
        directory = Path(import_module(_PACKAGE).__file__).parent
        found = tuple(sorted(
            module_path.stem
            for module_path in directory.glob("*.py")
            if module_path.stem != "__init__"
        ))
        self.assertEqual(found, tuple(sorted(
            module.rpartition(".")[2] for module in _MODULES
        )))

    def test_the_initializer_publishes_nothing(self) -> None:
        # An owner is named by the composition that drives it, so a binding
        # here would put every other owner's import behind naming any one of
        # them -- and would hand a caller a second site to patch a collaborator
        # on.
        initializer = import_module(_PACKAGE)
        self.assertNotIn("__all__", initializer.__dict__)
        for name, bound in initializer.__dict__.items():
            if name.startswith("__"):
                continue
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(bound, "__name__", ""), f"{_PACKAGE}.{name}",
                )


class CleanProcessImportTest(unittest.TestCase):
    """Each owner imports standalone, and none pulls the composition back.

    A subprocess per module gives each a clean `sys.modules` no other test has
    already populated, so an owner that reached back up to `cli` -- or sideways
    into an app -- shows up here rather than in whichever run happened to
    import the package first.
    """

    def test_each_owner_imports_without_the_cli(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                planted = _planted(module)
                self.assertEqual(
                    sorted(planted & frozenset(_COMPOSITION_MODULES)),
                    [],
                )

    def test_naming_the_package_costs_no_owner(self) -> None:
        self.assertEqual(
            tuple(sorted(
                name for name in _planted(_PACKAGE)
                if name.startswith(_ORCHESTRATOR)
            )),
            tuple(sorted((*_ROOT_MODULES, _PACKAGE))),
        )


class RetiredRuntimeModuleTest(unittest.TestCase):
    """No polling runtime answers beside the owners."""

    def test_no_retired_module_exists(self) -> None:
        # Anything importable at these paths would be a second identity for the
        # loop, the signal handling, and the process-wide state a live
        # deployment runs on -- free to drift from the owners silently, and
        # invisible to a patch aimed at one. Resolving the spec rather than
        # stat-ing a path catches a copy planted anywhere the interpreter would
        # find it.
        for module in _RETIRED_MODULES:
            with self.subTest(module=module):
                self.assertIsNone(find_spec(module))


if __name__ == "__main__":
    unittest.main()
