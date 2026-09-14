# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The one road through the production tree that ends in an agent process.

A lifetime ceiling on agent runs is worth what the number of places a run can
start makes it worth. The charge is taken around a single call -- the
`run_agent` inside `_run_agent_tracked` -- so every role, stage and cycle pays
it without a gate of its own, and a second call anywhere in the tree would be
a road that spends runs nothing counts. No test that drives a handler can see
that road, because the handler it would belong to does not exist yet; so the
shape is read off the source instead.

Three hops make up the road, and each is checked for who else may name it: the
subprocess the backend builds a command for, the two backend entries the
runner dispatches between, and the runner entry the workflow's charged wrapper
calls. A stage reaching `run_claude` directly, or a helper holding `run_agent`
in a variable to invoke a line later, is the bypass this exists to fail on --
and either is one edit away from being written by somebody who never read the
circuit. A reference is what is counted rather than a call, because the second
of those spellings makes the call somewhere the name is no longer written.

Two more readings sit inside the wrapper itself. Named by one module is not
yet invoked by one function, so the call is held to `_run_agent_tracked`'s own
body; and a charge taken behind the spawn is one a crash, a timeout, or a
shutdown kill collects for free, so the circuit has to be asked on a line
above the one that starts the process.
"""
from __future__ import annotations

import ast
import unittest

from tests.repository.layout_test_support import (
    PACKAGE_ROOT,
    dotted_name,
    module_path,
    parsed,
    python_files,
)

_PACKAGE = "orchestrator"

# The hops, bottom to top: the hardened subprocess launch, the per-backend
# command builders over it, and the dispatch entry over those.
_SUBPROCESS_ENTRY = "run_subprocess"

_BACKEND_ENTRIES = ("run_claude", "run_codex")

_DISPATCH_ENTRY = "run_agent"

# The boundary the charge is taken inside, and the circuit it asks.
_TRACKED_RUN = "_run_agent_tracked"

_CHARGE = "_charge_launch"

_BACKEND_OWNERS = (
    f"{_PACKAGE}.agents.backends.claude",
    f"{_PACKAGE}.agents.backends.codex",
)

_DISPATCH_OWNER = f"{_PACKAGE}.agents.runner"

# The package initializer publishes the dispatch entry as the agents API, so
# it names the function without ever starting anything with it.
_AGENTS_FACADE = f"{_PACKAGE}.agents"

_TRACKED_OWNER = f"{_PACKAGE}.workflow.engine.usage"


def _read_name(node: ast.AST) -> str | None:
    """The trailing name one expression reads, attribute or bare.

    Taken off the spelling rather than resolved back through the import that
    produced it. What a bypass looks like is `runner.run_agent` or a
    `run_agent` bound from wherever, and both answer here; resolving imports
    would answer the same question at the cost of a reader that can be one
    aliasing form out of date.

    A store is not a read: the module that defines the function, and the
    initializer target that publishes it, name it without reaching it.
    """
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
        return node.id
    return None


def _modules_naming(*names: str) -> frozenset[str]:
    """Every production module that reads one of `names` at all.

    A reference rather than a call, because a name held in a variable is a
    call the next line makes: a check that looked only at call sites would
    wave through a module that aliased the spawn and invoked the alias.
    """
    return frozenset(
        dotted_name(module, PACKAGE_ROOT)
        for module in python_files(PACKAGE_ROOT)
        if any(
            _read_name(node) in names for node in ast.walk(parsed(module))
        )
    )


def _call_lines(tree: ast.AST, name: str) -> tuple[int, ...]:
    """Where inside one tree `name` is invoked."""
    return tuple(sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _read_name(node.func) == name
    ))


def _function_named(tree: ast.AST, name: str) -> ast.FunctionDef:
    """The one function definition a module carries under `name`."""
    defined = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    ]
    return defined[0]


class AgentSpawnBoundaryTest(unittest.TestCase):
    """Nothing starts an agent except through the boundary that charges it."""

    def setUp(self) -> None:
        self.tracked_module = parsed(
            module_path(_TRACKED_OWNER, PACKAGE_ROOT),
        )
        self.tracked_run = _function_named(self.tracked_module, _TRACKED_RUN)

    def test_one_module_names_the_dispatch_entry(self) -> None:
        # The workflow's charged wrapper, plus the initializer that republishes
        # the entry as the agents package API. A stage or engine owner here is
        # a spawn road that never passes an `AgentRunBudget`, and so a run the
        # lifetime ledger is never told about.
        self.assertEqual(
            _modules_naming(_DISPATCH_ENTRY),
            frozenset((_AGENTS_FACADE, _TRACKED_OWNER)),
        )

    def test_only_the_runner_names_a_backend(self) -> None:
        # Both backend entries build a command and run it, so naming one is
        # starting a process. Reaching them anywhere but the dispatcher would
        # skip the entry the check above holds to one caller.
        self.assertEqual(
            _modules_naming(*_BACKEND_ENTRIES), frozenset((_DISPATCH_OWNER,)),
        )

    def test_only_backends_name_the_subprocess(self) -> None:
        # The last hop, under both backends. A caller here that is not one of
        # them would reach a CLI without a backend having chosen the command,
        # which is the same run by a road neither check above can see.
        self.assertEqual(
            _modules_naming(_SUBPROCESS_ENTRY), frozenset(_BACKEND_OWNERS),
        )

    def test_the_wrapper_owns_the_only_spawn(self) -> None:
        # Named by one module is not yet invoked by one function: the owner
        # could grow a second helper that calls the entry beside the wrapper,
        # and that helper would be uncharged.
        self.assertEqual(
            _call_lines(self.tracked_module, _DISPATCH_ENTRY),
            _call_lines(self.tracked_run, _DISPATCH_ENTRY),
        )

    def test_the_charge_is_asked_above_the_spawn(self) -> None:
        # Both are inside the same function, so the line order is the whole
        # ordering: a charge taken after the process exists is one a crash, a
        # timeout, or a shutdown kill has already collected for free.
        charged = _call_lines(self.tracked_run, _CHARGE)
        spawned = _call_lines(self.tracked_run, _DISPATCH_ENTRY)

        self.assertEqual(len(charged), 1)
        self.assertEqual(len(spawned), 1)
        self.assertLess(charged[0], spawned[0])


if __name__ == "__main__":
    unittest.main()
