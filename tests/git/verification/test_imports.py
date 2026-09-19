# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import, layering, and package-surface checks for verification."""

from __future__ import annotations

import unittest
from importlib.util import find_spec

from orchestrator.git import verification
from tests.support.import_probes import probe_import

_MODULES = (
    "orchestrator.git.verification",
    "orchestrator.git.verification.models",
    "orchestrator.git.verification.output",
    "orchestrator.git.verification.probes",
    "orchestrator.git.verification.status",
    "orchestrator.git.verification.process",
    "orchestrator.git.verification.runner",
)

# The module paths a second import site for these owners would take: the flat
# spelling itself, and the inventory and resolver hooks one would be built from.
_FLAT_MODULES = (
    "orchestrator._verify_export_manifest",
    "orchestrator._verify_exports",
    "orchestrator.verify",
)

# Verification owns result classification for a worktree, so it may reach the
# git command owner and the settings it reads. Anything above that -- the
# workflow engine, its stage handlers, or an application entrypoint -- would
# invert the dependency and let a `git status` probe drag the tick loop into
# its import graph.
_ALLOWED_ROOTS = ("orchestrator.config", "orchestrator.git")

_ALLOWED_MODULES = ("orchestrator",)

_RESULT_OWNERS = (
    "orchestrator.git.verification.models",
    "orchestrator.git.verification.output",
    "orchestrator.git.verification.probes",
    "orchestrator.git.verification.status",
)

_SUBPROCESS_OWNERS = (
    "orchestrator.git.verification.process",
    "orchestrator.git.verification.runner",
)

# The process and runner owners additionally borrow the agent package's
# process-group operations, its registry, and its credential filter, which drag
# the agent models' usage parser in with them, so an allowlist would not
# describe their graph. What they still owe is the direction of the dependency,
# checked as a prefix so every owner under the workflow and base-sync packages
# is covered too. Base sync is the sharpest of those: its snapshot and
# publication owners call these very probes, so one read back the other way
# would close the loop.
_FORBIDDEN_PREFIXES = (
    "orchestrator.cli",
    "orchestrator.git.base_sync",
    "orchestrator.runtime",
    "orchestrator.workflow",
)

# The initializer binds nothing, so each name stays reachable only through the
# owner that defines it.
_OWNER_ONLY_NAMES = (
    "VerifyCommandOutcome",
    "VerifyResult",
    "_VERIFY_OUTPUT_BUDGET",
    "_head_sha",
    "_run_verify_commands",
    "_tree_sha",
    "_truncate_verify_output",
    "_worktree_dirty_files",
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
    """Each verification module imports standalone in a fresh interpreter.

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

    def test_result_owners_stay_in_the_git_domain(self) -> None:
        for module in _RESULT_OWNERS:
            with self.subTest(module=module):
                for imported in _imported_orchestrator_modules(module):
                    self.assertTrue(
                        self._within_allowed_layers(imported),
                        f"{module} reaches above the git domain via {imported}",
                    )

    def test_subprocess_owners_stay_below_workflow(self) -> None:
        for module in _SUBPROCESS_OWNERS:
            with self.subTest(module=module):
                for imported in _imported_orchestrator_modules(module):
                    self.assertFalse(
                        imported.startswith(_FORBIDDEN_PREFIXES),
                        f"{module} inverts the dependency via {imported}",
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
                getattr(verification, owner_only_name)


class OwnerImportSiteTest(unittest.TestCase):
    """No module of this domain's own sits beside the owners."""

    def test_no_flat_module_exists(self) -> None:
        # Anything importable at these paths would be a second identity for the
        # `VerifyResult` statuses the validating gate branches on and the output
        # budget the park comment it publishes is sized to -- free to drift from
        # the owner silently and invisible to a patch aimed at it. Resolving the
        # spec rather than stat-ing one path catches a copy planted anywhere the
        # interpreter would find it.
        for module in _FLAT_MODULES:
            with self.subTest(module=module):
                self.assertIsNone(find_spec(module))


if __name__ == "__main__":
    unittest.main()
