# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read measurement-park ownership and update notice and quiet-retry coordinates.

Only transport failures consume quiet retries. A matching held park keeps
its notice ownership, and a successful reading clears its miss count while
a completed measurement also clears the recorded failure.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.measurement.models import MeasurementFailure
from orchestrator.github import (
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    models as _late_models,
    state as _late_state,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
    state as _state,
)

PARK_MEASUREMENT_FAILED = "late_measurement_failed"

# The steps a lost reading is retried quietly for, and the only two. Both name
# the transport between this host and the base -- a remote that would not
# answer for the branch, and a fetch that did not bring the object back -- and
# a transport fault is the one thing in this vocabulary that clears itself
# while nobody is watching. Every other member names something a second
# reading cannot change: a candidate this host does not hold, a diff nothing
# here can pin. Re-reading those buys the same answer, so they park on the
# first miss and ask a human for the one thing that would change it.
_TRANSPORT_STEPS = frozenset((
    MeasurementFailure.BASE_UNREADABLE,
    MeasurementFailure.BASE_ABSENT,
))


def _stands_over(
    gate: _late_gate_models._Gate, generation: _late_models.LateGeneration,
) -> bool:
    """Whether a human is still waiting on a notice about THIS pair.

    The pair has to be the one the park was taken over, read off the pinned
    record, since a candidate the branch has moved past is work that park was
    never about -- the fresh start owes its own bounded retry rather than
    inheriting one already spent.

    Past that the question is which park this call is standing under, and
    there are two answers because there are two roads in. On the ordinary one
    the park is the record's own: the LATCH says somebody is still waiting,
    not the reason beside it, since a resume consumes the latch and leaves the
    reason standing, and a human who answered with guidance has spent the
    notice they were sent rather than still being owed it.

    The other is a handoff made UNDER a park, and there the flags cannot
    answer at all: the park held across the call is put back after it whatever
    the seam refused for, so a measurement park taken in here never survives
    the tick that took it. What does survive is the member the notice named,
    which is written by the two roads that tell somebody and by nothing else
    -- so under a held park that is the whole of the question, and the
    operator waiting behind the park being restored is the human still owed
    nothing further.
    """
    recorded = _late_state.read_late_generation(gate.state)
    if recorded.candidate_sha != generation.candidate_sha:
        return False
    if _under_a_held_park(gate.state):
        return bool(recorded.measurement_failure)
    if not gate.state.get(_state._AWAITING_HUMAN):
        return False
    return gate.state.get(_state._PARK_REASON) == PARK_MEASUREMENT_FAILED


def _under_a_held_park(state: _pinned_state.PinnedState) -> bool:
    """Whether this call was entered under a park that will be put back.

    Written before the handoff and dropped after it, so it is on the record
    for exactly the calls the rollback covers -- and for the poll after a
    crash inside one, which puts the park back before any gate is entered
    again. One road writes it, under one park: the operator authorization an
    adjudicated candidate is waiting for.
    """
    held = state.get(_state._HELD_PARK)
    return isinstance(held, dict) and bool(held.get(_state._AWAITING_HUMAN))


def _announced(
    generation: _late_models.LateGeneration, failure,
) -> _late_models.LateGeneration:
    """The record a notice naming this step leaves behind.

    The field is what the thread has been TOLD, so it is written by the two
    roads that tell somebody and by nothing else. Read that way it answers the
    only question the retry after it has: does the sentence already on this
    issue cover the step this reading stopped at?
    """
    return replace(generation, measurement_failure=failure)


def _one_more_miss(
    generation: _late_models.LateGeneration, failure,
) -> _late_models.LateGeneration:
    """The record one lost reading leaves, where the bound counts it.

    A step outside the bound is handed on untouched. The count is what says
    how close this pair is to being handed to a human, so a failure nothing
    retries may not spend one of the readings a transport fault is owed.

    The count and nothing beside it. What a quiet miss stopped at is said to
    the log and to both streams and to no human at all, and the member on the
    record is the one a human was TOLD -- so writing this reading's step there
    would leave the announce-once guard reading a notice nobody made.
    """
    if failure not in _TRANSPORT_STEPS:
        return generation
    return replace(
        generation,
        measurement_miss_count=generation.measurement_miss_count + 1,
    )


def _retries_quietly(missed: _late_models.LateGeneration, failure) -> bool:
    """Whether this miss is one the next tick takes again without a human."""
    return (
        failure in _TRANSPORT_STEPS
        and missed.measurement_miss_count
        <= _state._MEASUREMENT_MISSES_BEFORE_PARK
    )


def _reached(
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """The record a base this host really holds leaves: no miss outstanding.

    A freeze that succeeded is what the count exists to be ended by, and the
    end has to be recorded rather than assumed. Carried past it, readings lost
    to a transport that has since recovered would be spent on the next fault
    instead: a pair that lost three of them and then measured would hand the
    issue to a human on the first hiccup after that.

    The count and only it. Reaching the base is not the end of the steps a
    reading can stop at -- the diff still has to be pinned, taken and read --
    and the member beside the count is what a NOTICE named, so dropping it
    here would lose the record of what a human was told on the very tick that
    reaches the base, and the diff failure behind it would be announced afresh
    on every poll for as long as the base stayed reachable. `_measured` is
    where it goes, once the reading it describes has actually happened.
    """
    return replace(generation, measurement_miss_count=0)


def _measured(
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """The record a reading that HAPPENED leaves: nothing outstanding at all.

    The end of every step a measurement can stop at, which is the first point
    a member on this record describes a refusal that is over. So it goes here,
    before the verdict settles on the record -- and the count with it, since
    the same reading ended the row of lost ones.

    Before this and not after: the settlement WRITES this record, and an
    oversized candidate's survives the write to be adjudicated from. Cleared
    afterwards instead, the pinned comment would carry a step a human was told
    about into an adjudication where nothing is refusing anything, and the
    announce-once guard would read it as a sentence still standing on a thread
    whose park was retired by this very verdict.
    """
    return replace(
        generation, measurement_miss_count=0, measurement_failure=None,
    )
