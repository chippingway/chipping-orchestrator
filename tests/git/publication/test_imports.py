# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import checks and owner boundaries for the publication package."""

from __future__ import annotations

import subprocess
import sys
import unittest
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path
from types import MappingProxyType

from orchestrator.git import publication as _publication_package

_PACKAGE = "orchestrator.git.publication"

_OWNERS = (
    "models", "planning", "pr_references", "probes", "resume", "rewrite",
    "squash", "standing", "titles",
)

_MODULES = (_PACKAGE, *(f"{_PACKAGE}.{owner}" for owner in _OWNERS))

# Bound at module scope, so collecting this file is what plants every owner in
# `sys.modules` rather than whichever publication test happened to run first.
_OWNER_MODULES = MappingProxyType({
    owner: import_module(f"{_PACKAGE}.{owner}") for owner in _OWNERS
})

# The divergence probe, named once because it recurs across the owner surface
# below.
_DIVERGENCE = "_branch_divergence"

# What each owner defines: the whole publication surface, split by the module a
# patch aimed at one of these names has to land on.
_DEFINED = MappingProxyType({
    "planning": (
        "_SquashPlan",
        "_SquashPreparationError",
        "_prepare_squash",
        "_squash_base_sha",
        "_squash_commit_count",
        "_squash_message",
        "_squash_subjects",
    ),
    "models": ("_SquashOutcome",),
    "pr_references": ("_subject_with_pr_reference",),
    "probes": (
        "_BranchDivergence",
        _DIVERGENCE,
        "_fork_point",
    ),
    "rewrite": (
        "_UNCONFIRMED_PUBLICATION",
        "_create_squash_commit",
        "_gated_rewrite",
        "_published_squash",
        "_rewrite_squash",
        "_rollback_squash",
        "_squash_commit_env",
        "_squash_failure",
        "log",
    ),
    "resume": (
        "_ABSENT_END",
        "_MISCOUNTED_HISTORY",
        "_UNEQUAL_COLLAPSE",
        "_UNPROVABLE_TREE",
        "_UNREADABLE_COLLAPSE",
        "_VANISHED_COLLAPSE",
        "_UNBURIED_COLLAPSE",
        "_UNCOLLAPSED_BRANCH",
        "_UNCOLLAPSED_PARENTS",
        "_UNREADABLE_SHAPE",
        "_UNRELATED_PAIR",
        "_finished_collapse",
        "_is_ancestor",
        "_outstanding_collapse",
        "_resumed_squash",
        "_unaccountable_branch",
        "_unprovable_claim",
        "_unrecovered_collapse",
    ),
    "squash": (
        "_DIRTIED_UNDER_THE_RECORD",
        "_HEAD",
        "_MOVED_UNDER_THE_READING",
        "_MOVED_UNDER_THE_RECORD",
        "_RACED_THE_RECORD",
        "_UNRECORDED_COLLAPSE",
        "_handed_back",
        "_moved_under_the_reading",
        "_raced_the_record",
        "_rewrites_the_branch",
        "_squash_and_force_push",
        "_squashed_or_resumed",
        "_still_the_planned_checkout",
    ),
    "standing": (
        "_claims_a_collapse",
        "_tells_the_caller_where_the_branch_is",
        "_where_the_branch_stands",
    ),
    "titles": (
        "_CONVENTIONAL_RE",
        "_CONVENTIONAL_TYPES",
        "_CONVENTIONAL_TYPES_ALT",
        "_PREFIXED_RE",
        "_PREFIX_TOKEN_RE",
        "_first_commit_subject",
        "_infer_subject_prefix",
        "_is_conventional_subject",
        "_is_prefixed_subject",
        "_pr_title_from_commit_or_issue",
        "_recent_base_subjects",
        "_subject_prefix",
    ),
})

# The functions and classes among those, which carry the module that defines
# them; the rest are the subject vocabulary, the compiled patterns, and the
# logger, none of which report one.
_DEFINED_CALLABLES = MappingProxyType({
    owner: tuple(
        name for name in names
        if callable(getattr(_OWNER_MODULES[owner], name))
    )
    for owner, names in _DEFINED.items()
})

# The owner each name is defined on, which the initializer and every sibling
# owe an `AttributeError` for.
_OWNER_OF = MappingProxyType({
    name: owner for owner, names in _DEFINED.items() for name in names
})

# Each name paired with a sibling owner that must not answer for it.
_FOREIGN_LOOKUPS = tuple(
    (sibling, name)
    for name, owner in _OWNER_OF.items()
    for sibling in _OWNERS
    if sibling != owner
)

# Every flat spelling a publication helper could be reached through beside the
# package.
_FLAT_MODULE_PATTERNS = ("branch_publication.py", "_branch_publication_*.py")

# The module paths a second aggregate over the git domains would take: the
# spelling itself, and the inventory and resolver hooks one would be built
# from.
_ABSENT_MODULES = (
    "orchestrator._worktrees_export_manifest",
    "orchestrator._worktrees_exports",
    "orchestrator.worktrees",
)

# The channel operators filter a squash on. It is a name rather than a module
# path, so no module answers at the spelling it reads like.
_LOGGER_NAME = "orchestrator.branch_publication"

_LOGGER_OWNER = "rewrite"


def _defined_here(owner: str) -> tuple:
    """The functions and classes the owner's own module defines."""
    module = _OWNER_MODULES[owner]
    return tuple(sorted(
        name for name, member in module.__dict__.items()
        if getattr(member, "__module__", None) == f"{_PACKAGE}.{owner}"
    ))


class CleanProcessImportTest(unittest.TestCase):
    """Each owner imports standalone in a fresh interpreter.

    `pr_references` depends on nothing, `probes` and `titles` each only on the
    config and git command owners, `planning` on `titles` and `pr_references`
    plus the verification probes, and
    `rewrite` / `resume` / `standing` / `squash` layer on top, so importing any
    one of them first must not need a name a half-run module has not defined
    yet. A subprocess per module gives each a clean `sys.modules` no other test
    has already populated, exposing an import-order cycle a package-first suite
    run would mask.
    """

    def test_each_module_imports_standalone(self) -> None:
        for module in _MODULES:
            with self.subTest(module=module):
                completed = subprocess.run(
                    [sys.executable, "-c", f"import {module}"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0, msg=completed.stderr)


class PackageSurfaceTest(unittest.TestCase):
    """The initializer carries no bindings of its own."""

    def test_initializer_exposes_no_owner_names(self) -> None:
        for owner_only_name in _OWNER_OF:
            with self.subTest(name=owner_only_name), self.assertRaises(AttributeError):
                getattr(_publication_package, owner_only_name)


class OwnerBoundaryTest(unittest.TestCase):
    """No facade of this domain's own, and no sibling, answers for a name.

    Each name answers on the owner that defines it, so what this class holds to
    is that nothing in the package's own layer, and no aggregate above it,
    becomes a second site the same name resolves at.
    """

    def test_no_flat_module_sits_beside_the_package(self) -> None:
        # A module at the flat spelling would be a second import site for the
        # names these owners define -- and one a patch aimed at an owner would
        # not intercept.
        package_root = Path(import_module("orchestrator").__file__).parent
        for pattern in _FLAT_MODULE_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertEqual(list(package_root.glob(pattern)), [])

    def test_no_second_aggregate_sits_above(self) -> None:
        # An aggregate over the git domains would answer for a superset of the
        # slice below with the owners' own objects, so identity alone would
        # never show the extra surface a mock has to be aimed at. Resolving the
        # spec rather than stat-ing one path catches a copy planted anywhere
        # the interpreter would find it.
        for module in _ABSENT_MODULES:
            with self.subTest(module=module):
                self.assertIsNone(find_spec(module))

    def test_no_sibling_answers_for_a_foreign_name(self) -> None:
        # The owners reach each other by module rather than by name, so a
        # sibling never becomes a second binding site for a helper it only
        # calls.
        for sibling, name in _FOREIGN_LOOKUPS:
            with self.subTest(sibling=sibling, name=name):
                self.assertFalse(hasattr(_OWNER_MODULES[sibling], name))

    def test_defined_names_report_their_owner(self) -> None:
        # A helper lifted off a sibling would resolve here just as well, so the
        # defining module is what separates an owner from an importer of one --
        # and comparing both ways keeps the inventory above complete, so a
        # helper added to an owner is an edit here rather than a silent gap.
        for owner, names in _DEFINED_CALLABLES.items():
            with self.subTest(owner=owner):
                self.assertEqual(_defined_here(owner), tuple(sorted(names)))


class LoggerChannelTest(unittest.TestCase):
    """The squash reports on the domain's channel, not on a module path."""

    def test_logger_keeps_its_operator_facing_name(self) -> None:
        # Operators filter and attach handlers on this prefix, so it is a
        # published name that outranks the module layout beneath it.
        self.assertEqual(_OWNER_MODULES[_LOGGER_OWNER].log.name, _LOGGER_NAME)


if __name__ == "__main__":
    unittest.main()
