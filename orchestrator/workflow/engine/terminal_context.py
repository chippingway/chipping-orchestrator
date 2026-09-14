# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Carry one terminal's issue, publication, pinned state, and originating stage.

The context keeps the pull-request number and conflict-round attribution
on the state being finalized, including the zero round a conflict stage
reports before it has recorded one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    terminal_reading as _terminal_reading,
)
from orchestrator.workflow.state import stage_name


def _terminal_context(
    gh: GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: PinnedState,
    pull_request: Any,
) -> _ReviewTerminalContext:
    """The subject a terminal finalizes, built from one proved reading."""
    return _ReviewTerminalContext(
        gh=gh,
        spec=spec,
        issue=issue,
        state=state,
        pr=pull_request,
        stage=stage_name(gh.workflow_label(issue)),
    )


@dataclass(frozen=True)
class _ReviewTerminalContext:
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    pr: Any
    stage: str | None

    @property
    def pr_number(self) -> int:
        return int(self.state.get(_terminal_reading._PR_NUMBER))

    @property
    def conflict_round(self):
        conflict_round = self.state.get("conflict_round")
        if self.stage == "resolving_conflict":
            return int(conflict_round or 0)
        return conflict_round
