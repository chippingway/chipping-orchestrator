# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import, layering, and package-surface checks for measurement."""

from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.git import measurement
from tests.support.import_probes import probe_import

_MODULES = (
    "orchestrator.git.measurement",
    "orchestrator.git.measurement.additions",
    "orchestrator.git.measurement.commits",
    "orchestrator.git.measurement.fingerprint",
    "orchestrator.git.measurement.models",
)

# The module paths a second import site for these owners would take: the flat
# spelling itself, and the inventory and resolver hooks one would be built from.
_FLAT_MODULES = (
    "orchestrator._measurement_export_manifest",
    "orchestrator._measurement_exports",
    "orchestrator.measurement",
)

# This domain reads what a checkout carries, so it may reach the git command
# and transport owners and the settings they read. Anything above that -- the
# workflow engine, its stage handlers, or an application entrypoint -- would
# invert the dependency: the gate that spends a reading lives up there, and
# an import back down would put the decision inside the reading.
_ALLOWED_ROOTS = ("orchestrator.config", "orchestrator.git")

_ALLOWED_MODULES = ("orchestrator",)

# The initializer binds nothing, so each name stays reachable only through the
# owner that defines it -- which is where a test intercepting one has to patch.
_OWNER_ONLY_NAMES = (
    "AdditionMeasurement",
    "ContributionFingerprint",
    "FingerprintFailure",
    "FrozenCommit",
    "MeasurementFailure",
    "_count_added_lines",
    "_fingerprint_contribution",
    "_freeze_base_commit",
    "_measure_candidate",
    "_prove_candidate_commit",
)


def _imported_orchestrator_modules(module: str) -> list[str]:
    """Names of the orchestrator modules a fresh `import module` pulls in.

    A module that does not import at all is raised on rather than answered
    with an empty list, which every bound below would pass vacuously. Whether
    each module does import standalone is `CleanProcessImportTest`'s check,
    read off this same recording.
    """
    probe = probe_import(module)
    if probe.returncode != 0:
        raise AssertionError(f"{module} does not import: {probe.stderr}")
    return sorted(probe.orchestrator_modules)


class CleanProcessImportTest(unittest.TestCase):
    """Each measurement module imports standalone in a fresh interpreter.

    The owners bind their collaborators at import time, so importing any one of
    them first must not need a name a half-run module has not defined yet. A
    recording per module gives each a clean `sys.modules` no other test has
    already populated, exposing an import-order cycle a package-first suite run
    would mask. The layering checks below read their planted sets off that same
    recording, so the package is swept for one interpreter per module rather
    than one per question.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                probe = probe_import(module)
                self.assertEqual(probe.returncode, 0, msg=probe.stderr)


class LayeringTest(unittest.TestCase):
    """The owners import nothing from the workflow or application layers."""

    def test_the_owners_stay_in_the_git_domain(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                for imported in _imported_orchestrator_modules(module):
                    self.assertTrue(
                        self._within_allowed_layers(imported),
                        f"{module} reaches above the git domain via {imported}",
                    )

    def test_the_record_costs_no_transport(self) -> None:
        # The model owner is what a caller recording or reading back a
        # measurement imports, and it has to stay free of the authenticated
        # transport the freeze needs: charging a reader for an askpass session
        # is what makes a data type expensive enough to copy instead.
        self.assertNotIn(
            "orchestrator.git.branch_transport",
            _imported_orchestrator_modules(
                "orchestrator.git.measurement.models",
            ),
        )

    def _within_allowed_layers(self, imported: str) -> bool:
        if imported in _ALLOWED_MODULES:
            return True
        return any(
            imported == root or imported.startswith(f"{root}.")
            for root in _ALLOWED_ROOTS
        )


class PackageSurfaceTest(unittest.TestCase):
    """The package initializer carries no bindings of its own."""

    def test_initializer_exposes_no_owner_names(self) -> None:
        for owner_only_name in _OWNER_ONLY_NAMES:
            with self.subTest(name=owner_only_name), self.assertRaises(AttributeError):
                getattr(measurement, owner_only_name)


class OwnerImportSiteTest(unittest.TestCase):
    """No module of this domain's own sits beside the owners."""

    def test_no_flat_module_exists(self) -> None:
        # Anything importable at these paths would be a second identity for the
        # failure vocabulary a park reason is written from and the count a
        # verdict is taken on -- free to drift from the owner silently and
        # invisible to a patch aimed at it. Resolving the spec rather than
        # stat-ing one path catches a copy planted anywhere the interpreter
        # would find it.
        for module in _FLAT_MODULES:
            with self.subTest(module=module):
                self.assertIsNone(find_spec(module))


if __name__ == "__main__":
    unittest.main()
