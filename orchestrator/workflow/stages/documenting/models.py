# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The frozen records one documenting tick hands between its owners.

`_DocumentingContext` exists so the drift-unwind, worktree-prep, run, and
disposition owners thread one value instead of up to six positional arguments.
`branch` and `pr_number` are tick-invariant once the missing-`pr_number` guard
has passed, so every consumer downstream of it reads them off the context
rather than re-deriving a branch name the pinned state may already override.

`_DocumentingRun` carries what the disposition cannot re-derive after the fact:
`before_sha` is the only thing that tells a commit this run produced from one
already on the branch, `recovered` distinguishes the shortcut that spawned no
agent, and `ahead` is what makes a `DOCS: NO_CHANGE` verdict over a recovered
commit still push it instead of advancing with the docs stranded locally.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from github.Issue import Issue

from orchestrator.agents.models import AgentResult
from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState


@dataclass(frozen=True)
class _DocumentingContext:
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    branch: str
    pr_number: Any


@dataclass(frozen=True)
class _DocumentingRun:
    worktree: Any
    agent_result: AgentResult
    before_sha: str
    recovered: bool
    paused: bool
    ahead: int
    # The head `<remote>/<branch>` was at when `ahead` was counted, from the
    # same fetch. The count says a recovered docs commit is waiting; this says
    # which head the push that ships it replaces, and it is what the size gate
    # is pinned to -- read afterwards instead, a pull request somebody moved
    # between the probe and the push is adopted as the lease and overwritten.
    publication_head: str = ""

    @property
    def entered_head(self) -> str:
        """The head the push this run earns would replace.

        The remote tip this tick fetched, because that is what a force-push
        replaces whatever produced the commit. On a pass that ran with the
        branch in sync it is the head the run began at too -- one fact read
        twice -- and where they differ the branch was already AHEAD, so the
        head this run started on says nothing about the remote at all: the
        commit being shipped was made on an earlier tick.

        `before_sha` stands in only where nothing could read the tip, which is
        the reading the gate then refuses rather than pinning to nothing.

        Named to the size gate either way, which is what makes a pull request
        somebody moved while the agent was out refuse the push rather than be
        adopted as its lease and force-overwritten.
        """
        return self.publication_head or self.before_sha
