# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import, layering, and surface checks for the stage package."""

from __future__ import annotations

import importlib
import unittest
from pathlib import Path
from types import MappingProxyType

from orchestrator.workflow.engine import stage_targets as _stage_targets
from orchestrator.workflow.stages import validating as _package
from orchestrator.workflow.state import WorkflowLabel
from tests.support.import_probes import probe_import

_PACKAGE = "orchestrator.workflow.stages.validating"

_PARENT = "orchestrator.workflow.stages"

_HANDLER_OWNER = "handler"

_OWNERS = (
    "approval",
    "collapse",
    "awaiting",
    "awaiting_resume",
    "dev_fix",
    "drift",
    "drift_models",
    "drift_outcomes",
    "handoff",
    _HANDLER_OWNER,
    "models",
    "recovery",
    "requested_changes",
    "reviewer",
    "state",
    "stranded",
    "verify",
    "watermarks",
)

# Bound at module scope, so collecting this file is what plants every owner in
# `sys.modules` -- the same protection each sibling owner package gets from its
# own import test, and what keeps an owner from being first imported by a test
# that has already reloaded the modules it binds.
_OWNER_MODULES = MappingProxyType({
    owner: importlib.import_module(f"{_PACKAGE}.{owner}") for owner in _OWNERS
})

_HANDLE_VALIDATING = "_handle_validating"


class CleanProcessImportTest(unittest.TestCase):
    """The package and each owner beneath it import alone.

    The owners import each other and reach the engine and the verification
    runner, and the engine's dispatcher reaches back into this package. A
    recording per module gives each a clean `sys.modules` no other test has
    already populated, exposing an import-order cycle a package-first suite run
    would mask. It is the recording the layering check below reads its planted
    set off, so asking both questions costs one interpreter per module.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in (_PACKAGE, *(f"{_PACKAGE}.{owner}" for owner in _OWNERS)):
            with self.subTest(module=module):
                probe = probe_import(module)
                self.assertEqual(probe.returncode, 0, msg=probe.stderr)


class LayeringTest(unittest.TestCase):
    """The initializer costs the package above it and nothing else."""

    def test_initializer_reaches_no_owner(self) -> None:
        # An eager owner binding here would charge a park or a watermark walk
        # for the reviewer spawn it never reaches -- and for the worktree,
        # GitHub, verification, and analytics subsystems those sit on.
        self.assertEqual(
            probe_import(_PACKAGE).orchestrator_modules,
            probe_import(_PARENT).orchestrator_modules | {_PACKAGE},
        )


class PackageSurfaceTest(unittest.TestCase):
    """The initializer is a package marker that owns no names."""

    def test_package_sits_under_the_stage_package(self) -> None:
        self.assertEqual(_package.__name__, _PACKAGE)
        initializer = Path(_package.__file__)
        self.assertEqual(initializer.name, "__init__.py")
        self.assertEqual(initializer.parent.name, "validating")
        self.assertIs(importlib.import_module(_PARENT).validating, _package)

    def test_initializer_binds_only_submodules(self) -> None:
        for owner, module in _OWNER_MODULES.items():
            with self.subTest(owner=owner):
                self.assertIs(getattr(_package, owner), module)
        for name, bound in _package.__dict__.items():
            if name.startswith("__"):
                continue
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(bound, "__name__", None), f"{_PACKAGE}.{name}",
                )


class DispatchTargetTest(unittest.TestCase):
    """The dispatcher names the handler owner."""

    def test_label_resolves_to_the_handler_owner(self) -> None:
        # A dispatched handler is resolved off the module the table names, so
        # that is where a patch has to land to intercept one.
        owner = _OWNER_MODULES[_HANDLER_OWNER]
        self.assertEqual(
            _stage_targets._STAGE_HANDLER_TARGETS[WorkflowLabel.VALIDATING],
            (owner.__name__, _HANDLE_VALIDATING),
        )
        self.assertTrue(hasattr(owner, _HANDLE_VALIDATING))


if __name__ == "__main__":
    unittest.main()
