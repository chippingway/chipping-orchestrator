# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Distribution identity and its directly imported version metadata."""
from __future__ import annotations

import subprocess
import sys
import tomllib
import unittest
from importlib import import_module
from pathlib import Path

from orchestrator.version import VERSION as imported_version

_ORCHESTRATOR_PACKAGE = import_module("orchestrator")
_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROJECT_NAME = "chipping-orchestrator"


class DistributionMetadataTest(unittest.TestCase):
    """The manifest names this distribution and shares the package version."""

    def test_manifest_identity(self) -> None:
        manifest = tomllib.loads(
            (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"),
        )["project"]

        self.assertEqual(manifest["name"], _PROJECT_NAME)
        self.assertEqual(manifest["version"], imported_version)


class PackageMetadataTest(unittest.TestCase):
    """The package is a marker and version metadata imports no runtime owners."""

    def test_root_package_declares_no_version_surface(self) -> None:
        self.assertNotIn("__version__", _ORCHESTRATOR_PACKAGE.__dict__)
        self.assertNotIn("__all__", _ORCHESTRATOR_PACKAGE.__dict__)

    def test_version_import_loads_no_subsystem(self) -> None:
        command = (
            "import sys; from orchestrator.version import VERSION; "
            "print(VERSION); "
            "print(' '.join(sorted(name for name in sys.modules "
            "if name.startswith('orchestrator'))))"
        )
        completed = subprocess.run(
            [sys.executable, "-c", command],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            completed.stdout.splitlines(),
            [imported_version, "orchestrator orchestrator.version"],
        )


if __name__ == "__main__":
    unittest.main()
