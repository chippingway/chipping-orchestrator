# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The records one question tick hands between its owners.

`_QuestionRun` is the tick itself, and it is the one mutable record here
because `keep_worktree` is a policy the tick revises: it opens holding whatever
the prior park implies, so a run that never reaches its disposition still tears
down (or preserves) the right tree, and the assessment overwrites it before any
park side effect can fail. Bundling the four handles also keeps the owners from
re-reading pinned state -- the session id, the usage counters, and the park all
have to land on the same `state` object the handler read at the top.

`route` is the one field decided before anything runs and never revised, and it
is settled here rather than where the two roads part because the flag it is read
off does not survive the tick: a resume clears `awaiting_human` on its way to
the disposition, so a park published afterwards could no longer tell which road
it came off. Taken at the top, the same value both picks the road and is what
the park reports having taken.

`_QuestionSession` is the locked agent identity, carried as the full configured
spec rather than a bare backend so a `DECOMPOSE_AGENT` flip between ticks cannot
retarget a conversation already in progress.

`_QuestionOutcome` is what the assessment decided without the router re-deriving
it: the park to publish, the cleanup policy it requires, and the answer or dirty
paths that park's comment quotes.
"""
from __future__ import annotations

from dataclasses import dataclass

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.stages.question import state as _state


@dataclass
class _QuestionRun:
    """Mutable cleanup policy, road, and stable inputs for one question tick."""
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    keep_worktree: bool
    route: str

    @classmethod
    def start(
        cls, gh: GitHubClient, spec: _config_models.RepoSpec, issue: Issue,
    ) -> _QuestionRun:
        state = gh.read_pinned_state(issue)
        return cls(
            gh=gh,
            spec=spec,
            issue=issue,
            state=state,
            keep_worktree=(
                state.get("park_reason") in _state._UNSAFE_QUESTION_PARKS
            ),
            route=(
                _state._ROUTE_QUESTION_RESUME
                if state.get("awaiting_human")
                else _state._ROUTE_QUESTION_ROUND
            ),
        )


@dataclass(frozen=True)
class _QuestionSession:
    """Locked agent identity used by one question-agent invocation."""
    agent_spec: str
    backend: str
    extra_args: tuple[str, ...]
    session_id: str | None


@dataclass(frozen=True)
class _QuestionOutcome:
    """Post-agent route and the cleanup policy it requires."""
    park_reason: str | None
    keep_worktree: bool
    answer: str = ""
    dirty_files: tuple[str, ...] = ()
