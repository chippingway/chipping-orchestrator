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
    """Mutable cleanup policy and stable inputs for one question-stage tick."""
    gh: GitHubClient
    spec: _config_models.RepoSpec
    issue: Issue
    state: PinnedState
    keep_worktree: bool

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
