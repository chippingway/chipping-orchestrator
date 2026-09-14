# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The carriers one decomposition tick hands between its owners.

Each of these exists because the value it carries has to survive a boundary
the call stack alone would lose it across: the worktree policy a run decides
before it can raise, the agent identity a resume is locked to, the children a
split has already created when the next one fails, and the child labels a
parent scan read once and several branches then ask about.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator import config
from orchestrator.agents.models import AgentResult
from orchestrator.git.worktrees import decomposition as _worktree_decomposition


@dataclass
class _DecomposerRunPlan:
    agent_result: AgentResult | None
    keep_worktree: bool = False


@dataclass
class _DecomposerCleanup:
    """Close one decomposer worktree unless its run requests inspection."""

    spec: config.RepoSpec
    issue_number: int
    run_plan: _DecomposerRunPlan

    def close(self) -> None:
        if not self.run_plan.keep_worktree:
            _worktree_decomposition._cleanup_decompose_worktree(
                self.spec, self.issue_number,
            )


@dataclass(frozen=True)
class _DecomposerSession:
    spec: str
    backend: str
    extra_args: tuple[str, ...]
    session_id: str | None


@dataclass
class _SplitPlan:
    children_manifest: list
    is_umbrella: bool
    created: list[tuple[int, dict]]
    dep_graph: dict[str, list[int]]

    @classmethod
    def start(cls, children_manifest: list, is_umbrella: bool) -> _SplitPlan:
        return cls(children_manifest, is_umbrella, [], {})

    def record(self, idx: int, issue_number: int, child: dict) -> None:
        self.created.append((issue_number, child))
        depends_on = list(child.get("depends_on") or [])
        if depends_on:
            self.dep_graph[str(idx)] = depends_on


@dataclass(frozen=True)
class _ChildScan:
    children: list
    issues: dict[int, Issue]
    labels: dict[int, str | None]
