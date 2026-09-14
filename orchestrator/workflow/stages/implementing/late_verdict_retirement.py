# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Retire a measured or superseded generation inside the close-observation window.

A close before the retirement marks the current generation cancelled. A
close inside the pinned write reinstates that generation cancelled, leaving
the cleanup path a durable cycle to end before any publication can proceed.
"""
from __future__ import annotations

import logging
from dataclasses import replace

from orchestrator.workflow.engine import (
    observations as _observations,
    retiring_cycles as _retiring_cycles,
    usage as _usage,
)
from orchestrator.workflow.late_split import (
    endings as _endings,
    events as _events,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.phases import LatePhase
from orchestrator.workflow.stages.implementing import (
    late_approval_state as _late_approval_state,
    late_gate_models as _late_gate_models,
    late_park_notices as _late_park_notices,
)

log = logging.getLogger("orchestrator.workflow")



def _superseded(gate: _late_gate_models._Gate, recorded: LateGeneration) -> bool:
    """Drop a record this publication is going past, and publish without it.

    Two roads reach it and they are the same fact. With the switch off a fresh
    candidate does not enter the gate, so the record it supersedes describes a
    commit nothing is going to publish. And an exemption is the same shape one
    step over: the commit an authorized settlement accepted publishes without being
    measured, so a generation recorded over some OTHER candidate is a record
    about work this issue has moved past.

    Leaving either would freeze the branch out of the ordinary base refresh
    for as long as the issue lives, and carry a live-looking cycle into the
    stages that close the issue -- where the guard that ends one on a close
    reads it as still running. An issue that never entered the gate has
    nothing to drop and is left exactly as it was.

    True is a close that ended the cycle instead, which the caller reads the
    same way `_accepted` does: nothing is published.
    """
    if not recorded.is_present:
        return False
    log.info(
        "issue=#%d is publishing past recorded candidate %s without measuring "
        "it; retiring cycle %d rather than leaving it over work nobody is "
        "publishing",
        gate.issue.number, recorded.candidate_sha, recorded.cycle_id,
    )
    return _retired(gate, recorded)


def _retired(
    gate: _late_gate_models._Gate, generation: LateGeneration, owed: tuple = (),
) -> bool:
    """Drop this generation durably, BEFORE the publication it licenses.

    The write is the point, and it is one the caller cannot defer. What
    follows a retirement is `_on_commits`, which pushes a branch, opens a pull
    request, and moves the label to `workflow:validating` -- and the pinned
    write that would have carried the retirement comes after all of it. A tick
    that died in that window would leave a published pull request under
    `validating` over a generation that still says `measuring`: the branch
    frozen out of the base refresh for good, and a close on that issue read by
    the cancellation guard as a live cycle to end.

    So the record is dropped first and the effects follow it. The cost is one
    pinned write per candidate that publishes; what it buys is that no window
    exists in which the issue has moved on and its record has not.

    True is the answer that stops the publication: a close ended this cycle
    instead, so nothing may be pushed, opened, or handed to review on an issue
    nobody wants. It is asked in the two places a retirement can lose one. The
    latch is one -- a poll observed the close and could hand the reading to no
    worker, so no request of this tick's would show it. The retirement WRITE
    is the other and the subtler: it takes the cycle identity off the record,
    and everything that decides what a close is worth reads that identity, so
    a poll landing inside it finds an issue with nothing to end and drops the
    observation. The window advertises the cycle for exactly as long as the
    write runs, and what it saw is decided as it closes -- under the lock that
    closes it, so no interval is left for a reading to arrive unreported.

    A reading the window caught is answered by putting the generation BACK.
    It is still in this call's own memory, which is what makes that possible:
    it goes back exactly as it was and is cancelled from there, so what the
    ending reads is the cycle that actually ran rather than a refusal with no
    record under it. There is nothing to take back either -- the retirement
    runs ahead of every effect it licenses, so nothing has been published.
    """
    if _cancelled(gate, generation):
        return True
    retiring = _retiring_cycles.retiring(
        gate.spec.slug, gate.issue.number, generation.cycle_id,
    )
    with retiring.held():
        _late_state.clear_late_generation(gate.state)
        _endings.record_retired_cycle(gate.state, generation.cycle_id)
        # What an APPROVAL still owes its route, put back inside the same
        # write that dropped the generation carrying it. Empty for every
        # other retirement: a superseded or adjudicated generation's
        # obligations belong to a candidate nothing is going to publish.
        _late_state.write_late_spends(gate.state, owed)
        gate.gh.write_pinned_state(gate.issue, gate.state)
    if not retiring.observed:
        return False
    log.warning(
        "repo=%s issue=#%d was observed closed inside the write retiring "
        "cycle %d; putting it back so the cancellation has something to end",
        gate.spec.slug, gate.issue.number, generation.cycle_id,
    )
    _marked(gate, generation)
    return True


def _cancelled(gate: _late_gate_models._Gate, generation: LateGeneration) -> bool:
    """End this cycle where a close is already latched against the issue.

    Asked before the retirement rather than after, because the retirement is
    what makes the reading unanswerable: once the identity is off the record
    there is no cycle for the ending to be entered from, and the receipt a
    poll left on the thread has nothing to be adopted against.

    The mark is durable before it is reported, and it is the same mark the
    adjudication's own barriers write -- the cleanup that settles a cancelled
    cycle reads this record and cannot tell which barrier put it there.
    """
    if not generation.is_present or generation.cancelled:
        return False
    if not _observations.close_observed(gate.spec.slug, gate.issue.number):
        return False
    log.warning(
        "repo=%s issue=#%d was observed closed as its measured candidate was "
        "about to publish; ending cycle %d rather than pushing a branch and "
        "opening a pull request on an issue nobody wants",
        gate.spec.slug, gate.issue.number, generation.cycle_id,
    )
    _marked(gate, generation)
    return True


def _marked(gate: _late_gate_models._Gate, generation: LateGeneration) -> None:
    """Record this cycle cancelled, then report it, in that order.

    Nothing is owed a publication on a cancelled cycle, so the commit an
    approval had recorded goes with it -- including one this very call is
    reinstating a generation over. Left standing it would freeze the branch
    out of the base refresh for as long as the issue lives and park a later
    tick asking for a checkout back for work nobody is going to push.
    """
    cancelled = replace(
        generation.cancel(_usage._now_iso()),
        phase=LatePhase.CANCELLING,
        owner_check_pending=False,
    )
    _late_approval_state._forget_approval(gate.state)
    _late_state.write_late_generation(gate.state, cancelled)
    _endings.clear_retired_cycle(gate.state)
    gate.gh.write_pinned_state(gate.issue, gate.state)
    _late_park_notices._emit(
        gate, cancelled,
        _events.LateEvent(family=_events.LateEventFamily.CANCELLATION),
    )
