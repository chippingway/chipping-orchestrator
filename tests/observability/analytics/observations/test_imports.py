# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, surface, and layering checks for the observation owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability.analytics import observations as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
    _under,
)

_PACKAGE = "orchestrator.observability.analytics.observations"

_CONFIG = "orchestrator.observability.analytics.config"

_SINK = "orchestrator.observability.analytics.sink"

_RECORDER = "recorder"

# The declared inventory. A new owner is a deliberate edit here and a
# paragraph in the module map, which is what the inventory check compares the
# directory against.
_OWNERS = ("attachments", "bounds", "records", _RECORDER, "redaction")

# What an import of any owner here costs before it names anything: the root
# package and the chain down to this one.
_ALWAYS_PLANTED = frozenset((
    "orchestrator",
    "orchestrator.observability",
    "orchestrator.observability.analytics",
))

# What each owner may reach beyond its own siblings. The reader, the bounds,
# and the redaction are leaves; the payloads build on the shared envelope; the
# recorder adds the configuration owner the sink knob is read through. The
# credential redactor and the policy it masks by are reached inside the call
# that redacts, so no import plants them, and the agent identity is a type
# alone: an owner here importing the agents package would charge every
# producer for the runner behind it.
_REACHABLE = MappingProxyType({
    "attachments": (),
    "bounds": (),
    "records": (_SINK,),
    _RECORDER: (_CONFIG, _SINK),
    "redaction": (),
})


def _qualified(owner: str) -> str:
    return f"{_PACKAGE}.{owner}"


def _reaches_beyond(owner: str) -> tuple[str, ...]:
    """Modules one owner plants that are neither siblings nor declared."""
    allowed = (_PACKAGE,) + _REACHABLE[owner]
    return tuple(sorted(
        imported
        for imported in _imported_orchestrator_modules(_qualified(owner)) - _ALWAYS_PLANTED
        if not _under(imported, allowed)
    ))


class OwnerInventoryTest(unittest.TestCase):
    """The declared owners are the ones on disk, and none publishes above itself."""

    def test_declared_owners_are_the_ones_on_disk(self) -> None:
        directory = Path(_package.__file__).parent
        found = tuple(sorted(
            module_path.stem
            for module_path in directory.glob("*.py")
            if module_path.stem != "__init__"
        ))
        self.assertEqual(found, tuple(sorted(_OWNERS)))

    def test_no_surface_is_declared_twice(self) -> None:
        self.assertNotIn("__all__", _package.__dict__)
        for owner in _OWNERS:
            with self.subTest(owner=owner):
                self.assertNotIn("__all__", import_module(_qualified(owner)).__dict__)


class LayeringTest(unittest.TestCase):
    """The owners reach only what they compose."""

    def test_no_owner_reaches_past_what_it_composes(self) -> None:
        for owner in _OWNERS:
            with self.subTest(owner=owner):
                self.assertEqual(_reaches_beyond(owner), ())


if __name__ == "__main__":
    unittest.main()
