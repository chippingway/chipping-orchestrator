# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The shape of the production tree: what the root holds, and what it may not.

Every owner answers on the module under a domain package that defines it, so
the root is metadata plus the two launch forms and nothing else, and no leaf
anywhere in the tree stands in for one -- no domain-prefixed module, no export
manifest, no resolver hook, no stub beside a module that already carries its
own annotations. Each of those is a second site a name could answer on, free to
drift from the owner and invisible to a patch aimed at it.

The directories are read as the modules under them see them rather than as the
initializers declare them: a directory holding a module without an
`__init__.py` is still importable as a namespace package, so a declared
inventory compared against the declared packages alone would never see one.
"""
from __future__ import annotations

import unittest

from tests.repository.binding_test_support import module_level_names
from tests.repository.layout_test_support import (
    PACKAGE_ROOT,
    TESTS_ROOT,
    module_directories,
    package_directories,
    python_files,
)

# What sits directly under the package root. The version metadata, the console
# script's composition point, and the module launch form over it -- three files
# a launch names, none of them an owner.
_ROOT_LEAVES = ("__init__.py", "__main__.py", "cli.py")

# The domain packages beneath it. A new one is a deliberate edit here and a
# paragraph in the module map, which is what this inventory is compared against.
_ROOT_PACKAGES = (
    "agents",
    "apps",
    "config",
    "git",
    "github",
    "observability",
    "runtime",
    "scheduler",
    "skills",
    "workflow",
)

# The domain families the flattened tree spelled into module names, forbidden
# as a prefix anywhere under the package. Every family is listed in the private
# spelling its compatibility leaves carried. The ones listed in the public
# spelling too are the words that name a domain package and nothing else, so a
# module wearing one is that domain flattened out of the package owning it. A
# word that also names a responsibility *inside* a package -- `agent_`,
# `skill_`, `trajectory_`, `usage_` -- stays private-only here, because the
# public spelling is how an owner under the family's own package is named.
_FLAT_PREFIXES = (
    "_agent_",
    "_analytics_",
    "_base_",
    "_branch_",
    "_compat_",
    "_config_",
    "_dashboard_",
    "_git_",
    "_github_",
    "_main_",
    "_package_",
    "_repo_",
    "_runtime_",
    "_scheduler_",
    "_skill_",
    "_state_",
    "_static_",
    "_trajectory_",
    "_usage_",
    "_verify_",
    "_workflow_",
    "_worktree_",
    "_worktrees_",
    "base_sync_",
    "branch_publication_",
    "dashboard_",
    "git_",
    "github_",
    "scheduler_",
    "state_machine",
    "workflow_",
    "worktree_",
    "worktrees_",
)

# One retired spelling per family above, as the flat tree spelled it. The list
# is deliberately not derived from the prefixes: a family dropped from the rule
# leaves its case behind here, and the case is then what fails.
_RETIRED_LEAVES = (
    "_agent_api",
    "_analytics_records",
    "_base_sync_recovery",
    "_branch_publication_state",
    "_compat_exports",
    "_config_diagnostics",
    "_dashboard_read_core",
    "_git_auth",
    "_github_internals",
    "_main_loop",
    "_package_exports",
    "_repo_context",
    "_runtime_ticks",
    "_scheduler_service",
    "_skill_catalog_scan",
    "_state_machine_labels",
    "_static_assets",
    "_trajectory_records",
    "_usage_parser",
    "_verify_runner",
    "_workflow_state",
    "_worktree_paths",
    "_worktrees_recovery",
    "base_sync_recovery",
    "branch_publication_state",
    "dashboard_reads",
    "git_plumbing",
    "github_client",
    "scheduler_service",
    "state_machine",
    "workflow_drift",
    "worktree_lifecycle",
    "worktrees_recovery",
)

# Names the rule must not reach: the one private leaf in the tree, a private
# leaf named for a responsibility of two words, and the public spellings a
# family word keeps inside the package that owns it.
_KEPT_LEAVES = (
    "_dotenv",
    "_rate_limit",
    "agent_exit",
    "query_rows",
    "skill_adoption",
    "trajectory_models",
    "usage_axis",
)

# What a leaf rebuilding the surface a package publishes is called: an
# inventory of names, the resolver read off it, or the shim between them. A
# re-export is the owner's own object bound at import, so none of the three has
# anything left to describe. Each is matched as a whole module name as well as
# the tail of a prefixed one, because a package-local `exports.py` is the same
# module the flat tree spelled `_dashboard_exports.py`.
_COMPATIBILITY_LEAVES = ("compatibility", "exports", "manifest")

# The one module named for a manifest that is not an inventory of names: the
# decomposer's output manifest, the JSON an agent emits and the stage parses.
# Exempted as a path rather than as a word, so the name stays forbidden
# everywhere else in the tree.
_MANIFEST_OWNER = PACKAGE_ROOT.joinpath(
    "workflow", "stages", "decomposition", "manifest.py",
)

# The stub such a resolver needs to stay legible to a type checker; a module
# that carries its own annotations has nothing for one to add.
_STUB_GLOB = "*.pyi"

_RESOLVER_HOOKS = frozenset(("__dir__", "__getattr__"))

# One retired spelling per leaf name, in both the flat tree's prefixed form and
# the package-local form the same thing takes inside a package.
_RETIRED_SURFACES = (
    "_base_sync_export_manifest",
    "_dashboard_compatibility",
    "_dashboard_exports",
    "compatibility",
    "exports",
    "manifest",
)


def _is_flattened(stem: str) -> bool:
    """Whether a module name wears one of the retired domain prefixes."""
    return stem.startswith(_FLAT_PREFIXES)


def _rebuilds_a_surface(stem: str) -> bool:
    """Whether a module name is one an export inventory answers on."""
    return any(
        stem == leaf or stem.endswith(f"_{leaf}")
        for leaf in _COMPATIBILITY_LEAVES
    )


class PackageRootTest(unittest.TestCase):
    """The root is the declared three leaves and the declared ten packages.

    Holding it to an exact inventory is what forbids a flat spelling of an
    owner: a module parked here would be importable beside the package that
    owns the responsibility, and both would answer.
    """

    def test_root_holds_the_declared_leaves(self) -> None:
        found = tuple(sorted(
            leaf.name for leaf in PACKAGE_ROOT.iterdir() if leaf.is_file()
        ))
        self.assertEqual(found, tuple(sorted(_ROOT_LEAVES)))

    def test_root_holds_the_declared_packages(self) -> None:
        # Read the directories that hold a module rather than the ones that
        # declare a package: an undeclared directory with no `__init__.py` is
        # still importable, and is how a domain would reappear at the root
        # without being named here.
        found = tuple(sorted(
            directory.name
            for directory in module_directories(PACKAGE_ROOT)
            if directory.parent == PACKAGE_ROOT
        ))
        self.assertEqual(found, tuple(sorted(_ROOT_PACKAGES)))


class FlattenedLeafTest(unittest.TestCase):
    """No module carries a domain prefix in front of its responsibility."""

    def test_no_module_wears_a_flattened_prefix(self) -> None:
        # `<domain>_<responsibility>.py` is the shape a flattened tree takes:
        # the package a module belongs to spelled into its own name, because
        # there was no package to put it in. The check runs over the whole tree
        # rather than the root alone, so a family re-flattened one level down --
        # a `dashboard_reads.py` under `observability/` -- fails here too.
        for module in python_files(PACKAGE_ROOT):
            stem = module.stem
            with self.subTest(module=stem):
                self.assertFalse(
                    _is_flattened(stem),
                    f"{stem} spells its domain into its own name",
                )

    def test_every_retired_spelling_is_rejected(self) -> None:
        for stem in _RETIRED_LEAVES:
            with self.subTest(stem=stem):
                self.assertTrue(_is_flattened(stem))

    def test_every_family_carries_a_case(self) -> None:
        # The other direction: a family added to the rule without a retired
        # spelling behind it is a prefix nothing ever exercises.
        covered = frozenset(
            prefix
            for prefix in _FLAT_PREFIXES
            for stem in _RETIRED_LEAVES
            if stem.startswith(prefix)
        )
        self.assertEqual(covered, frozenset(_FLAT_PREFIXES))

    def test_a_responsibility_name_is_kept(self) -> None:
        # The rule reaches domain prefixes and stops there: a private leaf may
        # still be named for a responsibility of two words, and a family word
        # is how an owner under that family's own package is named.
        for stem in _KEPT_LEAVES:
            with self.subTest(stem=stem):
                self.assertFalse(_is_flattened(stem))


class CompatibilityLeafTest(unittest.TestCase):
    """Nothing in the tree resolves a name the owner already answers for."""

    def test_no_inventory_leaf_in_the_tree(self) -> None:
        for module in python_files(PACKAGE_ROOT):
            if module == _MANIFEST_OWNER:
                continue
            with self.subTest(module=module.stem):
                self.assertFalse(_rebuilds_a_surface(module.stem))

    def test_the_exempt_manifest_is_the_decomposer_s(self) -> None:
        # The exemption is one file. If the decomposer's manifest moves, this
        # fails rather than quietly excusing whatever sits at that path.
        self.assertTrue(_MANIFEST_OWNER.is_file())

    def test_every_retired_surface_is_rejected(self) -> None:
        # The bare spellings are the point: `exports.py` inside a package is
        # the same inventory the flat tree parked beside it as
        # `_dashboard_exports.py`, and a glob keyed on the prefix would let the
        # nested one through.
        for stem in _RETIRED_SURFACES:
            with self.subTest(stem=stem):
                self.assertTrue(_rebuilds_a_surface(stem))

    def test_no_stub_sits_beside_a_module(self) -> None:
        self.assertEqual(list(PACKAGE_ROOT.rglob(_STUB_GLOB)), [])

    def test_no_module_installs_a_resolver_hook(self) -> None:
        # Read what the module binds rather than what `dir()` reports: a lazy
        # surface installs both hooks together, and the `__dir__` half is free
        # to answer with an inventory that never mentions the `__getattr__`
        # beside it. Every binding form counts -- a `def`, an assignment
        # annotated or not, and an import renamed to the hook's name all
        # install the same surface. The pair is read at module level only: the
        # same names inside a class body are an attribute protocol, not a
        # resolver.
        for module in python_files(PACKAGE_ROOT):
            with self.subTest(module=module.stem):
                self.assertEqual(
                    module_level_names(module) & _RESOLVER_HOOKS, frozenset(),
                )


class PackageDirectoryTest(unittest.TestCase):
    """Every directory is a declared package, and every package has a mirror.

    Where a test lands is decided by which owner it covers, so a package with
    no mirror is a domain whose tests are somewhere else -- and the guards each
    tests package carries for its own layering and surface are then missing.
    """

    def test_every_module_directory_is_a_package(self) -> None:
        # A namespace directory imports and collects like a package while
        # carrying none of the surface an initializer declares, so the tree
        # holds none: every directory a module sits in or under has one.
        for directory in module_directories(PACKAGE_ROOT):
            with self.subTest(directory=directory.name):
                self.assertTrue((directory / "__init__.py").is_file())

    def test_every_package_has_a_test_mirror(self) -> None:
        for directory in package_directories(PACKAGE_ROOT):
            relative = directory.relative_to(PACKAGE_ROOT)
            with self.subTest(package=str(relative)):
                mirrored = TESTS_ROOT / relative / "__init__.py"
                self.assertTrue(mirrored.is_file())


if __name__ == "__main__":
    unittest.main()
