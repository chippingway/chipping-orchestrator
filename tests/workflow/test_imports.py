# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import checks and package surface for the workflow package."""

from __future__ import annotations

import importlib
import pkgutil
import subprocess
import sys
import unittest
from importlib.util import find_spec
from unittest.mock import patch

from orchestrator import workflow as _workflow
from orchestrator.workflow import state as _state, transition_guard as _transition_guard

_TICK = "tick"

_TICK_OWNER = f"orchestrator.workflow.engine.{_TICK}"

_ENGINE_OWNERS = (
    "terminal_reading",
    "terminal_context",
    "terminal_effects",
    "stage_targets",
    "poll_models",
    "run_limit_dispatch",
    "dispatch_guards",
    "poll_reading",
    "dispatch_closure",
    "cleanup_observation",
    "dispatch_partition",
    "issue_processing",
    "dispatch_workers",
    "scheduled_dispatch",

    "retry_values",
    "retry_park_state",
    "retry_ledger",
    "retry_notices",
    "run_limit_values",
    "run_limit_state",
    "observation_state",
    "observation_receipts",
    "retiring_cycles",
    "publication_holds",

    "prompt_context",
    "content_hash",
    "prompt_notes",
    "conversation_prompts",
    "decomposition_prompts",
    "run_requests",
    "run_reporting",
    "issue_usage",
    "run_budget_models",
    "run_budget_fields",
    "run_charge_state",
    "run_ledger_models",
    "run_ledger_values",

    "agent_diagnostics",
    "comments",
    "community",
    "completion_verdicts",
    "dispatch",
    "drift",
    "guards",
    "messages",
    "parallel",
    "pickup",
    "prompts",
    "report_checkout_evidence",
    "report_consumed_values",
    "report_evidence",
    "report_evidence_models",
    "report_fences",
    "report_outcome_models",
    "report_outcomes",
    "report_publication_evidence",
    "report_publishing",
    "report_record_fields",
    "report_record_reading",
    "report_record_state",
    "report_record_values",
    "report_records",
    "report_remote_evidence",
    "report_settlement_state",
    "report_transaction",
    "retry_budget",
    "run_budget",
    "run_circuit",
    "run_grant",
    "run_grant_request",
    "run_ledger",
    "run_limit",
    "terminals",
    _TICK,
    "usage",
)

# The late-split domain's owners. They sit beside the engine rather than under
# it: the state round trip reaches the GitHub pinned-state model and the
# telemetry reaches the analytics recorders, both of which import the `state`
# owner's vocabulary back, so each has to load on its own.
_LATE_SPLIT_OWNERS = (
    "exemption_reading",
    "ancestry",
    "rewrite_values",
    "rewrite_fields",
    "rewrite_reading",

    "phases",
    "obligations",
    "publication",
    "collapses",
    "encoding",
    "endings",
    "events",
    "exemption",
    "formats",
    "handoffs",
    "identity",
    "keys",
    "ledger_encoding",
    "ledgers",
    "models",
    "overrides",
    "payloads",
    "records",
    "restart",
    "rewrites",
    "spends",
    "state",
    "telemetry",
    "validation",
)

_MODULES = (
    "orchestrator.workflow",
    "orchestrator.workflow.engine",
    *(f"orchestrator.workflow.engine.{owner}" for owner in _ENGINE_OWNERS),
    "orchestrator.workflow.late_split",
    *(
        f"orchestrator.workflow.late_split.{owner}"
        for owner in _LATE_SPLIT_OWNERS
    ),
    "orchestrator.workflow.state",
    "orchestrator.workflow.label_reading",
    "orchestrator.workflow.transitions",
    "orchestrator.workflow.transition_guard",
)

# What importing the package must leave out of `sys.modules`: the dispatcher,
# the tick loop, the stage-handler tree, the git and GitHub subsystems those
# reach, the analytics recorders under them, and the config package behind those.
_DEFERRED_MODULES = (
    "orchestrator.config",
    "orchestrator.git",
    "orchestrator.github",
    "orchestrator.observability.analytics.recording",
    "orchestrator.workflow.engine",
    "orchestrator.workflow.engine.dispatch",
    _TICK_OWNER,
    "orchestrator.workflow.stages",
)

# The vocabulary, label readings, transition graph, and guard are read by the
# GitHub and git layers, so each must import without any engine or subsystem.
_LAZY_IMPORTS = (
    "orchestrator.workflow",
    "orchestrator.workflow.state",
    "orchestrator.workflow.label_reading",
    "orchestrator.workflow.transitions",
    "orchestrator.workflow.transition_guard",
)

_LAZINESS_PROBE = (
    "import sys;"
    "import {module};"
    "print(' '.join(name for name in {names!r} if name in sys.modules))"
)

# The paths a second import site for anything under this package would take: a
# flat spelling of the drift owner or of the comment, message, prompt, and
# decomposition manifest owners, the shared-value and dependency leaves the
# owners hold their own copies of, the inventory plus resolver a lazy surface
# over them would be rebuilt from, and the flat spelling of the `state` owner
# itself -- which would be a second identity for the transition graph and the
# write guard live issues already run on.
_FLAT_MODULES = (
    "orchestrator._workflow_dependencies",
    "orchestrator._workflow_export_manifest",
    "orchestrator._workflow_exports",
    "orchestrator._workflow_state",
    "orchestrator.state_machine",
    "orchestrator.workflow_drift",
    "orchestrator.workflow_messages",
)

# The vocabularies and transition guard retain one defining owner each.
_STATE_NAMES = ("ControlLabel", "WorkflowLabel")

_GUARD_NAMES = ("IllegalTransition", "guard_transition", "is_allowed_transition")

# The two operator-facing log channels this package reports on. Every engine and
# stage owner spells the first literally, and the transition guard the second.
_WORKFLOW_CHANNEL = "orchestrator.workflow"

_STATE_CHANNEL = "orchestrator.state_machine"


class CleanProcessImportTest(unittest.TestCase):
    """The package, its subpackage, and each owner beneath them import alone.

    The engine owners import the GitHub and git layers, which import the `state`
    owner beside them and so run this initializer back. A subprocess per module
    gives each a clean `sys.modules` no other test has already populated,
    exposing an import-order cycle a package-first suite run would mask.
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

    def test_import_reaches_no_engine_or_subsystem(self) -> None:
        # The package boundary is where an accidental eager binding is cheapest
        # to add and hardest to notice: an engine import in the initializer
        # would drag the stage tree or the analytics graph into every
        # `orchestrator.workflow` import -- and into the GitHub and git layers
        # that import the state owner beside it, which is the cycle those layers
        # would then fail to import through.
        for module in _LAZY_IMPORTS:
            with self.subTest(module=module):
                self._assert_nothing_resolved(module)

    def _assert_nothing_resolved(self, module: str) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                _LAZINESS_PROBE.format(
                    module=module, names=_DEFERRED_MODULES,
                ),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(completed.stdout.strip(), "")


class PublicSurfaceTest(unittest.TestCase):
    """The public labels, guards, and lazy tick retain their defining owners."""

    def test_names_belong_to_their_defining_modules(self) -> None:
        self.assertEqual(
            _workflow.__all__, tuple(sorted((*_STATE_NAMES, *_GUARD_NAMES, _TICK))),
        )
        for owner, names in ((_state, _STATE_NAMES), (_transition_guard, _GUARD_NAMES)):
            for name in names:
                with self.subTest(owner=owner.__name__, name=name):
                    self.assertIs(getattr(_workflow, name), getattr(owner, name))
                    self.assertEqual(getattr(owner, name).__module__, owner.__name__)

    def test_tick_drives_the_engine_owner(self) -> None:
        engine_tick = importlib.import_module(_TICK_OWNER)
        self.assertIsNot(_workflow.tick, engine_tick.tick)
        with patch.object(engine_tick, _TICK) as driven:
            _workflow.tick("gh", "spec", scheduler="scheduler")
            driven.assert_called_once_with(
                "gh", "spec", global_semaphore=None, scheduler="scheduler",
            )


class LoggerChannelTest(unittest.TestCase):
    """Every owner reports on the channel operators filter on.

    The name is spelled literally on each owner rather than derived from
    `__name__`, because it is what an operator's log filter and handler select
    on -- a module moved between packages must not move its own channel with it.
    """

    def test_every_owner_reports_on_its_channel(self) -> None:
        for module in self._modules_declaring_a_logger():
            with self.subTest(module=module.__name__):
                expected = (
                    _STATE_CHANNEL if module is _transition_guard else _WORKFLOW_CHANNEL
                )
                self.assertEqual(module.log.name, expected)

    def _modules_declaring_a_logger(self) -> list:
        found = [
            importlib.import_module(module.name)
            for module in pkgutil.walk_packages(
                _workflow.__path__, prefix=f"{_workflow.__name__}.",
            )
        ]
        return [module for module in found if hasattr(module, "log")]


class OwnerImportSiteTest(unittest.TestCase):
    """The engine owners are the only modules their surfaces answer on."""

    def test_no_flat_module_exists(self) -> None:
        # Anything importable at these paths would be a second identity for the
        # hash live issues are already parked on, the marker their comments are
        # stamped with, or the prompt text an agent is spawned with -- free to
        # drift from the owner silently and invisible to a patch aimed at it.
        # Resolving the spec rather than stat-ing one path catches a copy
        # planted anywhere the interpreter would find it.
        for module in _FLAT_MODULES:
            with self.subTest(module=module):
                self.assertIsNone(find_spec(module))


if __name__ == "__main__":
    unittest.main()
