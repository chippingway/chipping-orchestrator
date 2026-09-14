# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tick entry points used by the agent-run lifetime scenarios."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from orchestrator.git.base_sync import refresh as _base_refresh
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
)


def dispatched_tick(github: FakeGitHubClient, issue) -> Callable[[], Any]:
    """The whole of an ordinary tick: one issue routed by its label."""
    return lambda: _issue_processing._route_issue_to_handler(
        github, _TEST_SPEC, issue, github.workflow_label(issue),
    )


def refreshed_tick(github: FakeGitHubClient, issue) -> Callable[[], Any]:
    """The half of a tick that runs before any issue is dispatched.

    The base refresh is not a stage and starts no agent, which is the point of
    driving it here: it rewrites the branch, resets the round the review cap
    is counted on, and hands the issue back to `validating` -- and none of
    that returns a run.
    """
    return lambda: _base_refresh._sync_worktree_with_base(
        github, _TEST_SPEC, _FAKE_WT, issue.number,
    )
