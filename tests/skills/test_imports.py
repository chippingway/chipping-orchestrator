# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, layering, and call-site checks for the skill owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from orchestrator import skills as _package
from tests.support.import_probes import probe_import

_PACKAGE = "orchestrator.skills"

_CATALOG_OWNER = "catalog"

_DISCOVERY_OWNER = "discovery"

# The declared inventory. A new owner is a deliberate edit here and a paragraph
# in the module map, which is what the inventory check compares the directory
# against.
_OWNERS = (_CATALOG_OWNER, _DISCOVERY_OWNER)

# Bound at module scope, so collecting this file is what plants both owners in
# `sys.modules` rather than whichever scenario test happened to run first.
_OWNER_MODULES = MappingProxyType({
    owner: import_module(f"{_PACKAGE}.{owner}") for owner in _OWNERS
})

_EMIT_CATALOG = "_emit_repo_skill_catalog"

# What a caller reaches each owner for: the per-tick catalog producer, the two
# per-run codex collectors, and the name/level pair type the provenance-carrying
# scan hands back. `__module__` is what holds them here, so the offered-tools
# baseline `discover_codex_tools` answers with -- a plain tuple carrying no
# stamp -- is pinned by `tests/skills/test_discovery.py` instead.
_OWNED_CALLABLES = MappingProxyType({
    _CATALOG_OWNER: (_EMIT_CATALOG,),
    _DISCOVERY_OWNER: (
        "SkillSource",
        "discover_codex_tools",
        "discover_local_skill_sources",
    ),
})

# The one pass that drives the catalog owner, and the only workflow module that
# names it.
_TICK = "orchestrator.workflow.engine.tick"

# A catalog is observation the tick drives, never state a handler consults, so
# no owner may read the workflow engine, a stage, the polling runtime, or an
# application entrypoint back.
_FORBIDDEN_PREFIXES = (
    "orchestrator.__main__",
    "orchestrator.cli",
    "orchestrator.runtime",
    "orchestrator.workflow",
)

# What `import orchestrator` alone plants, so the cost checks can hold a module
# to its own chain and nothing besides.
_ROOT_PACKAGE_MODULES = frozenset((
    "orchestrator",
))

_RESOLVER_HOOKS = ("__dir__", "__getattr__")

# Every flat spelling a scan could still be reached through beside the package.
_FLAT_MODULE_PATTERNS = ("_local_skills*.py", "skill_catalog*.py")

_PROBE_PATH = Path("/tmp/orchestrator-skills-owner-probe")

# A codex exit context with a worktree, which together with both skill sinks
# switched on is what makes the writer reach for discovery at all.
_CODEX_CONTEXT = SimpleNamespace(cwd=_PROBE_PATH)


class CleanProcessImportTest(unittest.TestCase):
    """The package and each owner import alone.

    A recording per module gives each one a `sys.modules` no earlier import
    has populated, which is the only place a cycle shows up at all: the
    analytics package `catalog` writes through reaches back into this one for
    a codex run's offered skills, and a suite that has already imported half
    the tree resolves the other half off what the first half left behind. It
    is the same recording the layering checks below read their planted sets
    off, so asking both questions costs one interpreter per module.
    """

    def test_each_module_imports_standalone(self) -> None:
        owners = (module.__name__ for module in _OWNER_MODULES.values())
        for module_name in (_PACKAGE, *owners):
            with self.subTest(module=module_name):
                probe = probe_import(module_name)
                self.assertEqual(probe.returncode, 0, msg=probe.stderr)


class LayeringTest(unittest.TestCase):
    """The package points away from the workflow and costs nothing eagerly."""

    def test_package_import_costs_only_its_own_chain(self) -> None:
        # A marker initializer binds nothing, so the analytics writer reaching
        # for `discovery` is not charged for the sink and the git execution
        # `catalog` is built on.
        self.assertEqual(
            probe_import(_PACKAGE).orchestrator_modules,
            _ROOT_PACKAGE_MODULES | {_PACKAGE},
        )

    def test_no_owner_reaches_the_workflow_layer(self) -> None:
        for owner, module in _OWNER_MODULES.items():
            planted = probe_import(module.__name__).orchestrator_modules
            for imported in planted:
                with self.subTest(owner=owner, imported=imported):
                    self.assertFalse(
                        imported.startswith(_FORBIDDEN_PREFIXES),
                        f"{owner} inverts the dependency via {imported}",
                    )

    def test_discovery_reaches_no_sibling(self) -> None:
        # The roots and the `SKILL.md` marker are defined on `discovery` rather
        # than `catalog` precisely so the direction can run this way: a codex
        # run's filesystem scan pays for nothing but the standard library.
        owner = _OWNER_MODULES[_DISCOVERY_OWNER].__name__
        self.assertEqual(
            probe_import(owner).orchestrator_modules,
            _ROOT_PACKAGE_MODULES | {_PACKAGE, owner},
        )


class PackageSurfaceTest(unittest.TestCase):
    """The initializer is a marker over exactly the owners on disk."""

    def test_declared_owners_are_the_ones_on_disk(self) -> None:
        directory = Path(_package.__file__).parent
        found = tuple(sorted(
            module_path.stem
            for module_path in directory.glob("*.py")
            if module_path.stem != "__init__"
        ))
        self.assertEqual(found, tuple(sorted(_OWNERS)))

    def test_initializer_binds_only_submodules(self) -> None:
        for owner, module in _OWNER_MODULES.items():
            with self.subTest(owner=owner):
                self.assertIs(getattr(_package, owner), module)
        for name, bound in _package.__dict__.items():
            if name.startswith("__"):
                continue
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(bound, "__name__", None), f"{_PACKAGE}.{name}",
                )

    def test_no_surface_or_resolver_declared(self) -> None:
        # Callers name an owner, so there is nothing here to publish and no
        # lazy inventory to rebuild -- a hook or an `__all__` would make this
        # initializer a second site the same names answer at.
        self.assertNotIn("__all__", _package.__dict__)
        for hook in _RESOLVER_HOOKS:
            with self.subTest(hook=hook):
                self.assertNotIn(hook, _package.__dict__)

    def test_no_flat_module_is_left_behind(self) -> None:
        # Every scan resolves off an owner here, so a flat module beside the
        # package would be a second import site for names this one defines --
        # and one a patch aimed at an owner would not intercept.
        package_root = Path(import_module("orchestrator").__file__).parent
        for pattern in _FLAT_MODULE_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertEqual(list(package_root.glob(pattern)), [])


class OwnerSurfaceTest(unittest.TestCase):
    """Each owner defines the names its callers reach it for."""

    def test_owners_define_what_callers_reach_for(self) -> None:
        # A name re-exported from elsewhere would leave a patch aimed here
        # intercepting a copy while the definition kept answering.
        for owner, owned in _OWNED_CALLABLES.items():
            module = _OWNER_MODULES[owner]
            for name in owned:
                with self.subTest(owner=owner, name=name):
                    self.assertEqual(
                        getattr(module, name).__module__, module.__name__,
                    )


class CallSiteTest(unittest.TestCase):
    """Both live producers resolve through the owner they drive."""

    def test_the_tick_names_the_catalog_owner(self) -> None:
        # The per-tick pass is reached on the module that defines it, so that
        # is where a test intercepting it has to patch -- and the tick pays for
        # that owner at import.
        self.assertIn(
            _OWNER_MODULES[_CATALOG_OWNER].__name__,
            probe_import(_TICK).orchestrator_modules,
        )

    def test_codex_backfill_reads_the_owner(self) -> None:
        # Patching the owner is what intercepts a codex run's offered skills
        # and tools, which holds only while the writer names it -- and the one
        # scan it reaches for is what both catalog projections are read off.
        from orchestrator.observability.analytics import (
            settings as analytics_settings,
        )
        from orchestrator.observability.analytics.recording import (
            catalog as recording_catalog,
            models as recording_models,
        )

        owner = _OWNER_MODULES[_DISCOVERY_OWNER]
        scanned = (owner.SkillSource("scanned", "user"),)
        catalog = recording_models.CodexCatalog()
        with patch.object(
            owner, "discover_local_skill_sources", lambda _cwd: scanned,
        ), patch.object(
            owner, "discover_codex_tools", lambda: ("offered",),
        ), patch.object(
            analytics_settings, "TRACK_SKILL_TRIGGERS", True,
        ), patch.object(
            analytics_settings, "TRAJECTORY_LOG_PATH", _PROBE_PATH,
        ):
            recording_catalog.populate_codex_catalog(_CODEX_CONTEXT, catalog)
        self.assertEqual(catalog.available_skills, ["scanned"])
        self.assertEqual(catalog.skill_levels, {"scanned": "user"})
        self.assertEqual(catalog.tools, ["offered"])


if __name__ == "__main__":
    unittest.main()
