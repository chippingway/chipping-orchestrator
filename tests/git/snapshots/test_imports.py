# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import, layering, and surface checks for the snapshot package."""

from __future__ import annotations

import unittest

from orchestrator.git import snapshots as _package
from orchestrator.git.snapshots import mirrors, namespace, refs
from tests.support.import_probes import probe_import

_PACKAGE = "orchestrator.git.snapshots"

_NAMESPACE_OWNER = f"{_PACKAGE}.namespace"

_MODULES = (
    _PACKAGE,
    f"{_PACKAGE}.mirrors",
    _NAMESPACE_OWNER,
    f"{_PACKAGE}.refs",
)

# The names each owner defines. The initializer binds nothing, so a caller
# reaches the owner it needs and a test intercepting one targets that owner.
_OWNER_DEFINED = (
    ("SNAPSHOT_NAMESPACE", namespace),
    ("InvalidSnapshotRef", namespace),
    ("is_snapshot_ref", namespace),
    ("snapshot_ref", namespace),
    ("local_snapshot_ref", mirrors),
    ("local_snapshot_present", mirrors),
    ("SnapshotOutcome", refs),
    ("create_snapshot_ref", refs),
    ("delete_snapshot_ref", refs),
    ("prove_snapshot_ref", refs),
)


class CleanProcessImportTest(unittest.TestCase):
    """Each module imports standalone in a fresh interpreter.

    The layering check below reads its planted set off the same recording, so
    the namespace owner answers both questions for one interpreter.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                probe = probe_import(module)
                self.assertEqual(probe.returncode, 0, msg=probe.stderr)


class LayeringTest(unittest.TestCase):
    """The namespace is string policy and costs nothing to consult.

    It is read by the late domain's own lineage owner, which is charged for it
    on every pinned read a child's ancestry goes through -- so importing it
    must not drag the authenticated transport in behind it.
    """

    def test_the_namespace_reaches_no_transport(self) -> None:
        # An owner that did not import at all plants nothing, and nothing
        # satisfies every bound below, so the recording is read for what it
        # reports before it is read for what it planted.
        probe = probe_import(_NAMESPACE_OWNER)
        self.assertEqual(probe.returncode, 0, msg=probe.stderr)
        planted = probe.orchestrator_modules

        self.assertNotIn("orchestrator.git.branch_transport", planted)
        self.assertNotIn("orchestrator.git.ref_transport", planted)
        self.assertNotIn("orchestrator.git.commands", planted)
        self.assertNotIn("orchestrator.config", planted)


class PackageSurfaceTest(unittest.TestCase):
    """The initializer is a marker; every name answers on its owner."""

    def test_initializer_binds_only_submodules(self) -> None:
        for name, bound in _package.__dict__.items():
            if name.startswith("__"):
                continue
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(bound, "__name__", None), f"{_PACKAGE}.{name}",
                )

    def test_each_name_answers_on_its_owner(self) -> None:
        for owner_name, owner in _OWNER_DEFINED:
            with self.subTest(name=owner_name):
                self.assertIn(owner_name, owner.__dict__)
                with self.assertRaises(AttributeError):
                    getattr(_package, owner_name)


if __name__ == "__main__":
    unittest.main()
