# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Inventory, layering, and public-surface checks for the usage owners."""
from __future__ import annotations

import unittest
from importlib import import_module
from pathlib import Path
from types import MappingProxyType

from orchestrator.observability import usage as _package
from tests.observability.observability_test_support import (
    _imported_orchestrator_modules,
)

_PACKAGE = "orchestrator.observability.usage"

# The owner every agent result and the per-issue meter is typed by.
_METRICS_OWNER = "metrics"

# The declared inventory. A new owner is a deliberate edit here and a
# paragraph in the module map, which is what the inventory check compares the
# directory against.
_OWNERS = (
    "claude_rows",
    "claude_summary",
    "codex_rows",
    "codex_summary",
    "event_stream",
    _METRICS_OWNER,
    "model_names",
    "prices",
    "protocol",
    "shell_segments",
    "skill_commands",
    "skills",
    "skills_claude",
    "skills_codex",
    "trajectory",
    "trajectory_claude_blocks",
    "trajectory_claude_stream",
    "trajectory_claude_turns",
    "trajectory_codex",
    "trajectory_codex_items",
    "trajectory_codex_payloads",
    "trajectory_models",
)

# Bound at module scope, so collecting this file is what plants every owner in
# `sys.modules` rather than whichever parser test happened to run first.
_OWNER_MODULES = MappingProxyType({
    owner: import_module(f"{_PACKAGE}.{owner}") for owner in _OWNERS
})

# What the package publishes, grouped by the owner each name is defined on.
_PUBLISHED = MappingProxyType({
    _METRICS_OWNER: (
        "UsageMetrics",
        "parse_agent_usage",
        "parse_claude_usage",
        "parse_codex_usage",
    ),
    "skills": (
        "SkillTriggers",
        "parse_agent_skills",
        "parse_claude_skills",
        "parse_codex_skills",
    ),
    "trajectory": (
        "parse_agent_trajectory",
        "parse_claude_trajectory",
        "parse_codex_trajectory",
    ),
})

# Four of the six result types are defined off an entry point, on the module
# the trajectory parsers build them from; the other two sit beside the parser
# that fills each and are grouped with it above.
_RECORD_OWNER = "trajectory_models"

_RECORDS = ("AgentTrajectory", "SourceItem", "TrajectoryStep", "TurnUsage")

# Every module that meters a finished run, paired with the owner it has to
# have imported to do so: the agent result `UsageMetrics` types, the tracked
# run that folds the counters, and the two analytics writers -- the token /
# cost record on one side and the opt-in trajectory record on the other.
_CALLERS = (
    ("orchestrator.agents.models", _METRICS_OWNER),
    ("orchestrator.workflow.engine.usage", _METRICS_OWNER),
    ("orchestrator.observability.analytics.recording.usage", _METRICS_OWNER),
    ("orchestrator.observability.analytics.recording.skills", "skills"),
    ("orchestrator.observability.analytics.trajectories.persistence", "trajectory"),
    ("orchestrator.observability.analytics.trajectories.serialize", _RECORD_OWNER),
)

# Every flat spelling a parser could still be reached through beside the
# package.
_FLAT_MODULE_PATTERNS = ("_usage_*.py", "usage*.py")


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

    def test_no_flat_module_is_left_behind(self) -> None:
        # Every parser resolves off an owner here, so a flat module beside the
        # package would be a second import site for names this one defines --
        # and one a patch aimed at an owner would not intercept.
        package_root = Path(import_module("orchestrator").__file__).parent
        for pattern in _FLAT_MODULE_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertEqual(list(package_root.glob(pattern)), [])


class PublicSurfaceTest(unittest.TestCase):
    """The package publishes a narrow, accurate `__all__`."""

    def test_published_surface_is_the_declared_one(self) -> None:
        declared = set(_RECORDS)
        for published in _PUBLISHED.values():
            declared.update(published)
        self.assertEqual(set(_package.__all__), declared)
        self.assertEqual(_package.__all__, tuple(sorted(_package.__all__)))

    def test_published_names_are_the_owners_objects(self) -> None:
        # The package publishes the owner's own object rather than a wrapper
        # around it, so the module a name reports is the module that defines
        # it. The binding is made once, at import: it is the identity that is
        # shared, not a later rebinding, which is why a test intercepting a
        # parser patches the module its caller imported.
        for owner, published in _PUBLISHED.items():
            module = _OWNER_MODULES[owner]
            for name in published:
                with self.subTest(owner=owner, name=name):
                    self.assertIs(getattr(_package, name), getattr(module, name))
                    self.assertEqual(
                        getattr(module, name).__module__, _qualified(owner),
                    )

    def test_records_come_from_their_owner(self) -> None:
        # The trajectory records are published beside the parsers that return
        # them even though the module defining them is not an entry point.
        owner = _OWNER_MODULES[_RECORD_OWNER]
        for name in _RECORDS:
            with self.subTest(name=name):
                self.assertIs(getattr(_package, name), getattr(owner, name))

    def test_no_owner_declares_a_surface_of_its_own(self) -> None:
        # One `__all__` for the package, so a name cannot be published here
        # and forgotten there.
        for owner, module in _OWNER_MODULES.items():
            with self.subTest(owner=owner):
                self.assertNotIn("__all__", module.__dict__)

    def test_records_report_their_defining_module(self) -> None:
        # A relocated `__module__` would point a reader at a module whose
        # source does not define the record it names.
        owner = _OWNER_MODULES[_RECORD_OWNER]
        for name in _RECORDS:
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(owner, name).__module__, _qualified(_RECORD_OWNER),
                )


class LayeringTest(unittest.TestCase):
    """The owners reach nothing outside, and every caller names one."""

    def test_no_owner_reaches_outside_the_package(self) -> None:
        # A parser is fed a payload rather than an issue, so the dependency
        # runs one way: an owner reaching the workflow that meters a run, the
        # agent that produced the payload, or a module beside the package
        # would invert that and cycle back through its own caller.
        for owner in _OWNERS:
            planted = _imported_orchestrator_modules(_qualified(owner))
            for imported in planted:
                with self.subTest(owner=owner, imported=imported):
                    self.assertTrue(
                        imported.startswith(("orchestrator.observability", "orchestrator._package"))
                        or imported == "orchestrator",
                        f"{owner} reaches {imported}",
                    )

    def test_every_caller_names_its_owner(self) -> None:
        # Every module that meters a run pays for the owner it is typed by at
        # import, which is what makes patching that owner intercept the parse:
        # a caller reaching the package instead would bind a name the package
        # resolved once, and a patch on the owner would not reach it.
        for caller, owner in _CALLERS:
            with self.subTest(caller=caller):
                self.assertIn(
                    _qualified(owner), _imported_orchestrator_modules(caller),
                )


if __name__ == "__main__":
    unittest.main()
