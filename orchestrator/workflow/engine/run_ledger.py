# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read, reserve, start, and settle the lifetime agent-run ledger in pinned state.

Validated values and the immutable snapshot have sibling owners. Mutations keep
the used count monotonic, and settlement clears only the standing reservation.
PROJECTED_KEYS names the allowance and count that issue-state projection keeps."""
from __future__ import annotations

from orchestrator.config import settings as config
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    run_ledger_models as _run_ledger_models,
    run_ledger_values as _run_ledger_values,
)

# What an issue-state projection keeps of this ledger. The allowance and the
# spend are facts about the ISSUE -- what it may have, and what it has already
# taken -- so they outlive any one attempt on it, and a projection that
# dropped them would hand a restarted issue a fresh lifetime. The reservation
# is not one of those facts: it describes a launch, and a projection rebuilds
# an issue that has none.
PROJECTED_KEYS = (_run_ledger_values.AGENT_RUN_ALLOWANCE, _run_ledger_values.AGENT_RUNS_USED)


def _read_ledger(state: PinnedState) -> _run_ledger_models.AgentRunLedger:
    """This issue's allowance, what it has spent, and the launch in flight."""
    return _run_ledger_models.AgentRunLedger(
        configured=config.MAX_AGENT_RUNS_PER_ISSUE,
        allowance=_run_ledger_values._allowance_in_force(state),
        used=_run_ledger_values._runs_used(state),
        reservation=_run_ledger_values._reservation(state),
        fingerprint=_run_ledger_values._fingerprint(state),
    )


def _reserve_run(state: PinnedState, fingerprint: str) -> _run_ledger_models.AgentRunLedger:
    """Charge one run to this issue and record the launch it was charged for.

    In memory only, like every other field a tick stages: what makes the
    charge durable is the caller's own write, which keeps the count and the
    launch it was taken for in one write rather than two.

    The charge lands ahead of the spawn on purpose. Charged behind it, a run
    that crashed, timed out, or was killed mid-flight is a run the issue spent
    and the ledger never saw -- and those are exactly the runs a lifetime
    ceiling exists to stop an issue repeating.
    """
    state.set(_run_ledger_values.AGENT_RUNS_USED, _run_ledger_values._runs_used(state) + 1)
    state.set(_run_ledger_values.AGENT_RUN_RESERVATION, _run_ledger_models.RunPhase.RESERVED)
    state.set(_run_ledger_values.AGENT_RUN_FINGERPRINT, fingerprint)
    return _read_ledger(state)


def _start_reserved_run(state: PinnedState) -> bool:
    """Move a standing reservation to the phase a launch that ran is in.

    Returns whether there was one to move. An issue holding no reservation is
    not given one here: the charge is what a reservation stands for, and one
    minted at the spawn would be a launch nothing paid for.
    """
    if _run_ledger_values._reservation(state) is None:
        return False
    state.set(_run_ledger_values.AGENT_RUN_RESERVATION, _run_ledger_models.RunPhase.STARTED)
    return True


def _settle_run(state: PinnedState) -> None:
    """Drop the reservation a finished launch held.

    The charge is untouched, which is the whole point of settling rather than
    releasing: the run happened, the issue paid for it, and what ends is only
    the claim that a launch is outstanding.

    The launch it named goes with it. A fingerprint left behind names a claim
    nothing stands behind, and the pair is only ever read together.
    """
    state.data.pop(_run_ledger_values.AGENT_RUN_RESERVATION, None)
    state.data.pop(_run_ledger_values.AGENT_RUN_FINGERPRINT, None)
