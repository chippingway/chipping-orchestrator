# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures, parsed runs, and the callable agent the usage-accumulator tests run on."""
from __future__ import annotations

from datetime import date

from orchestrator.observability.usage import cost_evidence as usage_cost, token_evidence as usage_tokens
from orchestrator.observability.usage.metrics import UsageMetrics
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

    def __call__(self, *_args, options):
        resume_session_id = options.resume_session_id
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


def parsed(
    cost: usage_cost.CostEvidence, *, overlap: str = usage_tokens.DISJOINT, backend: str = "claude", **counts: int,
) -> UsageMetrics:
    """One run's usage as a parser hands it back: `counts` observed with `overlap` between them, costing `cost`."""
    usage = UsageMetrics(
        backend=backend, token_evidence=usage_tokens.TokenEvidence.reporting(counts, overlap), **counts,
    )
    usage.apply_cost(cost)
    return usage


def stated(completeness: str, *parts: tuple) -> usage_cost.CostEvidence:
    """A cost of `completeness` stating each part: a basis, its amount, and its rates' ISO verification days."""
    contributions = tuple(
        usage_cost.CostContribution(basis, amount, tuple(map(date.fromisoformat, days)))
        for basis, amount, *days in parts
    )
    return usage_cost.CostEvidence(completeness, contributions)
