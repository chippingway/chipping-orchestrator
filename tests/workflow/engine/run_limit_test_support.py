# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Fixtures and protocol values the agent-run-limit park tests read against.

The state a live issue carries is what the park owner is written against, so
these build it directly rather than driving a stage: what the tests pin is the
protocol the dispatcher's hold and every gate that spends a run are written
on, not the road of any one of them.
"""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    run_limit_state as _run_limit_state,
    run_limit_values as _run_limit_values,
)
from orchestrator.workflow.engine.run_budget_models import AgentRunLaunch
from orchestrator.workflow.engine.run_ledger_values import AGENT_RUN_ALLOWANCE, AGENT_RUNS_USED
from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.engine import run_limit_seeds as _limit_seeds
from tests.workflow.fixtures import LABEL_IMPLEMENTING

ISSUE_NUMBER = 1541

RUN_LIMIT_EVENT = "agent_run_limit"

DELIVERED = _run_limit_values.RunLimitPhase.DELIVERED

RECONCILED = _run_limit_values.RunLimitPhase.RECONCILED

STANDING = _run_limit_values.RunLimitPhase.STANDING

GRANTED = _run_limit_values.RunLimitPhase.GRANTED

REFUSED = _run_limit_values.RunLimitPhase.REFUSED

WATERMARK = 900

LAST_ACTION_COMMENT_ID = "last_action_comment_id"

NOTICE = _run_limit_values.AGENT_RUN_LIMIT_NOTICE

ALLOWANCE_FIELD = AGENT_RUN_ALLOWANCE

USED_FIELD = AGENT_RUNS_USED

# The login the fake client posts under, and so the only author a receipt this
# orchestrator reads back off a thread may carry.
BOT_LOGIN = "orchestrator"

# A human whose reply is the input a refused launch was handed.
TRUSTED_AUTHOR = "alice"

# Where the ids of the comments this orchestrator posted are recorded.
LEDGER_FIELD = "orchestrator_comment_ids"

OUTSIDER = "stranger"

# The launch a park is taken against, as the boundary that refuses one hands
# it over: what the budget record names as the work the ceiling stopped.
LAUNCH = AgentRunLaunch(
    fingerprint="c0ffee" * 8,
    stage="implementing",
    agent_role="developer",
)


def notice_text(*, allowance: int = _limit_seeds.ALLOWANCE, used: int | None = None) -> str:
    return _run_limit_state._limit_message(_limit_seeds.ledger(allowance=allowance, used=used))


def issue_and_client(*comments):
    gh = FakeGitHubClient()
    issue = make_issue(ISSUE_NUMBER, label=LABEL_IMPLEMENTING)
    issue.comments.extend(comments)
    gh.add_issue(issue)
    return gh, issue


def owed(state: PinnedState):
    return _run_limit_state._owed_notice(state)


def phases(gh) -> list:
    return [
        record["phase"]
        for record in gh.recorded_events
        if record["event"] == RUN_LIMIT_EVENT
    ]
