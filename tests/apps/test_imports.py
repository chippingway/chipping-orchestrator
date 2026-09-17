# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, clean-process import, and cost checks for the entrypoints."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path

from tests.support.import_probes import probe_import

_ORCHESTRATOR = "orchestrator"

_PACKAGE = f"{_ORCHESTRATOR}.apps"

_BOOTSTRAP = f"{_PACKAGE}.bootstrap"

_ANALYTICS_APP = f"{_PACKAGE}.analytics_dashboard"

_TRAJECTORY_APP = f"{_PACKAGE}.trajectory_dashboard"

_APPS = (_ANALYTICS_APP, _TRAJECTORY_APP)

# The declared inventory. A new app is a deliberate edit here and a paragraph
# in the package's own map, which is what the inventory check compares the
# directory against.
_MODULES = (_BOOTSTRAP, *_APPS)

# What `import orchestrator` alone plants, so the cost check can hold each app
# to its own chain and nothing besides.
_ROOT_MODULES = (_ORCHESTRATOR,)

# The optional dependency group no launch path may cost at import: it is what
# the function-local imports inside the page's passes exist for.
_DASHBOARD_GROUP = ("pandas", "plotly", "streamlit")


class AppInventoryTest(unittest.TestCase):
    """The declared apps are the ones on disk, and none is published above."""

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
        # An app is started by name, so nothing is re-exported above it: a
        # binding here would put one page's whole composition behind an import
        # of the package, which is what the entry function defers.
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
    """Each launch path imports alone in a fresh interpreter.

    A page is reached by name under `streamlit run` rather than through an
    importing caller, so nothing else is loaded when its shim runs: the
    interpreter recorded here is the one the launch itself gives it.
    """

    def test_each_app_imports_standalone(self) -> None:
        for app in _APPS:
            with self.subTest(app=app):
                probe = probe_import(app)
                self.assertEqual(probe.returncode, 0, msg=probe.stderr)


class AppImportCostTest(unittest.TestCase):
    """Naming a launch path costs the shim, never the page behind it."""

    def test_each_app_plants_only_its_own_chain(self) -> None:
        # Every owner a page composes is imported inside the pass that reaches
        # it, because under a script launch the repo root only reaches
        # `sys.path` on the line above them. Holding the cost to the shim is
        # what keeps that ordering from being undone by a tidy-looking hoist.
        for app in _APPS:
            with self.subTest(app=app):
                self.assertEqual(
                    tuple(sorted(probe_import(app).orchestrator_modules)),
                    tuple(sorted((*_ROOT_MODULES, _PACKAGE, _BOOTSTRAP, app))),
                )

    def test_no_path_costs_the_dashboard_group(self) -> None:
        # The whole recorded set rather than the chain above: what a hoisted
        # import would cost an operator who installed the optional group is a
        # third-party root, and that is where it shows up.
        for app in _APPS:
            planted = probe_import(app).modules
            for dependency in _DASHBOARD_GROUP:
                with self.subTest(app=app, dependency=dependency):
                    self.assertNotIn(dependency, planted)


if __name__ == "__main__":
    unittest.main()
