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
_RECORDER_OWNERS = MappingProxyType({
    "append_record": _EVENTS_OWNER,
    "build_record": None,
    "record_agent_exit": _AGENT_EXIT_OWNER,
    "record_repo_skill_catalog": _EVENTS_OWNER,
    "record_stage_enter": _EVENTS_OWNER,
    "record_stage_evaluation": _EVENTS_OWNER,
})

_RECORDERS = tuple(sorted(_RECORDER_OWNERS))

_SINK = "orchestrator.observability.analytics.sink"

# Every module that appends an analytics record, paired with nothing else it
# needs: the client's paired audit / analytics stage-enter hook, the dispatch
# that times one handler, the tracked agent run, and the per-tick skill
# catalog. Each is checked to reach the owner that defines the recorder it
# calls, so the write path has one place a record is built.
_PRODUCERS = (
    ("orchestrator.github.client", _EVENTS_OWNER),
    ("orchestrator.workflow.engine.dispatch", _EVENTS_OWNER),
    ("orchestrator.workflow.engine.usage", _AGENT_EXIT_OWNER),
    ("orchestrator.skills.catalog", _EVENTS_OWNER),
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
    """Recorders belong to their defining owners, and the package is a marker."""

    def test_package_exposes_no_recorder_aliases(self) -> None:
        self.assertNotIn("__all__", _package.__dict__)
        for name in _RECORDERS:
            with self.subTest(name=name):
                self.assertNotIn(name, _package.__dict__)

    def test_recorders_report_their_defining_module(self) -> None:
        for name, owner in _RECORDER_OWNERS.items():
            defining_module = _SINK if owner is None else _qualified(owner)
            binding_owner = _EVENTS_OWNER if owner is None else owner
            with self.subTest(name=name):
                self.assertEqual(getattr(_OWNER_MODULES[binding_owner], name).__module__, defining_module)

    def test_events_republishes_the_envelope(self) -> None:
        self.assertIs(_OWNER_MODULES[_EVENTS_OWNER].build_record, import_module(_SINK).build_record)

    def test_no_owner_declares_a_surface_of_its_own(self) -> None:
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
        for producer, owner in _PRODUCERS:
            planted = _imported_orchestrator_modules(producer)
            with self.subTest(producer=producer):
                self.assertIn(_qualified(owner), planted)


if __name__ == "__main__":
    unittest.main()
