# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the trajectory owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability.analytics import trajectories as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
    _under,
)

_PACKAGE = "orchestrator.observability.analytics.trajectories"

_CONFIG = "orchestrator.observability.analytics.config"

_SINK = "orchestrator.observability.analytics.sink"

_USAGE = "orchestrator.observability.usage"

_API_OWNER = "api"

_PERSISTENCE_OWNER = "persistence"

_LAUNCH_OWNER = "codex_launch"

# The declared inventory. A new owner is a deliberate edit here and a
# paragraph in the module map, which is what the inventory check compares the
# directory against.
_OWNERS = (
    _API_OWNER,
    _LAUNCH_OWNER,
    "codex_sessions",
    "models",
    _PERSISTENCE_OWNER,
    "requests",
    "sanitize",
    "serialize",
)

# What an import of any owner here costs before it names anything: the root
# package and the chain down to this one.
_ALWAYS_PLANTED = frozenset((
    "orchestrator",
    "orchestrator.observability",
    "orchestrator.observability.analytics",
))

# What each owner may reach beyond its own siblings, declared per owner
# because the direction is the point. The two leaves reach nothing; the
# request usage field names only the usage records it bounds, and the Codex
# session read only the collector it hands the log to; the serializer names
# the shared write owner for the record envelope and the parsers a run is
# metered by; the append, the write, and the launch observation add the
# configuration owner the knob is read through. The recording package is
# deliberately absent from all of them: an `agent_exit` composes this write,
# so a trajectory owner importing the recorders that call it is the cycle this
# rejects.
_REACHABLE = MappingProxyType({
    _API_OWNER: (_CONFIG, _SINK),
    _LAUNCH_OWNER: (_CONFIG, _SINK, _USAGE),
    "codex_sessions": (_USAGE,),
    "models": (),
    _PERSISTENCE_OWNER: (_CONFIG, _SINK, _USAGE),
    "requests": (_USAGE,),
    "sanitize": (),
    "serialize": (_SINK, _USAGE),
})

# Every caller that has to obtain a trajectory owner from this package: the
# `agent_exit` that hands one finished run's second record over, and the
# tracked spawn's exit reporting, which observes a Codex launch for it before
# the process starts. The by-age prune is deliberately absent -- it takes the
# sink lock off the `sink` owner that minted it, which is what keeps that
# object identical to the one the append here takes.
_CALLERS = MappingProxyType({
    "orchestrator.observability.analytics.recording.agent_exit": _PERSISTENCE_OWNER,
    "orchestrator.workflow.engine.run_reporting": _LAUNCH_OWNER,
})


def _qualified(owner: str) -> str:
    return f"{_PACKAGE}.{owner}"


def _reaches_beyond(owner: str) -> tuple[str, ...]:
    """Modules one owner plants that are neither siblings nor declared."""
    allowed = (_PACKAGE,) + _REACHABLE[owner]
    return tuple(sorted(
        imported
        for imported in _imported_orchestrator_modules(_qualified(owner))
        - _ALWAYS_PLANTED
        if not _under(imported, allowed)
    ))


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
    """Nothing is published above the owner that defines it."""

    def test_no_surface_is_declared_twice(self) -> None:
        # The initializer is a marker, so a name is reached on its owner
        # rather than re-exported here: the write path is entered by one
        # caller per owner, and a package surface would only add a second
        # spelling for each.
        self.assertNotIn("__all__", _package.__dict__)
        for owner in _OWNERS:
            with self.subTest(owner=owner):
                self.assertNotIn(
                    "__all__", import_module(_qualified(owner)).__dict__,
                )


class LayeringTest(unittest.TestCase):
    """The owners reach only what they compose, and every caller names them."""

    def test_no_owner_reaches_past_what_it_composes(self) -> None:
        for owner in _OWNERS:
            with self.subTest(owner=owner):
                self.assertEqual(_reaches_beyond(owner), ())

    def test_every_caller_names_the_owner(self) -> None:
        for caller, owner in _CALLERS.items():
            planted = _imported_orchestrator_modules(caller)
            with self.subTest(caller=caller):
                self.assertIn(_qualified(owner), planted)


if __name__ == "__main__":
    unittest.main()
