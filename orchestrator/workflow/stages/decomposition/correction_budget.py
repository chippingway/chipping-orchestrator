# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The daily retry a manifest correction's launch pays, charged in the write that reserves its run.

The launch is a retry the issue's daily budget pays for like any fresh spawn,
so a spent budget takes its retry-cap park instead (`admits`). What it pays is
staged on the reading the circuit writes the launch's lifetime charge over
(`pays`, through `run_charge_state.OwedLaunch.pays`), so the two land in one
write rather than leaving the daily slot to the run's disposition: a
correction a hold, an interruption, or an unresolved accounting keeps from any
whole-state write of its own still counts it, since the comment carries it
beside the charge. A charge reserved and never started -- refused at its start, or
behind a write nobody confirmed -- has paid its daily retry with it, so the
tick that starts it charges the daily budget nothing more, in whatever window
it starts.
"""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from functools import partial

from github.Issue import Issue

from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import (
    record_admission as _record_admission,
    retry_budget as _retry_budget,
    retry_ledger as _retry_ledger,
    run_ledger as _run_ledger,
    run_requests as _run_requests,
)
from orchestrator.workflow.stages.decomposition import correction_source as _source

log = logging.getLogger("orchestrator.workflow")


def admits(
    gh: GitHubClient,
    issue: Issue,
    state: PinnedState,
    request: _run_requests._AgentRunRequest,
    still: Callable[[], bool],
) -> bool:
    """Whether `request`'s launch may go on to its charge, the retry-cap park taken where the daily budget refuses it.

    A reservation of this very launch standing unstarted paid its daily retry
    in its own write, so it is admitted as it stands, charged nothing more.
    The budget is asked of a copy of `state`, so an admitted launch stages
    nothing on the caller: what it pays is staged with its charge (`pays`)
    and laid back only once that write lands. A refused one takes its
    retry-cap park, and the write settling its notice, only over the comment
    `state` last synced with and only while the issue `still` stands,
    immediately before each edit leaves (`record_admission.strictly_written`),
    and posts that notice only where both still stand behind its thread's
    read (`record_admission.stands`): a hold, or a comment moved -- a session pinned or the
    park cleared while the issue was being read -- parks over and announces
    nothing, a moved comment withholding `state`.
    """
    if _run_ledger._read_ledger(state).pending_for(request.fingerprint):
        return True
    trial = PinnedState(state_data=copy.deepcopy(state.state_data))
    if _retry_ledger._consume_retry_slot(trial, stage=_source.STAGE).allowed:
        return True
    guard = _retry_budget.ParkGuard(
        writes=partial(_record_admission.strictly_written, still=still),
        posts=partial(_record_admission.stands, gh, issue, state, still),
    )
    _retry_budget._charge_or_park(gh, issue, state, stage=_source.STAGE, guard=guard)
    if not state.withheld:
        _record_admission.strictly_written(gh, issue, state, still=still)
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
