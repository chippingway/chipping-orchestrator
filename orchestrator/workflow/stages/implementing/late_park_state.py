# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist measurement generations and account for the park and command they own.

A new candidate retires the old measurement park before its generation
and route spends become durable. Spending a held authorization advances
the command watermark monotonically.
"""
from __future__ import annotations

import logging

from orchestrator.github import (
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    models as _late_models,
    payloads as _payloads,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    late_measurement_state as _late_measurement_state,
    late_park_retirement as _late_park_retirement,
    state as _state,
)

log = logging.getLogger("orchestrator.workflow")



def _recorded_candidate(state: _pinned_state.PinnedState) -> str:
    """The commit this issue's record names, or "" where none does.

    Published for the disposition beside this owner, which needs the floor a
    park left on the branch: commits already there when a resumed run started
    are not that run's, and reading them as its own would publish work an
    agent's clarifying question was asked INSTEAD of.
    """
    return _late_state.read_late_generation(state).candidate_sha


def _spends_a_held_reading(state: _pinned_state.PinnedState) -> None:
    """Consume the thread to the boundary a publication handoff staged.

    The other half of what an authorization handoff leaves in flight, and it
    is spent HERE -- in the write that ends this stage's hold on the issue --
    for the reason the park beside it is dropped here. Past that write nothing
    under the new label spends what implementing left behind and this stage
    never sees the issue again, so a boundary applied after the call is one a
    crash in that window loses for good.

    What it answers is a command the seam published on without ever reading
    the thread: a candidate the ceiling now lets through settles on its own
    count, and one an authorization already on the record covers publishes as
    decided. Neither consumes the reply that ended the park, and a reply left
    above the watermark is read on the next stage as somebody's fresh
    feedback -- a developer paid to answer a command nothing there can act on,
    over an implementation that is already published.

    Never past what that reading LOOKED at, which is what the boundary
    records: a tick consuming past whatever the tip has become since would
    swallow a reply posted in between, a retraction of the very command being
    published on included.

    Dropped whether it was spent or not. A boundary already behind the
    watermark is one the seam consumed for itself on the road that reads the
    thread, and one left standing would be applied to whatever this issue
    parks over next.
    """
    boundary = _payloads.as_identity(state.get(_state._HELD_COMMAND))
    state.set(_state._HELD_COMMAND, None)
    if boundary is None:
        return
    reached = _payloads.as_identity(
        state.get(_state._LAST_ACTION_COMMENT_ID),
    ) or 0
    if boundary <= reached:
        return
    log.info(
        "issue candidate published under an authorization the seam never "
        "read; consuming the thread to %d so the command is not taken for "
        "fresh feedback on the stage this issue moves to", boundary,
    )
    state.set(_state._LAST_ACTION_COMMENT_ID, boundary)


def _persisted(
    gate: _late_gate_models._Gate, generation: _late_models.LateGeneration,
) -> None:
    """Write the generation this step reached, and the state around it.

    What the caller's hold owes rides the same write, because the freeze is
    durable and the count that follows it is not: a tick that dies in between
    leaves a pair for the reconciliation ahead of the next handler to answer,
    and that tick has no run behind it to re-derive a reviewer round, a
    cleared bookmark, or a stage tail from. Written after the generation and
    inside its own key group, so the retirement that ends the pair drops it in
    the same write.

    Only while the pair still AWAITS its count, which is exactly the window it
    pays for. A record carrying a number has been answered -- the routed hold
    that carries it spent this on the way past -- and rewriting it there would
    leave a spent claim on the comment for a later reader to apply twice.

    A measurement park the new record moves PAST goes out in this same write,
    because the two are read as one afterwards: a later tick asks whether the
    park standing is the one this pair was parked for, and answers by
    comparing it against the recorded candidate. Left to the verdict alone,
    the window between this write and that one is a crash away from a park
    taken over one commit sitting beside a record naming another -- which the
    next tick reads as that pair's own, holding every later reading of it
    silently, counting none of them, and never reaching the notice a human is
    owed. Bound here, the comment can never say two things at once.
    """
    _unbound_park(gate.state, generation)
    _late_state.write_late_generation(gate.state, generation)
    if generation.additions is None:
        _late_state.write_late_spends(gate.state, gate.spends.fields)
    gate.gh.write_pinned_state(gate.issue, gate.state)


def _unbound_park(
    state: _pinned_state.PinnedState, generation: _late_models.LateGeneration,
) -> None:
    """Retire a measurement park the record being written moves past.

    Only a park over some OTHER candidate: one taken over the pair still being
    written is exactly the park that has to survive, since the reading it was
    taken for still has not happened. A record that names no candidate at all
    is no claim about which pair is parked, so it leaves the park alone.
    """
    if not generation.candidate_sha:
        return
    if state.get(_state._PARK_REASON) != _late_measurement_state.PARK_MEASUREMENT_FAILED:
        return
    if _late_state.read_late_generation(state).candidate_sha == (
        generation.candidate_sha
    ):
        return
    _late_park_retirement._retire_spent_park(state)
