# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures and the callable agent the usage-accumulator tests run on."""
from __future__ import annotations

from tests.support import fakes
from tests.workflow import fixtures

FakeGitHubClient = fakes.FakeGitHubClient
make_issue = fakes.make_issue
REVIEW_APPROVED_MESSAGE = fixtures.REVIEW_APPROVED_MESSAGE
_PatchedWorkflowMixin = fixtures._PatchedWorkflowMixin
_TEST_SPEC = fixtures._TEST_SPEC
_agent = fixtures._agent
_fake_worktree = fixtures._fake_worktree
_open_pr_for = fixtures._open_pr_for


class _PoisonedThenFreshRun:
    def __init__(self) -> None:
        self.calls: list[str | None] = []

    def __call__(self, *_args, resume_session_id=None, **_kwargs):
        self.calls.append(resume_session_id)
        if resume_session_id == "poisoned-sess":
            return _agent(
                session_id="",
                last_message="",
                stderr=(
                    "Error: No conversation found with session ID: x"
                ),
            )
        return _agent(session_id="fresh-sess", last_message="ok")
