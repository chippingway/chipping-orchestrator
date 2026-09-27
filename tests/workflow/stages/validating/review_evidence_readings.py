# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a review-evidence case reads back off the in-memory client.

The artifacts the pull request carries, the evidence the pinned comment calls
current, the agents spawned across every tick, the notices posted on either
thread, the prompt a run was handed -- and the one thing a case writes, a
reply on the issue thread -- spelled once for every module that walks the
world `review_evidence_test_support` seeds.
"""
from __future__ import annotations

from orchestrator.github import verification_artifacts as _artifacts
from orchestrator.workflow.engine import verification_settlement_state as _settlement
from tests.support.fakes import FakeComment, FakeUser
from tests.workflow.engine.event_values import EVENT_AGENT_SPAWN

RUN_AGENT = "run_agent"


def artifacts(case) -> list:
    """Every verification artifact on `case`'s pull request, oldest first."""
    readings = (
        _artifacts.verification_artifact_from_comment(posted, bot_login=case.github._bot_login)
        for posted in case.pull_request.issue_comments
    )
    return [found for found in readings if found is not None]


def current_evidence(case):
    """The evidence `case`'s pinned comment records as current."""
    return _settlement.read_current_evidence(case.github.read_pinned_state(case.issue))


def spawns(case, role: str) -> int:
    """How many agents of `role` `case`'s issue has spawned, across every tick."""
    return sum(
        1 for event in case.github.recorded_events
        if event["event"] == EVENT_AGENT_SPAWN and event.get("agent_role") == role
    )


def pr_comments(case, notice: str = "") -> list[str]:
    """Every comment posted on the pull request that carries `notice`, in posting order."""
    return [body for _, body in case.github.posted_pr_comments if notice in body]


def issue_notices(case, notice: str) -> int:
    """How many comments posted on the issue carry `notice`."""
    return sum(1 for _, body in case.github.posted_comments if notice in body)


def replies(case, text: str) -> None:
    """The issue author's reply on its thread, below everything posted on it so far."""
    case.issue.comments.append(FakeComment(
        id=case.github._next_comment_id(case.issue),
        body=text,
        user=FakeUser(case.issue.user.login),
    ))


def prompt(mocks, call: int = 0) -> str:
    """The prompt one agent run of a tick was handed."""
    runs = mocks[RUN_AGENT].call_args_list
    return runs[call].args[1]
