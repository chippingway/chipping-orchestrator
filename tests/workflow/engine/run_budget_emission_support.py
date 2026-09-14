# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Ledger, launch, and emission fixtures for agent-run accounting records."""
from __future__ import annotations

from orchestrator.workflow.engine import run_budget as _run_budget
from orchestrator.workflow.engine.run_ledger import AgentRunLedger
from tests.workflow.engine import run_budget_test_support as budget

_STAGE = "implementing"

_ROLE = "developer"

# A whole SHA-256 digest, which is what the circuit charges a launch under.
_FINGERPRINT = (
    "ababababababababababababababababababababababababababababababcdef"
)

_LAUNCH = _run_budget.AgentRunLaunch(
    fingerprint=_FINGERPRINT, stage=_STAGE, agent_role=_ROLE,
)

_CONFIGURED = 50

_USED = 7

_TS = "ts"


def _ledger(**overrides) -> AgentRunLedger:
    """One ledger reading, as a caller about to spend a run hands it over."""
    named = {
        "configured": _CONFIGURED,
        "allowance": _CONFIGURED,
        "used": _USED,
        "reservation": None,
    }
    return AgentRunLedger(**{**named, **overrides})


def _charge(gh, issue, phase=budget.RESERVED, **reading) -> None:
    _run_budget._emit_charge(gh, issue, phase, _ledger(**reading), _LAUNCH)


def _started(gh, issue) -> None:
    _charge(gh, issue, budget.STARTED)


def _refusal(gh, issue, **reading) -> None:
    _run_budget._emit_exhaustion(
        gh, issue, _ledger(**{"used": _CONFIGURED, **reading}), _LAUNCH,
    )


def _extension(gh, issue, **reading) -> None:
    _run_budget._emit_extension(gh, issue, _ledger(**reading))


def _unlimited_charge(gh, issue) -> None:
    _charge(gh, issue, configured=0, allowance=0)


def _without_ts(record: dict) -> dict:
    return {key: found for key, found in record.items() if key != _TS}
