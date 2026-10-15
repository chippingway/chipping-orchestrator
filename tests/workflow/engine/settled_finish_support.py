# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A finish held to the dormant settled-evidence policy, and the run ledger another road's launch charged.

No production road selects the policy (`rewrite_finish_models.LandedFinish.proves_settled`),
so a case builds the finish itself over the pinned comment read afresh
(`dormant`) and asks one of the policy's primitives directly. Beside it,
`charges` leaves the run ledger another road's launch charged on the comment,
for a case to read back exactly as left (`assert_charged_as_left`): nothing
those primitives retire, mark, or put back spends, reserves, or releases a run.
"""
from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

from orchestrator.workflow.engine import run_ledger_values as _run_ledger
from orchestrator.workflow.engine.rewrite_finish_models import LandedFinish

# The run ledger another road's launch left on the comment: the runs spent on
# it and on the legacy usage meter beside it, and a launch reserved and
# started under its fingerprint, at the count it was owed at.
_CHARGED = MappingProxyType({
    _run_ledger.AGENT_RUNS_USED: 5,
    "issue_agent_runs": 4,
    _run_ledger.AGENT_RUN_RESERVATION: "started",
    _run_ledger.AGENT_RUN_FINGERPRINT: "developer:issue-7:round-3",
    _run_ledger.AGENT_RUN_OWED_STARTED: 4,
})


def dormant(finish: LandedFinish) -> LandedFinish:
    """`finish` held to the dormant settled-evidence policy."""
    return replace(finish, proves_settled=True)


def charges(case) -> None:
    """Leave the run ledger another road's launch charged (`_CHARGED`) on `case`'s comment as it stands."""
    state = case.gh.read_pinned_state(case.issue)
    for key, charged in _CHARGED.items():
        state.set(key, charged)
    case.gh.write_pinned_state(case.issue, state)


def assert_charged_as_left(case) -> None:
    """`case`'s run ledger exactly as `charges` left it: nothing spent, reserved, or released since."""
    pinned = case.gh.pinned_data(case.issue.number)
    ledger = {key: pinned.get(key) for key in _CHARGED}
    case.assertEqual(ledger, dict(_CHARGED))
