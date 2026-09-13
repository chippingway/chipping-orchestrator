# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import, layering, and surface checks for the stage package."""

from __future__ import annotations

import importlib
import subprocess
import sys
import unittest
from pathlib import Path
from types import MappingProxyType

from orchestrator.workflow.engine import dispatch as _dispatch, pickup as _pickup
from orchestrator.workflow.stages import implementing as _package
from orchestrator.workflow.state import WorkflowLabel

_PACKAGE = "orchestrator.workflow.stages.implementing"

_PARENT = "orchestrator.workflow.stages"

_HANDLER_OWNER = "handler"

_OWNERS = (
    "checkout_guards",
    "checkout_recovery",
    "continue_command",
    "dev_pr",
    "disposition",
    "drift",
    "drift_preflight",
    "execution",
    "handoff",
    _HANDLER_OWNER,
    "late_accepted",
    "late_authority",
    "late_authorship",
    "late_claims",
    "late_command",
    "late_consent",
    "late_debt",
    "late_evidence",
    "late_freeze",
    "late_gate",
    "late_overflow",
    "late_parks",
    "late_publication",
    "late_push",
    "late_reconcile",
    "late_records",
    "late_rollback",
    "late_recovery",
    "late_rewrite",
    "late_rotation",
    "late_transfer",
    "late_transfer_telemetry",
    "late_verdict",
    "models",
    "parks",
    "plan_handoff",
    "plan_reading",
    "publication",
    "read_only_relabel",
    "relabel_evidence",
    "relabel_hazard",
    "relabel_refusal",
    "resume",
    "resume_request",
    "retry_cap",
    "session",
    "session_read",
    "spawn",
    "state",
    "worktree",
)

# Bound at module scope, so collecting this file is what plants every owner in
# `sys.modules` -- the same protection each sibling owner package gets from its
# own import test, and what keeps an owner from being first imported by a test
# that has already reloaded the modules it binds.
_OWNER_MODULES = MappingProxyType({
    owner: importlib.import_module(f"{_PACKAGE}.{owner}") for owner in _OWNERS
})

_IMPORTED_SCRIPT = """
import sys
import {module}
print(*sorted(name for name in sys.modules if name.startswith('orchestrator')))
"""

_HANDLE_IMPLEMENTING = "_handle_implementing"


def _imported_orchestrator_modules(module: str) -> set[str]:
    """Names of the orchestrator modules a fresh `import module` plants."""
    completed = subprocess.run(
        [sys.executable, "-c", _IMPORTED_SCRIPT.format(module=module)],
        capture_output=True,
        text=True,
        check=True,
    )
    return set(completed.stdout.split())


class CleanProcessImportTest(unittest.TestCase):
    """The package and each owner beneath it import alone.

    The owners import each other and reach the engine, whose dispatcher reaches
    back into this package. A subprocess per module gives each a clean
    `sys.modules` no other test has already populated, exposing an import-order
    cycle a package-first suite run would mask.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in (_PACKAGE, *(f"{_PACKAGE}.{owner}" for owner in _OWNERS)):
            with self.subTest(module=module):
                completed = subprocess.run(
                    [sys.executable, "-c", f"import {module}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)


class LayeringTest(unittest.TestCase):
    """The initializer costs the package above it and nothing else."""

    def test_initializer_reaches_no_owner(self) -> None:
        # An eager owner binding here would charge a park or a session read for
        # the publication path it never reaches -- and for the worktree, GitHub,
        # and analytics subsystems those sit on.
        self.assertEqual(
            _imported_orchestrator_modules(_PACKAGE),
            _imported_orchestrator_modules(_PARENT) | {_PACKAGE},
        )


class PackageSurfaceTest(unittest.TestCase):
    """The initializer is a package marker that owns no names."""

    def test_package_sits_under_the_stage_package(self) -> None:
        self.assertEqual(_package.__name__, _PACKAGE)
        initializer = Path(_package.__file__)
        self.assertEqual(initializer.name, "__init__.py")
        self.assertEqual(initializer.parent.name, "implementing")
        self.assertIs(importlib.import_module(_PARENT).implementing, _package)

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
    """The dispatcher and the pickup start name the handler owner."""

    def test_label_resolves_to_the_handler_owner(self) -> None:
        # A dispatched handler is resolved off the module the table names, so
        # that is where a patch has to land to intercept one.
        owner = _OWNER_MODULES[_HANDLER_OWNER]
        self.assertEqual(
            _dispatch._STAGE_HANDLER_TARGETS[WorkflowLabel.IMPLEMENTING],
            (owner.__name__, _HANDLE_IMPLEMENTING),
        )
        self.assertTrue(hasattr(owner, _HANDLE_IMPLEMENTING))

    def test_decompose_off_start_names_the_owner(self) -> None:
        # `DECOMPOSE=off` dispatches the handler inside the pickup tick, so the
        # legacy start reads it off the owner for the same reason.
        source = Path(_pickup.__file__).read_text(encoding="utf-8")
        self.assertIn(
            f"from {_PACKAGE}.{_HANDLER_OWNER} import {_HANDLE_IMPLEMENTING}", source,
        )


if __name__ == "__main__":
    unittest.main()
