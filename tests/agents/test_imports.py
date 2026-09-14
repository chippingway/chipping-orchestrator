# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Clean-process import checks for the agents package and its leaves."""

from __future__ import annotations

import subprocess
import sys
import typing
import unittest

from orchestrator.agents import (
    models as _agent_models,
    processes as _agent_processes,
    provider_failures as _agent_provider_failures,
    runner as _agent_runner,
)
from orchestrator.agents.backends import claude as _agent_claude, codex as _agent_codex

_MODULES = (
    "orchestrator.agents",
    "orchestrator.agents.models",
    "orchestrator.agents.environment",
    "orchestrator.agents.session_ids",
    "orchestrator.agents.sessions",
    "orchestrator.agents.provider_failures",
    "orchestrator.agents.process_groups",
    "orchestrator.agents.processes",
    "orchestrator.agents.runner",
    "orchestrator.agents.backends",
    "orchestrator.agents.backends.codex",
    "orchestrator.agents.backends.claude",
)

# Agent-package functions annotated against the `models` owner -- the runner
# and provider-failure owners plus the Codex and Claude backends. Their hints
# must resolve at runtime, so the owner stays importable at module scope rather
# than only for static type checkers.
_OWNER_ANNOTATED_FUNCS = (
    _agent_codex.codex_command,
    _agent_codex.run_codex,
    _agent_claude.claude_command,
    _agent_claude.claude_process_last_message,
    _agent_claude.run_claude,
    _agent_runner.resolve_agent_run_options,
    _agent_runner.run_agent,
    _agent_runner.build_agent_result,
    _agent_runner.log_agent_spawn,
    _agent_provider_failures.is_transient_provider_failure,
)


class CleanProcessImportTest(unittest.TestCase):
    """Each owner imports cleanly before any siblings are cached."""

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


class RuntimeAnnotationTest(unittest.TestCase):
    """Owner-typed annotations stay runtime-resolvable across the package.

    The runner owner and the Codex / Claude backends annotate against the
    `models` owner, and `typing.get_type_hints()` -- exercised by tooling and
    introspection -- evaluates those annotations in each function's globals.
    The owner names must therefore be bound at runtime, not only for static
    type checkers.
    """

    def test_leaf_function_hints_resolve(self) -> None:
        for owner_annotated in _OWNER_ANNOTATED_FUNCS:
            with self.subTest(function=owner_annotated.__qualname__):
                # An unbound owner name surfaces here as NameError.
                typing.get_type_hints(owner_annotated)


class PublicSurfaceTest(unittest.TestCase):
    """Agent names are reached on the modules that define them."""

    def test_names_belong_to_their_defining_modules(self) -> None:
        owners = (
            (_agent_models, ("AgentResult", "AgentRunOptions", "CodexResult")),
            (_agent_runner, ("run_agent",)),
            (_agent_processes, ("terminate_all_running",)),
        )
        for owner, names in owners:
            for name in names:
                with self.subTest(name=name):
                    self.assertEqual(getattr(owner, name).__module__, owner.__name__)
