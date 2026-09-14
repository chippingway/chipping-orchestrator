# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The reading one candidate gets, taken fresh or acted on from the record.

The two roads into a count, and they are one owner because they end in the
same place: whatever a candidate's size turns out to be, the verdict is
settled by `late_verdict` and a reading that did not happen is parked by
`late_parks`. What differs is only where the pair came from.

A FRESH reading freezes the pair before it counts. The write goes out carrying
both commits and the `measuring` boundary, so a tick that dies over the diff
comes back to the pair this one froze rather than re-deriving one from a
branch and a remote that have both moved.

A RECORDED one is the other side of exactly that crash, and it is not simply
believed. A count on the pinned comment is one END of a reading whose other
fields say what it means -- without a base there is no pair it was taken over,
without a threshold no ceiling to compare it to, without a whole identity
nothing to join it to afterwards -- and the base it names is proved present
here, because a host that cannot show the object the count was taken against
cannot show the diff a verdict is defended by either.
"""
from __future__ import annotations

from dataclasses import replace

from orchestrator.git.measurement import additions as _additions
from orchestrator.workflow.late_split import events as _events
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.stages.implementing import (
    late_freeze as _freeze,
    late_gate_models as _late_gate_models,
    late_parks as _parks,
    late_verdict as _verdict_owner,
)


def _reconciled_measurement(
    gate: _late_gate_models._Gate, recorded: LateGeneration,
) -> bool:
    """Act on a measurement this issue already took, or park on what is left.

    A count on the record is not on its own a measurement anything may act on.
    It is one END of a reading whose other fields say what it MEANS: without a
    base there is no pair it was taken over, without a threshold there is no
    ceiling to compare it to -- and `is_oversized` answers False on a missing
    one, which is the shape of a damaged record publishing as a small
    candidate -- and without a boundary there is nothing saying which step
    wrote it. Without a whole identity naming THIS issue there is nothing to
    join it to afterwards, or it is somebody else's reading entirely. A record
    short of any of them is repaired by a human or measured again, never read
    as an answer.

    The recorded base is proved present for the same reason it is on the way
    in: a host that cannot show the object the count was taken against cannot
    show the diff a verdict is defended by either, and acting on the number
    while the evidence behind it is missing is the substitution this whole
    contract refuses.

    Both halves are asked by the one proof: a record too damaged to act on and
    a base this host cannot show come back the same way, since neither is a
    reading anything may be settled on. What that proof hands back is what the
    verdict is settled on, rather than the record it was asked about -- a base
    reached after a retry lost readings for it ends that run, and the record
    carrying the end is the one the write behind the verdict has to be made
    from.
    """
    refrozen = _freeze._refrozen_base(gate, recorded)
    if refrozen is None:
        return True
    return _verdict_owner._settled(gate, refrozen)


def _freshly_measured(
    gate: _late_gate_models._Gate, recorded: LateGeneration, candidate_sha: str,
) -> bool:
    """Freeze the pair, count between it, and act on what came back."""
    frozen = _freeze._frozen_pair(gate, recorded, candidate_sha)
    if frozen is None:
        return True
    counted = _additions._count_added_lines(
        gate.worktree, frozen.base_sha, frozen.candidate_sha,
    )
    if not counted.is_measured:
        return _parks._unmeasured(
            gate, frozen, counted.failure, counted.detail,
        )
    measured = replace(frozen, additions=counted.additions)
    _parks._emit(
        gate, measured,
        _events.LateEvent(family=_events.LateEventFamily.MEASUREMENT),
    )
    return _verdict_owner._settled(gate, measured)
