# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, clean-process import, and surface checks for the service package."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path

from tests.support.import_probes import probe_import

_ORCHESTRATOR = "orchestrator"

_PACKAGE = f"{_ORCHESTRATOR}.service"

_TEMPLATES_OWNER = f"{_PACKAGE}.templates"

# The declared inventory: the one owner, and the two templates it reads as
# package data. A new file here is a deliberate edit and an entry in the module
# map, which is what the inventory check compares the directory against -- and
# a second copy of a template beside these would be one nothing reads.
_OWNER_FILES = ("templates.py",)

_PACKAGE_DATA = (".env.example", ".env.example.advanced")

# What a fresh import of each module may plant under the package: its own
# chain and nothing besides. `orchestrator.config` above all stays out, since
# importing it resolves the settings and an installed package with no `REPOS`
# exits there -- the state a first setup reads the templates from.
_IMPORT_CHAINS = (
    (_PACKAGE, frozenset((_ORCHESTRATOR, _PACKAGE))),
    (_TEMPLATES_OWNER, frozenset((_ORCHESTRATOR, _PACKAGE, _TEMPLATES_OWNER))),
)

_RESOLVER_HOOKS = ("__dir__", "__getattr__")


class ServiceInventoryTest(unittest.TestCase):
    """The declared owner and package data are the files on disk."""

    def test_declared_files_are_the_ones_on_disk(self) -> None:
        directory = Path(import_module(_PACKAGE).__file__).parent
        found = tuple(sorted(
            path.name
            for path in directory.iterdir()
            if path.is_file() and path.name != "__init__.py"
        ))
        self.assertEqual(found, tuple(sorted((*_OWNER_FILES, *_PACKAGE_DATA))))


class CleanProcessImportTest(unittest.TestCase):
    """Each module imports alone and loads no configuration.

    A fresh interpreter per module is the only place a stray import shows: a
    suite that has already imported the settings would resolve them off what
    that left behind, and the template read would look free when it is not.
    """

    def test_each_module_costs_only_its_own_chain(self) -> None:
        for module, chain in _IMPORT_CHAINS:
            with self.subTest(module=module):
                probe = probe_import(module)
                self.assertEqual(probe.returncode, 0, msg=probe.stderr)
                self.assertEqual(probe.orchestrator_modules, chain)


class PackageSurfaceTest(unittest.TestCase):
    """The initializer is a marker: callers name the owner they need."""

    def test_initializer_publishes_nothing(self) -> None:
        initializer = import_module(_PACKAGE)
        for declared in ("__all__", *_RESOLVER_HOOKS):
            with self.subTest(declared=declared):
                self.assertNotIn(declared, initializer.__dict__)
        for name, bound in initializer.__dict__.items():
            if name.startswith("__"):
                continue
            with self.subTest(name=name):
                self.assertEqual(getattr(bound, "__name__", ""), f"{_PACKAGE}.{name}")


if __name__ == "__main__":
    unittest.main()
