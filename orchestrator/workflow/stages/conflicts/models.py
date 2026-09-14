# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one conflict tick hands between its owners.

`_ConflictContext` is the tick itself. The rebase loop threads it through eight
owners, and bundling the four handles keeps each of them from re-reading pinned
state: the `conflict_round` bump, the label flip, and the audit event all have
to land on the same `state` object the handler read at the top, or a park and
the write that must accompany it would disagree.

`_WorktreeSync` is the worktree measured against the freshly fetched remote PR
head, and the three shapes it can take are the whole reconciliation decision --
in sync, ahead (a prior tick committed but never pushed), or behind (stale or
diverged, and refused).

`_DivergeDecision` is how the diverged-worktree guard answers without the
caller re-deriving it: `parked` says the tick is over, and `publish_lease`
carries the exact PR head validated as orchestrator-produced so the force-push
below leases against that SHA rather than whatever `ls-remote` reports later.

`_ConflictResumeRun` carries what a finished dev resume cannot re-derive: the
worktree it actually ran in (the resume may have re-created it), the result,
and whether an operator paused mid-run.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState


@dataclass(frozen=True)
class _ConflictContext:
    """The per-tick `resolving_conflict` handles, bundled so the rebase-loop
    helpers thread them as a single value instead of four positional
    arguments (mirrors fixing's `_FixingContext`)."""
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState


@dataclass(frozen=True)
class _WorktreeSync:
    """A PR worktree measured against its remote branch tip: the worktree
    path, the branch name, and how far HEAD is ahead / behind the freshly
    fetched `<remote>/<branch>` head."""
    worktree: Path
    branch: str
    ahead: int
    behind: int
    # The commit that fetched ref was AT, read from the same ref the counts
    # above were taken against. It travels with them because the counts are a
    # claim about it and nothing downstream can re-derive it: a push proved
    # against "ahead and not behind" is pinned to this exact head, and a
    # caller that dropped it would leave the gate reading the pull request
    # for itself and adopting whatever landed in between. Empty is a tip
    # nothing could read, which every reader treats as no head established.
    fetched_tip: str = ""


@dataclass(frozen=True)
class _DivergeDecision:
    """Verdict of the diverged-worktree guard: whether the tick parked, plus
    the force-publish lease pinned to a validated orchestrator-produced PR
    head when an already-rebased worktree may be force-published instead."""
    parked: bool
    publish_lease: str | None = None


@dataclass(frozen=True)
class _ConflictResumeRun:
    """The outputs of one locked dev resume in the rebase loop: the worktree
    the agent ran in (`_resume_dev_with_text` may re-create it), the agent
    result, and whether an operator paused mid-run."""
    worktree: Path
    dev_result: AgentResult
    paused: bool
