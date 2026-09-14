# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Every package is a marker that binds no settings, metadata, or owner API.

A submodule imported elsewhere appears on its parent package automatically.
Reading initializer source distinguishes that binding from an eager import
that charges every caller for owners it never requested.
"""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.repository.binding_test_support import module_level_names
from tests.repository.layout_test_support import (
    PACKAGE_ROOT,
    dotted_name,
    package_directories,
)

# A marker initializer that loads a sibling for everyone who names the package.
# The name it binds is the sibling's own, which is what makes the eager import
# invisible in the namespace and visible only here, in the source.
_EAGER_MARKER = '''
"""A package marker that imports one of its owners."""
from orchestrator.git import commands
'''


def _packages() -> frozenset[str]:
    """Every package in the production tree, by dotted name."""
    return frozenset(
        dotted_name(directory / "__init__.py", PACKAGE_ROOT)
        for directory in package_directories(PACKAGE_ROOT)
    )


def _initializer_path(package: str) -> Path:
    """Where the package's initializer sits on disk."""
    return PACKAGE_ROOT.joinpath(*package.split(".")[1:], "__init__.py")


class MarkerInventoryTest(unittest.TestCase):
    """No initializer declares a package API."""

    def test_no_package_declares_an_export_list(self) -> None:
        declaring = frozenset(
            package for package in _packages()
            if hasattr(import_module(package), "__all__")
        )
        self.assertEqual(declaring, frozenset())


class NarrowSurfaceTest(unittest.TestCase):
    """Importing a package leaves every owner on its defining module."""

    def test_a_marker_initializer_binds_nothing(self) -> None:
        # Read the initializer's own statements, because the namespace cannot
        # answer this: importing `git.commands` from anywhere at all plants
        # `commands` on `orchestrator.git`, so a sibling the initializer
        # imported itself and one someone else's import left behind look
        # identical from the outside. What the source says is the difference,
        # and it is the whole difference -- an eager import here loads that
        # sibling for every caller who names the package.
        for package in _packages():
            with self.subTest(package=package):
                self.assertEqual(
                    module_level_names(_initializer_path(package)),
                    frozenset(),
                )

    def test_an_eager_import_is_a_binding(self) -> None:
        # What the check above rejects, spelled out: importing a sibling is a
        # binding even where the name it lands under is the sibling's own.
        with TemporaryDirectory() as directory:
            initializer = Path(directory) / "__init__.py"
            initializer.write_text(_EAGER_MARKER, encoding="utf-8")
            bound = module_level_names(initializer)
        self.assertEqual(bound, frozenset(("commands",)))

    def test_a_marker_namespace_holds_only_submodules(self) -> None:
        # The other side of it: whatever an import elsewhere plants here is a
        # submodule of this package under its own name. Anything else would be
        # a re-export, making the initializer a second identity for an owner.
        for package in _packages():
            initializer = import_module(package)
            for name, bound in initializer.__dict__.items():
                if name.startswith("__"):
                    continue
                with self.subTest(package=package, name=name):
                    self.assertEqual(
                        getattr(bound, "__name__", ""), f"{package}.{name}",
                    )


if __name__ == "__main__":
    unittest.main()
