# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the analytics owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability import analytics as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
    _under,
)
from tests.support.import_probes import CONFIGURATION_READS

_PACKAGE = "orchestrator.observability.analytics"

_CONFIG_OWNER = "config"

_ENVIRONMENT_OWNER = "environment"

_RETENTION_OWNER = "retention"

_RETENTION_REWRITE_OWNER = "retention_rewrite"

_RETENTION_SCAN_OWNER = "retention_scan"

_SETTINGS_OWNER = "settings"

_SINK_OWNER = "sink"

# The declared inventory. A new owner is a deliberate edit here and a
# paragraph in the module map, which is what the inventory check compares the
# directory against.
_OWNERS = (
    _CONFIG_OWNER,
    _ENVIRONMENT_OWNER,
    _RETENTION_OWNER,
    _RETENTION_REWRITE_OWNER,
    _RETENTION_SCAN_OWNER,
    _SETTINGS_OWNER,
    _SINK_OWNER,
)

# The names the settings owner binds, which are the whole surface it answers
# for -- it declares values rather than callables, so they are compared
# against its annotations instead of the defined-here sweep below.
_KNOBS = (
    "ANALYTICS_DB_URL",
    "ANALYTICS_LOG_PATH",
    "ANALYTICS_RETENTION_DAYS",
    "TRACK_SKILL_TRIGGERS",
    "TRAJECTORY_LOG_PATH",
    "TRAJECTORY_RETENTION_DAYS",
)

# What each owner answers for, declared rather than discovered so a new public
# name is a deliberate edit: these are what a caller reaches for a setting or a
# prune, and an accidental export is a second answer to the same question.
# Configuration is the view every adapter reads a knob back through, the two
# ways it is entered, and the read-path URL fallback; `environment` under it is
# the parse of the six knobs and nothing else, and `settings` beside them binds
# nothing but what that parse returned. Retention is the three entry points one
# caller each reaches -- the per-tick wrapper and the two sinks' by-age prunes
# -- over a scan that decides what is expired and a rewrite that swaps the file
# out from under it. The `sink` owner is what both write packages share: the
# record envelope and the JSONL line under it.
_SURFACES = MappingProxyType({
    _CONFIG_OWNER: (
        "Settings",
        "live_settings",
        "resolve_db_url",
        "settings_on",
    ),
    _ENVIRONMENT_OWNER: (
        "parse_db_url",
        "parse_log_path",
        "parse_retention_days",
        "parse_track_skill_triggers",
        "parse_trajectory_log_path",
        "parse_trajectory_retention_days",
    ),
    _RETENTION_OWNER: (
        "prune_old_records",
        "prune_trajectory_records",
        "prune_with_retention_logging",
    ),
    _RETENTION_REWRITE_OWNER: (
        "atomic_rewrite",
        "flush_fd_and_replace",
        "prune_jsonl_records",
        "rewrite_pruned_file",
        "unlink_quietly",
    ),
    _RETENTION_SCAN_OWNER: (
        "PruneScan",
        "normalized_jsonl_line",
        "probe_exists",
        "prune_timestamp",
        "read_kept_records",
    ),
    _SETTINGS_OWNER: (),
    _SINK_OWNER: (
        "append_jsonl_record",
        "build_record",
    ),
})

# The flat tree whose responsibility the observability owners took over, whole.
# A survivor of it would be a second place a knob could be parsed from, a sink
# pruned by, a read issued through, or a replay started from.
_VACATED_TREE = "orchestrator/analytics"

# Every adapter that has to read a knob back through the owner: the append
# paths of both sinks and the prune both are bounded by, the two skill readers,
# the gate the opt-in trajectory write runs behind, the two read-path owners
# that resolve a query's URL, and the sync request that falls back to both sink
# knobs. The holder they read off is not among them -- it obtains the values by
# parsing rather than by reading one back, so it names the `environment` owner.
_CONFIG_ADAPTERS = (
    "orchestrator.observability.analytics.recording.events",
    "orchestrator.observability.analytics.recording.catalog",
    "orchestrator.observability.analytics.recording.skills",
    "orchestrator.observability.analytics.retention",
    "orchestrator.observability.analytics.trajectories.api",
    "orchestrator.observability.analytics.trajectories.persistence",
    "orchestrator.observability.analytics.query.connection_cache",
    "orchestrator.observability.analytics.query.execution",
    "orchestrator.observability.analytics.sync.run",
)

# The one adapter of the parse, which is what makes a knob's spelling answer
# the same way for every reader downstream of the holder.
_ENVIRONMENT_ADAPTERS = ("orchestrator.observability.analytics.settings",)

# The one owner allowed outside the observability tree, and what it reaches:
# the default analytics sink lives under `config.LOG_DIR`, so the module that
# binds the knobs is where that dependency is paid -- the parse defers the
# import to the call, so it is planted by this holder's import and by no
# other. `live_settings` names the holder inside the call in turn, so no
# producer pays for it at import.
_OUTSIDE_REACH = MappingProxyType({_SETTINGS_OWNER: ("orchestrator.config",)})


def _reachable(imported: str, allowed: tuple[str, ...]) -> bool:
    """Whether an owner allowed `allowed` outside the tree may plant `imported`.

    The settings come with what they read: the service's install facts,
    named exactly.
    """
    if _under(imported, allowed):
        return True
    return "orchestrator.config" in allowed and imported in CONFIGURATION_READS


def _qualified(owner: str) -> str:
    return f"{_PACKAGE}.{owner}"


def _defined_here(owner: str) -> tuple[str, ...]:
    """Public names the owner defines, as opposed to ones it imported."""
    module = import_module(_qualified(owner))
    return tuple(sorted(
        name
        for name, member in module.__dict__.items()
        if not name.startswith("_")
        and getattr(member, "__module__", None) == module.__name__
    ))


class OwnerInventoryTest(unittest.TestCase):
    """The declared owners are the ones on disk, and nothing is left behind."""

    def test_declared_owners_are_the_ones_on_disk(self) -> None:
        directory = Path(_package.__file__).parent
        found = tuple(sorted(
            module_path.stem
            for module_path in directory.glob("*.py")
            if module_path.stem != "__init__"
        ))
        self.assertEqual(found, tuple(sorted(_OWNERS)))

    def test_the_vacated_tree_is_gone(self) -> None:
        repository_root = Path(import_module("orchestrator").__file__).parents[1]
        self.assertFalse(repository_root.joinpath(_VACATED_TREE).exists())


class PublicSurfaceTest(unittest.TestCase):
    """Each owner answers for a narrow, declared surface."""

    def test_public_names_are_the_declared_ones(self) -> None:
        for owner, surface in _SURFACES.items():
            with self.subTest(owner=owner):
                self.assertEqual(_defined_here(owner), surface)

    def test_the_settings_owner_binds_every_knob(self) -> None:
        # It declares values rather than callables, so what it answers for is
        # the annotated set: a seventh knob parsed but left unbound, or one
        # bound here and nowhere read, would show up as a difference.
        holder = import_module(_qualified(_SETTINGS_OWNER))
        self.assertEqual(tuple(sorted(holder.__annotations__)), _KNOBS)

    def test_no_surface_is_declared_twice(self) -> None:
        # The package initializer is a marker, so a name is reached on the
        # owner that defines it rather than published a second time above it.
        self.assertNotIn("__all__", _package.__dict__)
        for owner in _OWNERS:
            with self.subTest(owner=owner):
                self.assertNotIn(
                    "__all__", import_module(_qualified(owner)).__dict__,
                )


class LayeringTest(unittest.TestCase):
    """The owners reach nothing outside, and every adapter names them."""

    def test_no_owner_reaches_outside_the_package(self) -> None:
        for owner in _OWNERS:
            allowed = _OUTSIDE_REACH.get(owner, ())
            planted = _imported_orchestrator_modules(_qualified(owner))
            for imported in planted:
                with self.subTest(owner=owner, imported=imported):
                    self.assertTrue(
                        imported.startswith(("orchestrator.observability", "orchestrator._package"))
                        or imported == "orchestrator"
                        or _reachable(imported, allowed),
                        f"{owner} reaches {imported}",
                    )

    def test_every_adapter_names_the_config_owner(self) -> None:
        # Configuration has one source, so an adapter that parses a knob or
        # re-reads the environment itself would be a second one.
        for adapter in _CONFIG_ADAPTERS:
            with self.subTest(adapter=adapter):
                self.assertIn(
                    _qualified(_CONFIG_OWNER),
                    _imported_orchestrator_modules(adapter),
                )

    def test_the_holder_names_the_environment_owner(self) -> None:
        # The parse is reached only to bind the knobs: a reader that wants a
        # value asks the holder for it rather than parsing a second time.
        for adapter in _ENVIRONMENT_ADAPTERS:
            with self.subTest(adapter=adapter):
                self.assertIn(
                    _qualified(_ENVIRONMENT_OWNER),
                    _imported_orchestrator_modules(adapter),
                )


if __name__ == "__main__":
    unittest.main()
