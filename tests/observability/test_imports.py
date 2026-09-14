# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import, layering, and surface checks for observability."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path

from tests.observability.observability_test_support import (
    _PACKAGE_ROOT,
    _PACKAGES,
    _imported_orchestrator_modules,
    _observability_modules,
    _observability_packages,
    _run_import_probe,
)

_TESTS_ROOT = Path(__file__).resolve().parents[1]

# What `import orchestrator` alone plants, so the cost check can hold each
# package to its own chain and nothing besides.
_ROOT_PACKAGE_MODULES = frozenset((
    "orchestrator",
))

# Nothing observed here is on the workflow's decision path, so the dependency
# runs one way: an application entrypoint composes these owners and no owner
# reads one back. On the tick side that is the workflow engine, the stage
# handlers, and the CLI and runtime loop under them. On the page side it is the
# two `streamlit run` targets under `apps`: those are entry points in the same
# sense the polling runtime is, they are what a migrated owner is composed
# *by*, and reading one back would drag Streamlit and Plotly in behind it.
_FORBIDDEN_PREFIXES = (
    "orchestrator.__main__",
    "orchestrator.apps",
    "orchestrator.cli",
    "orchestrator.runtime",
    "orchestrator.workflow",
)

# A manifest or a resolver hook under the tree would rebuild the lazy surface
# this destination replaces, and a `.pyi` is what such a surface needs to stay
# legible to a type checker. None of the three belongs here.
_RESOLVER_LEAF_GLOBS = ("*_exports.py", "*_manifest.py", "*.pyi")

_RESOLVER_HOOKS = ("__dir__", "__getattr__")


def _package_chain(package: str) -> frozenset[str]:
    """The package itself and every parent an import of it plants."""
    parts = package.split(".")
    depths = range(1, len(parts) + 1)
    return frozenset(".".join(parts[:depth]) for depth in depths)


def _mirrored_test_package(package: str) -> Path:
    """Initializer of the tests package that mirrors a runtime package."""
    return _TESTS_ROOT.joinpath(*package.split(".")[1:], "__init__.py")


class CleanProcessImportTest(unittest.TestCase):
    """Every module in the tree imports standalone in a fresh interpreter.

    A subprocess per module gives each one a `sys.modules` no earlier import
    has populated, which is the only place a cycle between two owners shows
    up at all: a suite that has already imported half the tree resolves the
    other half off what the first half left behind.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in _observability_modules():
            with self.subTest(module=module):
                completed = _run_import_probe(f"import {module}")
                self.assertEqual(
                    completed.returncode, 0, msg=completed.stderr,
                )


class LayeringTest(unittest.TestCase):
    """Each package costs its own chain and points away from the workflow."""

    def test_package_import_costs_only_its_own_chain(self) -> None:
        for package in _PACKAGES:
            with self.subTest(package=package):
                self.assertEqual(
                    _imported_orchestrator_modules(package),
                    _ROOT_PACKAGE_MODULES | _package_chain(package),
                )

    def test_no_module_reaches_the_workflow_layer(self) -> None:
        for module in _observability_modules():
            for imported in _imported_orchestrator_modules(module):
                with self.subTest(module=module, imported=imported):
                    self.assertFalse(
                        imported.startswith(_FORBIDDEN_PREFIXES),
                        f"{module} inverts the dependency via {imported}",
                    )


class PackageSurfaceTest(unittest.TestCase):
    """Initializers expose only submodules and install no lookup machinery."""

    def test_declared_packages_are_the_ones_on_disk(self) -> None:
        self.assertEqual(_observability_packages(), tuple(sorted(_PACKAGES)))

    def test_initializer_installs_no_resolver_hook(self) -> None:
        for package in _PACKAGES:
            initializer = import_module(package).__dict__
            for hook in _RESOLVER_HOOKS:
                with self.subTest(package=package, hook=hook):
                    self.assertNotIn(hook, initializer)

    def test_no_manifest_or_stub_leaf_in_the_tree(self) -> None:
        for leaf_glob in _RESOLVER_LEAF_GLOBS:
            with self.subTest(leaf_glob=leaf_glob):
                self.assertEqual(list(_PACKAGE_ROOT.rglob(leaf_glob)), [])

    def test_each_package_has_a_mirrored_test_package(self) -> None:
        for package in _PACKAGES:
            with self.subTest(package=package):
                self.assertTrue(_mirrored_test_package(package).is_file())


if __name__ == "__main__":
    unittest.main()
