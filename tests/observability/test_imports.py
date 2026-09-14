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
    _PUBLISHING_PACKAGES,
    _imported_orchestrator_modules,
    _observability_modules,
    _observability_packages,
    _payable_import,
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


def _is_own_submodule(package: str, name: str, bound: object) -> bool:
    """Whether `name` binds a submodule of `package` under its own name.

    A private alias is excused the name match: that is how a publishing
    initializer holds the owner it re-exports from.
    """
    parent, _, leaf = getattr(bound, "__name__", "").rpartition(".")
    return parent == package and (name.startswith("_") or name == leaf)


def _undeclared_bindings(package: str) -> tuple[str, ...]:
    """Names an initializer binds that are neither declared nor its owners."""
    initializer = import_module(package)
    published = frozenset(getattr(initializer, "__all__", ()))
    return tuple(
        name
        for name, bound in initializer.__dict__.items()
        if not name.startswith("__")
        and name not in published
        and not _is_own_submodule(package, name, bound)
    )


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
        # A marker initializer binds nothing, so importing one owner must not
        # charge the importer for its siblings: a stage that wants the
        # recording path would otherwise pay for the query owners and the
        # database driver under them.
        for package in frozenset(_PACKAGES) - _PUBLISHING_PACKAGES:
            with self.subTest(package=package):
                self.assertEqual(
                    _imported_orchestrator_modules(package),
                    _ROOT_PACKAGE_MODULES | _package_chain(package),
                )

    def test_a_publishing_package_costs_its_owners(self) -> None:
        # A package that publishes a surface pays for the owners behind it,
        # which is what an importer buys by naming the package rather than
        # one of them, plus the siblings it composes -- declared per package,
        # so a new chain behind an import is a deliberate edit. What it must
        # still not pay for is anything else.
        for package in _PUBLISHING_PACKAGES:
            planted = _imported_orchestrator_modules(package)
            outside = planted - _ROOT_PACKAGE_MODULES - _package_chain(package)
            for imported in outside:
                with self.subTest(package=package, imported=imported):
                    self.assertTrue(_payable_import(package, imported))

    def test_no_module_reaches_the_workflow_layer(self) -> None:
        for module in _observability_modules():
            for imported in _imported_orchestrator_modules(module):
                with self.subTest(module=module, imported=imported):
                    self.assertFalse(
                        imported.startswith(_FORBIDDEN_PREFIXES),
                        f"{module} inverts the dependency via {imported}",
                    )


class PackageSurfaceTest(unittest.TestCase):
    """An initializer owns only what it declares, and installs no resolver."""

    def test_declared_packages_are_the_ones_on_disk(self) -> None:
        self.assertEqual(_observability_packages(), tuple(sorted(_PACKAGES)))

    def test_initializer_binds_only_declared_names(self) -> None:
        # Undeclared, the only thing allowed here is a submodule of this
        # package: the one an import planted under its own name, or the
        # private alias a publishing initializer re-exports one through.
        # Anything else has to be named in `__all__`, which is what marks it a
        # deliberate surface an importer of one owner pays for the rest of.
        for package in _PACKAGES:
            with self.subTest(package=package):
                self.assertEqual(_undeclared_bindings(package), ())

    def test_only_publishers_declare_a_surface(self) -> None:
        # `__all__` is what makes the exemption above visible, so the packages
        # carrying one are exactly the packages the layering check excuses.
        declaring = frozenset(
            package for package in _PACKAGES
            if hasattr(import_module(package), "__all__")
        )
        self.assertEqual(declaring, _PUBLISHING_PACKAGES)

    def test_a_published_name_is_its_owner_s(self) -> None:
        # A re-export binds the owner's own object at import rather than
        # wrapping or rebuilding it, so the module a published name reports is
        # the module that defines it -- which is where a reader looks for the
        # source and where an interception has to be aimed. That module is the
        # package's own or one of the siblings it composes: the record
        # envelope both sinks satisfy is owned above either of them.
        for package in _PUBLISHING_PACKAGES:
            initializer = import_module(package)
            for name in initializer.__all__:
                published = getattr(initializer, name)
                owner = import_module(published.__module__)
                with self.subTest(package=package, name=name):
                    self.assertTrue(_payable_import(package, owner.__name__))
                    self.assertIs(published, getattr(owner, name))

    def test_initializer_installs_no_resolver_hook(self) -> None:
        # Read the namespace rather than `dir()`: a lazy facade installs both
        # hooks together, and the `__dir__` half is free to answer with an
        # inventory that never mentions the `__getattr__` beside it.
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
