# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The publication gate holding the leased no-op a recovery's landed road receipts a transfer through.

The transfer's machinery -- how far it got, its permit, and the gate's
answer -- is stood in for (`holding`); the hold is recorded through the
guarded `HOLD` (`workflow/engine/rewrite_recovery_parks.lands_a_hold`).
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

from orchestrator.git.base_sync import transfer_permits as _transfer_permits, transfers as _transfers
from orchestrator.git.base_sync.transfer_values import _Handoff
from orchestrator.workflow.stages.implementing import late_push as _late_push
from tests.workflow.engine import settled_finish_support as _settled
from tests.workflow.engine.rewrite_retry_permits_support import gated

# What the gate answered the permit-only no-op: held, with nothing pushed.
HELD = _late_push._PushedCandidate(held=True)


@contextlib.contextmanager
def holding(publishes=None):
    """A transfer permission outstanding, its permit granted, and the gate -- `publishes`, where given -- holding."""
    with (
        patch.object(_transfers, "_carried_by", return_value=_Handoff.OUTSTANDING),
        patch.object(_transfer_permits, "_permits_the_publication", return_value=True),
        patch.object(_late_push, "_publishes", publishes or gated(HELD)),
    ):
        yield


def holds(case) -> None:
    """One poll of `case` whose recovery takes the landed road, the gate holding its permit-only leased no-op."""
    with holding():
        case.recovers()


def holds_beside_a_newer_run(case, recorded: list, *_called, **_options):
    """The gate's answer, held once another road recorded a newer transaction beside the run, kept in `recorded`."""
    recorded.append(_settled.records_a_newer_run(case))
    return HELD
