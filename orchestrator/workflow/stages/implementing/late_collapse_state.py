# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Persist and read the pre-rewrite head, base, and count before a destructive reset.

A failed pinned write restores the caller's in-memory state and refuses
the rewrite. The claim stays until the publication handoff or a proved
rollback clears it in its own durable write.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from orchestrator.workflow.late_split import (
    collapses as _collapses,
    formats as _formats,
)
from orchestrator.workflow.stages.implementing import (
    late_gate_models as _late_gate_models,
)

log = logging.getLogger("orchestrator.workflow")



@dataclass(frozen=True)
class _Collapsed:
    """What the plan taken before the reset says this squash replaced.

    The two facts the rewrite destroys and nothing past it can recover: the
    head that was replaced, and the merge base it was read over. They travel
    together because they are one reading -- the plan takes both while the
    branch is still intact -- and as a record rather than as two arguments so
    the seam that hands them over cannot transpose them.

    Empty for a caller with no plan behind it, which is what a squash the
    switch kept out of the gate has: nothing is measured there and no transfer
    is decided, so there is no before-state for either to be about.
    """

    head: str = ""
    base_sha: str = ""


def _records_the_collapse(
    gate: _late_gate_models._Gate, head: str, base_sha: str, count: int,
) -> str:
    """Say what this squash is about to collapse, durably, before it does.

    The one write that has to happen while the branch can still describe
    itself. A squash replaces the commits a reviewer approved with a single
    object carrying the same tree, so past the reset the head it replaced is
    off the branch, the count is gone with the commits it counted, and what is
    left looks exactly like a branch nobody ever squashed. A process that dies
    in that window comes back to a one-commit branch, a remote still standing
    on the head it replaced, and nothing on the comment saying a rewrite was
    begun -- and the retry takes the nothing-to-rewrite road and reports
    success without measuring or pushing anything. A branch of one commit
    rewritten for its subject leaves exactly that too, and leaves it without
    even a change of shape to notice.

    So the terms go down first. They are what a later tick tells an
    interrupted rotation from a finished one BY, and they are the whole of
    what it may take on trust: everything else the resumed publication needs
    is asked again of the world it is about.

    A write GitHub refuses is answered by NOT rewriting. The staged payload is
    put back exactly as it was found and the caller is handed the reason, so
    the approved commits stay on the branch and the next tick squashes them
    afresh -- rather than a collapse being made that nothing on the comment
    could ever account for.

    Answers with the refusal, or "" where the terms are durable.
    """
    before = dict(gate.state.data)
    try:
        _collapses.record_pending_collapse(
            gate.state, head=head, base_sha=base_sha, count=count,
        )
    except _formats.InvalidLateValue as refused:
        return f"the squash could not be recorded before it ran ({refused})"
    try:
        gate.gh.write_pinned_state(gate.issue, gate.state)
    except Exception:
        log.warning(
            "issue=#%d could not record the squash it was about to make of "
            "%s; leaving the approved commits on the branch",
            gate.issue.number, head, exc_info=True,
        )
        gate.state.data.clear()
        gate.state.data.update(before)
        return "the squash could not be recorded before it ran"
    return ""


def _claims_a_collapse(state) -> bool:
    """Whether this comment claims a squash somebody may not have finished.

    Presence rather than readability, which is the difference the caller acts
    on: a comment carrying no claim has nothing to recover, and one carrying a
    claim this build cannot read has a branch nobody can account for. Read
    through the fail-closed reader alone, the second would be waved past as
    the first -- and the branch it is about is the one that looks like it has
    nothing to squash.

    It is also what a failure asks before it words a human's notice: an issue
    still claiming a collapse is one whose branch may be standing on the
    rewrite rather than on the commits a reviewer approved.
    """
    return _collapses.carries_pending_collapse(state)


def _recorded_collapse(state) -> _collapses.LateCollapse | None:
    """The squash this issue began and may not have finished, or None."""
    return _collapses.read_pending_collapse(state)


def _forgets_the_collapse(state) -> None:
    """Drop the record of a squash nothing is waiting on any more.

    Staged rather than persisted, and every caller of it has a durable write
    of its own behind it: the reset a rollback made, the reset that never ran,
    the fresh terms the next squash records, and the write the approval handoff
    makes once its notice has gone out. A process dying before one of those
    comes back to a record still standing over a branch the recovery reads
    again and answers the same way -- an already-published collapse is
    finished a second time as the leased no-op it is, and an untouched branch
    is squashed afresh.

    Taken over the pinned STATE rather than over a gate, because the owner
    that finally drops one is the stage handoff, which has no candidate to
    build a gate around: past the push there is nothing left to decide about.
    """
    _collapses.clear_pending_collapse(state)


def _collapse_of(
    head: str, base_sha: str, count: int,
) -> _collapses.LateCollapse:
    """The three facts a squash destroys, as the record every owner holds one.

    Built here rather than by the caller that took them, so the plan a fresh
    squash makes and the record a resumed one reads back are the same shape
    all the way down: the head that is being replaced, the base it is
    rewritten over, and how many commits go in. The publication tail past the
    reset is handed one of these whichever of the two produced it, and nothing
    below has to know which -- or how much history the rewrite replaced.
    """
    return _collapses.LateCollapse(
        head=head, base_sha=base_sha, count=count,
    )
