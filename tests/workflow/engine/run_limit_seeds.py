# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Ledger and pinned-state seeds for exhausted or parked agent-run budgets."""
from __future__ import annotations

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    run_limit_state as _run_limit_state,
    run_limit_values as _run_limit_values,
)
from orchestrator.workflow.engine.run_ledger_models import AgentRunLedger

ALLOWANCE = 50

AWAITING_HUMAN = "awaiting_human"

PARK_REASON = "park_reason"


def ledger(*, allowance: int = ALLOWANCE, used: int | None = None):
    """One spent ledger, as the reader that refuses a spawn hands it over."""
    return AgentRunLedger(
        configured=ALLOWANCE,
        allowance=allowance,
        used=allowance if used is None else used,
        reservation=None,
    )


def state_with(**fields) -> PinnedState:
    return PinnedState(comment_id=1, data=dict(fields))


def parked_state(*, owing: bool = False, **fields) -> PinnedState:
    """An issue standing on an agent-run-limit park, said or still owed.

    Every field is overridable, including the ones that make the park what it
    is: what a hand-edited or older pinned comment leaves behind is exactly
    what the safe defaults are read against.
    """
    standing = {
        AWAITING_HUMAN: True,
        PARK_REASON: _run_limit_values.PARK_AGENT_RUN_LIMIT,
    }
    parked = state_with(**{**standing, **fields})
    if owing:
        _run_limit_state._owe_notice(parked, ledger())
    return parked


def owing_park() -> PinnedState:
    """A park already standing whose sentence the thread was never told."""
    return parked_state(owing=True)
