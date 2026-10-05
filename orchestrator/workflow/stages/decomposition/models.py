# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The carriers one decomposition tick hands between its owners.

Each of these exists because the value it carries has to survive a boundary
the call stack alone would lose it across: the worktree policy a run decides
before it can raise, the agent identity a resume is locked to, the children a
split has already created when the next one fails -- with the lineage it
seeds each of them with, the attempt their receipts name, and the ones a seed
under the child's claim had to leave for the split's recovery to seed and
finalize -- and the child labels a parent scan read once, and takes again for
a child a write reads anew under that child's claim, that several branches
then ask about.
"""
from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import decomposition as _worktree_decomposition
from orchestrator.github.issues import issue_is_closed
from orchestrator.workflow.stages.decomposition.replacement_lineage import ReplacementLineage
from orchestrator.workflow.state import WorkflowLabel


@dataclass
class _DecomposerRunPlan:
    agent_result: AgentResult | None
    keep_worktree: bool = False


@dataclass
class _DecomposerCleanup:
    """Close one decomposer worktree unless its run requests inspection."""

    spec: _config_models.RepoSpec
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
    lineage: ReplacementLineage = field(default_factory=ReplacementLineage)
    attempt: str = ""
    # Created and recorded, but held by another poller on this host when the
    # split went to seed them: the split stops short of its finalize, and its
    # recovery seeds them and finalizes it.
    unseeded: list[int] = field(default_factory=list)

    @classmethod
    def start(
        cls, children_manifest: list, is_umbrella: bool, lineage: ReplacementLineage | None = None,
    ) -> _SplitPlan:
        return cls(children_manifest, is_umbrella, [], {}, lineage or ReplacementLineage())

    def record(self, idx: int, issue_number: int, child: dict) -> None:
        self.created.append((issue_number, child))
        depends_on = list(child.get("depends_on") or [])
        if depends_on:
            self.dep_graph[str(idx)] = depends_on

    def declared_dependencies(self) -> dict[str, list[int]]:
        """Every slice's dependencies as the manifest declared them, keyed as `record` keys them."""
        return {
            str(idx): list(child["depends_on"])
            for idx, child in enumerate(self.children_manifest)
            if child.get("depends_on")
        }


@dataclass(frozen=True)
class _ChildScan:
    children: list
    issues: dict[int, Issue]
    labels: dict[int, str | None]

    def waiting(self, number: int) -> bool:
        """Whether this scan read the child open and `blocked`, the one reading a release walk starts a child from."""
        child = self.issues.get(number)
        if child is None or issue_is_closed(child):
            return False
        return self.labels.get(number) == WorkflowLabel.BLOCKED

    def adopt(self, current: _ChildScan | None) -> bool:
        """Take a later reading of some of these children over this one, and say whether there was one."""
        if current is None:
            return False
        self.issues.update(current.issues)
        self.labels.update(current.labels)
        return True

    def closed_unended(self, number: int, ended: Collection[str | None]) -> bool:
        """Whether this scan read the child closed on a label none of `ended` explains."""
        child = self.issues.get(number)
        if child is None or not issue_is_closed(child):
            return False
        return self.labels.get(number) not in ended
