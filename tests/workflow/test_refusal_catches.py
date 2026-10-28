# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A best-effort catch around a write of the dispatched issue's record never swallows the writer's refusal.

The whole-state writer raises `RecordRefused` over a pinned record admission
refuses, with nothing written, and the dispatcher abandons the handler on it
before any exit road the handler has -- a scratch checkout's teardown among
them. A broad `except Exception` around such a write would take that refusal
for an ordinary failure to retry on a later tick and carry on to those roads,
so every one in the workflow package lets the refusal through first. The
branch resolver and the checkout creators raise its `BranchRefused` over a
record or a checkout live work may not stand on, and a catch around one of
them is held to the same rule: read as a failed request, the refusal would
park, retry, or hold an issue as unreadable rather than end the handler.
"""
from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass
from pathlib import Path

from orchestrator import workflow as _workflow

# The calls whose try blocks are held to it: the whole-state write itself, the
# drift check that writes its baseline (and the validating report refresh's
# reading of it), the split's first release walk, behind which the parent's
# record is written, and the live branch resolver with the creators and the
# resume checkout that resolve through it.
_WRITES_THE_RECORD = frozenset((
    "write_pinned_state",
    "_detect_user_content_change",
    "requirements_moved",
    "_activate_created_children",
    "_resolve_branch_name",
    "_ensure_worktree",
    "_ensure_pr_worktree",
    "_ensure_resume_worktree",
))

_BROAD = frozenset(("Exception", "BaseException"))

_REFUSAL = "RecordRefused"


def _walked(statements: list[ast.stmt], kind: type[ast.AST]) -> list:
    """Every node of `kind` anywhere in `statements`."""
    block = ast.Module(body=statements, type_ignores=[])
    return [node for node in ast.walk(block) if isinstance(node, kind)]


def _name(node: ast.AST) -> str:
    """The name a call or an exception class is spelled by, attribute or bare."""
    return node.attr if isinstance(node, ast.Attribute) else getattr(node, "id", "")


@dataclass(frozen=True)
class _Catch:
    """One handler of a try, as far as the refusal is concerned."""

    clause: ast.ExceptHandler

    @property
    def names(self) -> set[str]:
        """The exception class names it catches; empty for a bare `except`."""
        caught = self.clause.type
        if caught is None:
            return set()
        listed = caught.elts if isinstance(caught, ast.Tuple) else [caught]
        return set(map(_name, listed))

    @property
    def broad(self) -> bool:
        """Whether it would catch the refusal unnamed: bare, or `Exception` / `BaseException`."""
        return not self.names or bool(self.names & _BROAD)

    @property
    def reraises(self) -> bool:
        """Whether it raises what it caught again."""
        raises = _walked(self.clause.body, ast.Raise)
        return any(node.exc is None for node in raises)


def _swallowing(attempt: ast.Try) -> list[int]:
    """The lines of the broad handlers that would take the refusal for their own and keep it."""
    swallowing = []
    lets_through = False
    for catch in map(_Catch, attempt.handlers):
        keeps = catch.broad and not catch.reraises
        if keeps and not lets_through:
            swallowing.append(catch.clause.lineno)
        lets_through = lets_through or _REFUSAL in catch.names
    return swallowing


def _writes_the_record(node: ast.AST) -> bool:
    """Whether `node` is a try whose body calls a write of the dispatched issue's record."""
    if not isinstance(node, ast.Try):
        return False
    called = {_name(call.func) for call in _walked(node.body, ast.Call)}
    return bool(called & _WRITES_THE_RECORD)


def _in_module(module: Path, root: Path) -> list[str]:
    """Every broad catch in one module around a write of the record that lets the refusal through nowhere."""
    parsed = ast.parse(module.read_text(encoding="utf-8"))
    where = module.relative_to(root)
    tries = filter(_writes_the_record, ast.walk(parsed))
    lines = [line for attempt in tries for line in _swallowing(attempt)]
    return [f"{where}:{line}" for line in lines]


class RefusalCatchTest(unittest.TestCase):
    """Every broad catch around a write of the record lets `RecordRefused` through first."""

    def test_no_broad_catch_swallows_the_refusal(self) -> None:
        root = Path(_workflow.__file__).parent
        modules = sorted(root.rglob("*.py"))
        found = [where for module in modules for where in _in_module(module, root)]

        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
