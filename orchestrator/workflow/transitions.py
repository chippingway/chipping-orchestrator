# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Declare the workflow transition graph and its publication and base-refresh stage sets.

The forward spine and explicit interrupt sources share the same label
vocabulary. Publication and refresh eligibility read those exact stage sets
so the graph and the rewrite evidence cannot disagree.
"""
from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from orchestrator.workflow.state import WorkflowLabel

_DETOUR_TO_RESOLVING: frozenset[WorkflowLabel] = frozenset(
    (
        WorkflowLabel.VALIDATING,
        WorkflowLabel.DOCUMENTING,
        WorkflowLabel.IN_REVIEW,
        WorkflowLabel.FIXING,
    ),
)

# The states a candidate the remote ALREADY carries can be measured from:
# every one that pushes onto an open pull request -- the reviewer's own fix
# loop, the human one, the body-edit resume an open PR takes, the conflict
# rebase's, and the final documentation pass. The size gate holds an oversized
# one off the pull request and hands the issue to the same adjudication an
# unpublished candidate gets, so each of them owes the edge `implementing`
# already has -- and owes it for the label a human moved by hand too, which
# the relabel guard puts back on `decomposing` from wherever it landed.
_ENTER_ADJUDICATION_PUBLISHED: frozenset[WorkflowLabel] = frozenset(
    (
        WorkflowLabel.VALIDATING,
        WorkflowLabel.DOCUMENTING,
        WorkflowLabel.IN_REVIEW,
        WorkflowLabel.FIXING,
        WorkflowLabel.RESOLVING_CONFLICT,
    ),
)

_FORWARD: Mapping[
    WorkflowLabel | None, frozenset[WorkflowLabel]
] = MappingProxyType({
    None: frozenset((WorkflowLabel.DECOMPOSING, WorkflowLabel.IMPLEMENTING)),
    # The published states are the size gate's way BACK. An adjudication
    # entered on work the remote already carries settles at the stage it was
    # taken out of, because that stage is the only owner of the completion the
    # candidate still owes -- the docs watermark and its `in_review` handoff,
    # a conflict round, another reviewer look. Sending every one of them to
    # `implementing` instead would walk the issue back to a point it had
    # already passed.
    WorkflowLabel.DECOMPOSING: frozenset(
        (
            WorkflowLabel.READY,
            WorkflowLabel.IMPLEMENTING,
            WorkflowLabel.BLOCKED,
            WorkflowLabel.UMBRELLA,
        ),
    ) | _ENTER_ADJUDICATION_PUBLISHED,
    WorkflowLabel.READY: frozenset(
        (WorkflowLabel.IMPLEMENTING, WorkflowLabel.DECOMPOSING),
    ),
    WorkflowLabel.BLOCKED: frozenset(
        (WorkflowLabel.READY, WorkflowLabel.DECOMPOSING),
    ),
    WorkflowLabel.UMBRELLA: frozenset(
        (WorkflowLabel.DONE, WorkflowLabel.DECOMPOSING),
    ),
    # `decomposing` is the late gate's edge: a clean committed candidate
    # measured past the size threshold is adjudicated before anything is
    # pushed, and the adjudication runs under the decomposing label rather
    # than a state of its own.
    WorkflowLabel.IMPLEMENTING: frozenset(
        (WorkflowLabel.VALIDATING, WorkflowLabel.DECOMPOSING),
    ),
    WorkflowLabel.VALIDATING: frozenset(
        (WorkflowLabel.DOCUMENTING, WorkflowLabel.FIXING),
    ),
    WorkflowLabel.DOCUMENTING: frozenset(
        (WorkflowLabel.IN_REVIEW, WorkflowLabel.VALIDATING),
    ),
    WorkflowLabel.IN_REVIEW: frozenset(
        (WorkflowLabel.FIXING, WorkflowLabel.VALIDATING),
    ),
    WorkflowLabel.FIXING: frozenset(
        (
            WorkflowLabel.VALIDATING,
            WorkflowLabel.RESOLVING_CONFLICT,
            WorkflowLabel.IN_REVIEW,
        ),
    ),
    WorkflowLabel.RESOLVING_CONFLICT: frozenset((WorkflowLabel.VALIDATING,)),
    WorkflowLabel.QUESTION: frozenset((WorkflowLabel.DONE,)),
    # Nothing routes an issue into `discussion`, so the only edges it needs are
    # its two endings: the design was taken, or it was not. A human applies
    # either by hand, and the stage writes the same two itself once they have
    # decided somewhere it can read -- by merging or closing the plan PR, or by
    # closing the issue before one exists.
    WorkflowLabel.DISCUSSION: frozenset(
        (WorkflowLabel.DONE, WorkflowLabel.REJECTED),
    ),
    WorkflowLabel.DONE: frozenset(),
    WorkflowLabel.REJECTED: frozenset(),
})

_INTERRUPT_SOURCES: Mapping[
    WorkflowLabel, frozenset[WorkflowLabel]
] = MappingProxyType({
    WorkflowLabel.DONE: frozenset(
        (
            WorkflowLabel.IMPLEMENTING,
            WorkflowLabel.VALIDATING,
            WorkflowLabel.DOCUMENTING,
            WorkflowLabel.IN_REVIEW,
            WorkflowLabel.FIXING,
            WorkflowLabel.RESOLVING_CONFLICT,
        ),
    ),
    # The last three are the late gate's cancellation: an issue whose owner is
    # observed closed mid-adjudication finishes its external cleanup and stops
    # there, under whichever label the adjudication had reached --
    # `decomposing` before a split, `umbrella` once one converted it, and
    # `done` for an owner a human moved onto the terminal over a cycle that
    # still has an ending to reach. That last one is the only edge out of a
    # terminal the orchestrator takes. The umbrella's own terminal needs none
    # of it: the write that records the resolution retires the cycle with it,
    # so a close arriving past that write finds nothing left to cancel and
    # nothing is ever left under `done` for a later pass to correct.
    WorkflowLabel.REJECTED: frozenset(
        (
            WorkflowLabel.IMPLEMENTING,
            WorkflowLabel.VALIDATING,
            WorkflowLabel.DOCUMENTING,
            WorkflowLabel.IN_REVIEW,
            WorkflowLabel.FIXING,
            WorkflowLabel.RESOLVING_CONFLICT,
            WorkflowLabel.DECOMPOSING,
            WorkflowLabel.UMBRELLA,
            WorkflowLabel.DONE,
        ),
    ),
    WorkflowLabel.RESOLVING_CONFLICT: _DETOUR_TO_RESOLVING,
    WorkflowLabel.DECOMPOSING: _ENTER_ADJUDICATION_PUBLISHED,
})


def _mutable_forward_transitions(
) -> dict[WorkflowLabel | None, set[WorkflowLabel]]:
    """Copy the forward graph into mutable target sets."""
    return {
        forward_source: set(forward_targets)
        for forward_source, forward_targets in _FORWARD.items()
    }


def _add_interrupt_transitions(
    allowed: dict[WorkflowLabel | None, set[WorkflowLabel]],
) -> None:
    """Fold each target's exact interrupt sources into the graph."""
    for target, sources in _INTERRUPT_SOURCES.items():
        for interrupt_source in sources:
            allowed[interrupt_source].add(target)


def _freeze_transitions(
    allowed: dict[WorkflowLabel | None, set[WorkflowLabel]],
) -> dict[WorkflowLabel | None, frozenset[WorkflowLabel]]:
    """Freeze target sets so the exported graph is immutable."""
    return {
        allowed_source: frozenset(edges)
        for allowed_source, edges in allowed.items()
    }


def build_allowed_transitions(
) -> dict[WorkflowLabel | None, frozenset[WorkflowLabel]]:
    """Compose the forward spine with exact interrupt sources."""
    allowed = _mutable_forward_transitions()
    _add_interrupt_transitions(allowed)
    return _freeze_transitions(allowed)


ALLOWED_TRANSITIONS = build_allowed_transitions()


def publishes_onto_a_pull_request(label: WorkflowLabel | None) -> bool:
    """Whether this stage pushes onto a pull request the remote already has.

    The five the size gate can take an issue out of, named off the same set
    the edges to the adjudication are built from so the two cannot drift.
    Derived instead -- from "has an edge to `workflow:decomposing`" -- it
    would admit `workflow:implementing`, whose own gate routes there too and
    whose approval carries no pull-request head because its push is the one
    that opens the pull request.
    """
    return label in _ENTER_ADJUDICATION_PUBLISHED


def rebased_by_the_base_refresh(label: WorkflowLabel | None) -> bool:
    """Whether the per-tick base refresh drives this stage's own rebase.

    The four states that detour to `workflow:resolving_conflict` when that
    rebase leaves conflicted files, named off the same set those edges are
    built from so the two cannot drift. It is the five above minus
    `workflow:resolving_conflict` itself, which owns its rebase rather than
    being driven through one -- and telling them apart is what says which
    rewrite kind a record naming a rebase may have come from.
    """
    return label in _DETOUR_TO_RESOLVING
