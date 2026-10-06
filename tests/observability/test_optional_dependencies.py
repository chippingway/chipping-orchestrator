# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The observability tree imports without the optional page dependencies."""
from __future__ import annotations

import subprocess
import unittest

from tests.observability.observability_test_support import (
    _observability_modules,
    _run_import_probe,
)

# Streamlit and Plotly live in the optional `dashboard` dependency group, so
# the default `poetry sync` install has neither. Blocking them outright
# is what keeps this honest for an operator who installed that group: a
# `sys.modules` scan would stay clean either way, while a module-scope import
# is refused here whether or not the package is on disk.
_OPTIONAL_ROOTS = ("plotly", "streamlit")

# The probe is the whole test, so these cases prove it fails an import that
# would otherwise succeed. A blocked optional root cannot show that -- it
# fails in the default install with the probe or without it.
_ALWAYS_IMPORTABLE_ROOTS = ("json",)

# A module that guards its import and swallows the `ImportError` still loads
# the dependency in the install that has it, which is why the probe records
# the attempt instead of leaving the exception to decide.
_SWALLOWED_IMPORT = """
try:
    import json
except ImportError:
    pass
"""

_HARNESS_PROBES = (
    ("raised", "import json"),
    ("swallowed", _SWALLOWED_IMPORT),
)

_BLOCKED_IMPORT_SCRIPT = """
import importlib.abc
import sys

_BLOCKED_ROOTS = {blocked}
_ATTEMPTED = []


class _BlockedFinder(importlib.abc.MetaPathFinder):

    def find_spec(self, fullname, path=None, target=None):
        if fullname.partition('.')[0] in _BLOCKED_ROOTS:
            _ATTEMPTED.append(fullname)
            raise ImportError(fullname)
        return None


sys.meta_path.insert(0, _BlockedFinder())
{importer}
if _ATTEMPTED:
    sys.exit('blocked import attempted: ' + ', '.join(_ATTEMPTED))
"""


class OptionalDependencyTest(unittest.TestCase):
    """No module reaches for Streamlit or Plotly on an ordinary import.

    A page imports them inside the function that renders with them, so the
    owners around that function stay importable -- and their data shaping
    stays testable -- in an install carrying neither. What the probe answers
    is whether the module asked for one at all: a module-scope import wrapped
    in `try: ... except ImportError` is a load in every install that has the
    package, so the attempt is the violation and the exception is beside the
    point.
    """

    def test_each_module_imports_with_both_blocked(self) -> None:
        for module in _observability_modules():
            with self.subTest(module=module):
                completed = self._import_blocking(
                    _OPTIONAL_ROOTS, f"import {module}",
                )
                self.assertEqual(
                    completed.returncode, 0, msg=completed.stderr,
                )

    def test_the_probe_fails_an_importable_module(self) -> None:
        for probe, importer in _HARNESS_PROBES:
            with self.subTest(probe=probe):
                completed = self._import_blocking(
                    _ALWAYS_IMPORTABLE_ROOTS, importer,
                )
                self.assertNotEqual(completed.returncode, 0)

    def _import_blocking(
        self, blocked: tuple[str, ...], importer: str,
    ) -> subprocess.CompletedProcess[str]:
        return _run_import_probe(_BLOCKED_IMPORT_SCRIPT.format(
            blocked=blocked, importer=importer,
        ))


if __name__ == "__main__":
    unittest.main()
