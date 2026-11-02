# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The daily retry a manifest correction's launch pays, charged in the write that reserves its run.

The launch is a retry the issue's daily budget pays for like any fresh spawn,
so a spent budget takes its retry-cap park instead (`admits`). What it pays is
staged on the reading the circuit writes the launch's lifetime charge over
(`pays`, through `run_charge_state.OwedLaunch.pays`), so the two land in one
write rather than leaving the daily slot to the run's disposition: a
correction a hold, an interruption, or an unresolved accounting keeps from any
whole-state write of its own still counts it, through the next tick's
recovery. A charge reserved and never started -- refused at its start, or
behind a write nobody confirmed -- has paid its daily retry with it, so the
tick that starts it charges the daily budget nothing more, in whatever window
it starts.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    retry_budget as _retry_budget,
    retry_ledger as _retry_ledger,
    run_ledger as _run_ledger,
    run_requests as _run_requests,
)
from orchestrator.workflow.stages.decomposition import correction_source as _source

log = logging.getLogger("orchestrator.workflow")


def admits(gh: GitHubClient, issue: Issue, state: PinnedState, request: _run_requests._AgentRunRequest) -> bool:
    """Whether `request`'s launch may go on to its charge, the retry-cap park taken where the daily budget refuses it.

    A reservation of this very launch standing unstarted paid its daily retry
    in its own write, so it is admitted as it stands, charged nothing more.
    """
    if _run_ledger._read_ledger(state).pending_for(request.fingerprint):
        return True
    if _retry_budget._charge_or_park(gh, issue, state, stage=_source.STAGE):
        return True
    gh.write_pinned_state(issue, state)
    return False


def pays(issue_number: int, reading: PinnedState) -> bool:
    """Stage the daily retry the launch pays on `reading`, the one its charge is written over; whether one is left.

    Decided again on that reading rather than carried from the caller's: a
    slot another road spent, or a park it took, since the caller read the
    comment refuses the charge with nothing written, and the caller's own
    reading decides the park on a later tick.
    """
    if _retry_ledger._consume_retry_slot(reading, stage=_source.STAGE).allowed:
        return True
    log.info(
        "issue=#%d its daily retry budget reads spent where its manifest correction is charged; charging nothing",
        issue_number,
    )
    return False
