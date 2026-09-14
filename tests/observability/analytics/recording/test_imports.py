# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the recording owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability.analytics import recording as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
    _under,
)

_PACKAGE = "orchestrator.observability.analytics.recording"

# The owner the three directly-called recorders and the sink append are
# defined on, and the one that owns the sequenced fourth.
_EVENTS_OWNER = "events"

_AGENT_EXIT_OWNER = "agent_exit"

# The declared inventory. A new owner is a deliberate edit here and a
# paragraph in the module map, which is what the inventory check compares the
# directory against.
_OWNERS = (
    _AGENT_EXIT_OWNER,
    "catalog",
    _EVENTS_OWNER,
    "models",
    "skills",
    "usage",
)

# Bound at module scope, so collecting this file is what plants every owner in
# `sys.modules` rather than whichever recorder test happened to run first.
_OWNER_MODULES = MappingProxyType({
    owner: import_module(f"{_PACKAGE}.{owner}") for owner in _OWNERS
})

# What the package publishes, paired with the module that defines it. The
# envelope is the shared `sink` owner's, because a trajectory record satisfies
# it too; the append that resolves the analytics knob and the three recorders
# a producer calls directly are `events`; and the family with a sequence to
# run before it writes is `agent_exit`.
_PUBLISHED_OWNERS = MappingProxyType({
    "append_record": _EVENTS_OWNER,
    "build_record": None,
    "record_agent_exit": _AGENT_EXIT_OWNER,
    "record_repo_skill_catalog": _EVENTS_OWNER,
    "record_stage_enter": _EVENTS_OWNER,
    "record_stage_evaluation": _EVENTS_OWNER,
})

_PUBLISHED = tuple(sorted(_PUBLISHED_OWNERS))

_SINK = "orchestrator.observability.analytics.sink"

# Every module that appends an analytics record, paired with nothing else it
# needs: the client's paired audit / analytics stage-enter hook, the dispatch
# that times one handler, the tracked agent run, and the per-tick skill
# catalog. Each is checked to reach the owner that defines the recorder it
# calls, so the write path has one place a record is built.
_PRODUCERS = (
    "orchestrator.github.client",
    "orchestrator.workflow.engine.dispatch",
    "orchestrator.workflow.engine.usage",
    "orchestrator.skills.catalog",
)

# What an owner here is allowed to reach: its siblings, the configuration
# owner every knob is read through, the shared sink owner the envelope and the
# JSONL line come from, the parsers a finished run is metered by, and the
# trajectory writers an `agent_exit` hands that run's second record to. The
# query, sync, and page graphs are deliberately absent -- this is the one
# analytics path the orchestrator process itself runs.
_REACHABLE = (
    _PACKAGE,
    "orchestrator.observability.analytics.config",
    _SINK,
    "orchestrator.observability.analytics.trajectories",
    "orchestrator.observability.usage",
    "orchestrator.observability",
    "orchestrator._package",
    "orchestrator",
)


def _qualified(owner: str) -> str:
    return f"{_PACKAGE}.{owner}"


class OwnerInventoryTest(unittest.TestCase):
    """The declared owners are the ones on disk."""

    def test_declared_owners_are_the_ones_on_disk(self) -> None:
        directory = Path(_package.__file__).parent
        found = tuple(sorted(
            module_path.stem
            for module_path in directory.glob("*.py")
            if module_path.stem != "__init__"
        ))
        self.assertEqual(found, tuple(sorted(_OWNERS)))


class PublicSurfaceTest(unittest.TestCase):
    """The package publishes a narrow, accurate `__all__`."""

    def test_published_surface_is_the_declared_one(self) -> None:
        # Declared rather than discovered, so a new public name here is a
        # deliberate edit: this package is what a producer reaches to append a
        # record, and an accidental export is a second way to write one.
        self.assertEqual(_package.__all__, _PUBLISHED)
        self.assertEqual(_package.__all__, tuple(sorted(_package.__all__)))

    def test_published_names_are_the_owner_s_objects(self) -> None:
        # The package publishes the owner's own object rather than a wrapper
        # around it, so the module a name reports is the module that defines
        # it -- which is where a reader looks for the source.
        for name, owner in _PUBLISHED_OWNERS.items():
            defining_module = _SINK if owner is None else _qualified(owner)
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(_package, name).__module__, defining_module,
                )

    def test_events_republishes_the_envelope(self) -> None:
        # `build_record` is reached on `events` as well as on the package: it
        # is the import site a producer already names, and the two spellings
        # have to be the one shared object a trajectory record is built with.
        self.assertIs(
            _OWNER_MODULES[_EVENTS_OWNER].build_record, _package.build_record,
        )

    def test_no_owner_declares_a_surface_of_its_own(self) -> None:
        # One `__all__` for the package, so a name cannot be published here
        # and forgotten there.
        for owner, module in _OWNER_MODULES.items():
            with self.subTest(owner=owner):
                self.assertNotIn("__all__", module.__dict__)


class LayeringTest(unittest.TestCase):
    """The owners reach only what they compose, and every producer names them."""

    def test_no_owner_reaches_past_what_it_composes(self) -> None:
        # The sharpest case this rejects is `orchestrator.config`: the knobs
        # are read off the `settings` holder inside the call, so a producer
        # that imports a recorder pays for the process configuration when it
        # writes a record rather than when it imports.
        for owner in _OWNERS:
            planted = _imported_orchestrator_modules(_qualified(owner))
            for imported in planted:
                with self.subTest(owner=owner, imported=imported):
                    self.assertTrue(
                        _under(imported, _REACHABLE),
                        f"{owner} reaches {imported}",
                    )

    def test_every_producer_names_the_owner(self) -> None:
        for producer in _PRODUCERS:
            planted = _imported_orchestrator_modules(producer)
            with self.subTest(producer=producer):
                self.assertIn(_PACKAGE, planted)


if __name__ == "__main__":
    unittest.main()
