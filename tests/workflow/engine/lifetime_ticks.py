# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tick entry points used by the agent-run lifetime scenarios."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from orchestrator.git.base_sync import refresh as _base_refresh
from orchestrator.workflow.engine import (
    issue_processing as _issue_processing,
    prompt_context as _prompt_context,
)
from tests.support.fakes import FakeGitHubClient
from tests.workflow import published_reports as _published_reports
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
)

# The requirements baseline a settled round leaves on the pinned comment.
_BASELINE = "user_content_hash"


def dispatched_tick(github: FakeGitHubClient, issue) -> Callable[[], Any]:
    """The whole of an ordinary tick: one issue routed by its label."""
    return lambda: _issue_processing._route_issue_to_handler(
        github, _TEST_SPEC, issue, github.workflow_label(issue),
    )


def reviewed_tick(github: FakeGitHubClient, issue) -> Callable[[], Any]:
    """An ordinary tick, over a pull request carrying a report of where it stands.

    Every round of these loops publishes its own report before a reviewer is
    handed it. The fake remote never moves the pull request, so the report a
    developer's push proved names a commit the pull request is not standing
    on and is held: what the round's delivery published is put there instead,
    in place of whatever report an earlier round left, written against the
    thread the round answered -- which is the baseline its settlement leaves.
    """
    github._pinned[issue.number].data[_BASELINE] = _prompt_context._delivered_thread(
        github, issue, github.read_pinned_state(issue),
    ).requirements_revision
    _published_reports.republishes_the_report(github, issue)
    return dispatched_tick(github, issue)


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
