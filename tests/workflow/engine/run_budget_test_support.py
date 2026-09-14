# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""How the shared agent-run budget stream is read back off both of its sinks.

Three owners write to it -- the circuit that charges a launch, the park a
spent lifetime takes, and the command that widens one -- so the fixtures a
case reads it with sit apart from all three. What every one of them needs is
the same two things: the records a sink was handed, and the phases in them.

The analytics half needs a patch and the audit half does not. That sink is
disabled unless a path is configured, which is every test's default, so a case
that has to see what it was handed installs the capture below; a case that
only has to count transitions reads the audit copy, which the fake client
keeps for free.
"""
from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

from orchestrator.workflow.engine import run_budget as _run_budget

EVENT = _run_budget.AGENT_RUN_BUDGET_EVENT

RESERVED = _run_budget.BudgetPhase.RESERVED

STARTED = _run_budget.BudgetPhase.STARTED

EXHAUSTED = _run_budget.BudgetPhase.EXHAUSTED

EXTENDED = _run_budget.BudgetPhase.EXTENDED

ALLOWANCE_SPENT = _run_budget.ExhaustionReason.ALLOWANCE_SPENT

ALLOWANCE_EXCEEDED = _run_budget.ExhaustionReason.ALLOWANCE_EXCEEDED

# What `remaining` says where the allowance bounds nothing at all.
UNLIMITED = _run_budget.REMAINING_UNLIMITED

# The payload's own field names, spelled here rather than in each case: they
# are a wire contract on two sinks and a Postgres column, so a rename is a
# migration and the one place it has to be made is this list.
PHASE = "phase"

CONFIGURED = "configured"

ALLOWANCE = "allowance"

USED = "used"

REMAINING = "remaining"

RESERVATION_ID = "reservation_id"

AGENT_ROLE = "agent_role"

REASON = "reason"

STAGE = "stage"

EVENT_KEY = "event"

# Where the analytics half of a dual emission lands.
ANALYTICS_APPEND = (
    "orchestrator.observability.analytics.recording.events.append_record"
)


def analytics_of(emit: Callable[[], None]) -> list[dict]:
    """The analytics records one emission wrote, in the order written."""
    appended: list[dict] = []
    with patch(ANALYTICS_APPEND, appended.append):
        emit()
    return appended


def audited(gh) -> list[dict]:
    """The budget records the audit sink was handed, in the order written."""
    return [
        record for record in gh.recorded_events
        if record[EVENT_KEY] == EVENT
    ]


def phases(records: list[dict]) -> list[str]:
    """The phase each record describes, in the order they were written."""
    return [record[PHASE] for record in records]
