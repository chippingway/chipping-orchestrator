# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Durable late-child walk records, cancellation seals, and ancestry seeding.

The parent records every created issue before the child is seeded. A close
seen inside the child read prevents its write, and a resumed walk seals
only after every possible unrecorded child has been accounted for.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from github.Issue import Issue

from orchestrator.workflow.engine import usage as _usage
from orchestrator.workflow.late_split import (
    formats as _formats,
    lineage as _lineage,
    phases as _late_phases,
)
from orchestrator.workflow.late_split.models import LateFailure, LateResource, LateResourceKind, LateResourceState
from orchestrator.workflow.stages.decomposition import (
    late_child_content as _late_child_content,
    late_outcome as _late_outcome,
    late_owner as _late_owner,
    late_park_state as _late_park_state,
    late_parks as _late_parks,
    state as _state,
)
from orchestrator.workflow.stages.decomposition.late_models import _LateContext
from orchestrator.workflow.stages.decomposition.models import _SplitPlan

log = logging.getLogger("orchestrator.workflow")


_EXPECTED_CHILDREN = "expected_children_count"

_DEP_GRAPH = "dep_graph"

_CHILD_CREATE_PARK = (
    "the committed candidate for this issue was adjudicated as a split and "
    "its snapshot is safe, but {child} could not be created, recorded, or "
    "seeded. The snapshot ref and every child already created are recorded on "
    "this issue; the next tick adopts them and continues from the same "
    "manifest without re-running any agent."
)


@dataclass
class _ChildWalk:
    """One pass over a split manifest, and what the parent already records.

    `known` is read once, before the walk, and never again: it is both the
    register a resumed pass adopts from and the floor its writes may not go
    below. Re-reading it per child would read the walk's own partial write --
    the second index would find only the first child recorded, decide the
    slice it is on has none, and create a duplicate beside the one that
    exists.
    """

    plan: _SplitPlan
    known: tuple[int, ...]
    snapshot_ref: str
    resumed: bool

    # Whether no child of this generation exists that the register does not
    # name. True from the start of a walk nobody resumed -- no earlier attempt
    # could have created anything -- and set once this one has passed the
    # first UNRECORDED index: to have created the index after that, an earlier
    # attempt would have had to record this one, and it did not. Until then a
    # resumed walk cannot say it, which is what keeps a create-before-record
    # crash from being sealed over.
    orphans_ruled_out: list[bool] = field(default_factory=list)

    def past_the_unrecorded(self) -> None:
        """Say the first index no attempt had recorded has been answered."""
        self.orphans_ruled_out.append(True)

    @property
    def every_child_is_recorded(self) -> bool:
        """Whether the register names every child this generation made."""
        return not self.resumed or bool(self.orphans_ruled_out)

    def recorded_numbers(self) -> tuple[int, ...]:
        """The children this generation records once this step is durable.

        Monotonic on purpose. What the walk has placed so far, extended by
        whatever the previous pass recorded beyond it, so a crash in the
        middle of a resumed pass can never leave the parent knowing about
        fewer children than exist on GitHub.
        """
        placed = tuple(number for number, _ in self.plan.created)
        return placed + self.known[len(placed):]


def _sealed(context: _LateContext, walk: _ChildWalk) -> None:
    """Close the consumer ledger of a split a CANCELLATION stopped.

    The count this transaction wrote before its first create is what tells a
    partial split from a finished one, and a cancelled loop can never reach
    it: the children it did not make are ones nothing is ever going to make.
    Left unsealed, the ref those children were cut from is one no pass could
    release -- every consumer could end and the proof would still be short of
    the count -- so the owner would hold a snapshot and its terminal forever.

    What makes the ledger final rather than short is the cancellation itself.
    Every exit that reaches here with the mark down is one where the child in
    hand was already RECORDED: the create, the record, and the seed are three
    steps in that order, and each barrier between them is asked after the
    write that names the child. So the register accounts for every child that
    exists, and no further one will ever be opened.

    Except where an EARLIER attempt could have created one this walk has not
    reached: a create is a request and the write recording it is another, so a
    pass that died between them left a child on GitHub with nothing naming it.
    That is what the adoption lookup answers, and until this walk has passed
    the first unrecorded index a resumed one cannot say it -- so it does not,
    and the ref stays held on the count exactly as before.

    Written as the CYCLE it is a fact about, not as a flag. Nothing that ends
    a generation drops this key, so a seal left saying only "yes" would be
    read by the next cycle on the same issue as proof about a register it
    never wrote -- and a later split stopped mid-loop, on a resumed walk that
    seals nothing of its own, would release the ref its unrecorded children
    were cut from.

    Written once, and only over a record that does not already say it.
    """
    if not context.generation.cancelled:
        return
    if not walk.every_child_is_recorded:
        log.info(
            "issue=#%d was cancelled mid-split on a resumed walk; leaving "
            "its consumer ledger open, since a child an earlier attempt "
            "created and never recorded would not be on it",
            context.issue.number,
        )
        return
    cycle = context.generation.cycle_id
    if _state._ledger_is_sealed(
        context.state.get(_state._SPLIT_LEDGER_SEALED), cycle,
    ):
        return
    log.warning(
        "issue=#%d was cancelled with %d of %s children made; sealing cycle "
        "%d's consumer ledger, since the rest are children nothing will "
        "create",
        context.issue.number, len(walk.recorded_numbers()),
        context.state.get(_EXPECTED_CHILDREN), cycle,
    )
    context.state.set(_state._SPLIT_LEDGER_SEALED, cycle)
    _late_park_state._persist(context)


def _prepared(context: _LateContext, manifest: tuple) -> None:
    """Force this issue to be an umbrella, before a single child exists.

    Both fields are what a tick that died mid-loop is read back through: the
    count tells a partial split from a finished one, and the umbrella flag
    says the parent has no implementation of its own to return to. A split
    that recorded neither would leave a parent nobody could finish.

    The flag rather than the label. The label is the last thing this
    transaction writes, because a live generation pins `workflow:decomposing`
    and an issue relabelled ahead of its own retirement is one the guard puts
    straight back.
    """
    context.state.set(_EXPECTED_CHILDREN, len(manifest))
    context.state.set(_state._UMBRELLA, True)
    context.generation = replace(
        context.generation, phase=_late_phases.LatePhase.SPLITTING,
    )
    _late_park_state._persist(context)


def _recorded(
    context: _LateContext,
    walk: _ChildWalk,
    index: int,
    child_issue: Issue,
    child: dict,
) -> bool:
    """Record this child as a child, a consumer, and an obligation, at once.

    One write, because the three say the same thing to different readers: the
    parent's walk drives the tree, the consumer ledger is what decides whether
    the snapshot may ever be reclaimed, and the obligation entry is what a
    cleanup asks GitHub about. A child recorded as one and not the others is a
    child the snapshot would stop waiting for.

    It is also the durable step that has to precede activation, which is why
    it is here rather than folded into the final write: a runnable child whose
    slot the ledger never took is one a reclamation could delete the snapshot
    out from under.
    """
    walk.plan.record(index, child_issue.number, child)
    try:
        owed = context.generation.with_consumers(
            (child_issue.number,),
        ).with_resource(LateResource(
            kind=LateResourceKind.CHILD,
            target=str(child_issue.number),
            resource_state=LateResourceState.PENDING,
        ))
    except _formats.InvalidLateValue:
        log.exception(
            "issue=#%d cannot record child #%d on its ledgers",
            context.issue.number, child_issue.number,
        )
        _parked(context, f"child #{child_issue.number} ({child.get('title')!r})")
        return False
    recorded = walk.recorded_numbers()
    context.generation = replace(
        owed.with_split_children(recorded), phase=_late_phases.LatePhase.SPLITTING,
    )
    # The stage's own list is written FROM the register rather than appended
    # to, so an earlier decomposition's children and dependency graph are
    # replaced by this generation's rather than left standing over them.
    context.state.set(_state._CHILDREN, list(recorded))
    context.state.set(_DEP_GRAPH, walk.plan.dep_graph or None)
    _late_park_state._persist(context)
    return True


def _seeded(
    context: _LateContext,
    walk: _ChildWalk,
    child_issue: Issue,
    child: dict,
) -> bool:
    """Give this child its parent link, its stamp, and its ancestry.

    The child's own state is read and added to rather than written fresh, for
    the case this step exists to repair: a retry reaches a child that was
    already created, and by then it may be implementing. Writing a fresh
    record over it would take its work with it.

    False is either of the two ways this child is the last one: a write that
    could not be made, which parks, and the cancellation a close latched
    inside the read earned, which is on the record already. Both stop the
    loop where it stands, and the cancellation has to -- reporting success
    would let the loop go on opening real issues against an ended cycle, and
    would leave the barriers behind it marking a cancellation that is already
    marked.
    """
    try:
        return _seed_child_state(context, walk, child_issue, child)
    except Exception:
        log.exception(
            "issue=#%d could not seed child #%d with its ancestry",
            context.issue.number, child_issue.number,
        )
        _parked(context, f"child #{child_issue.number} ({child.get('title')!r})")
        return False


def _seed_child_state(
    context: _LateContext,
    walk: _ChildWalk,
    child_issue: Issue,
    child: dict,
) -> bool:
    """Add the parent link, the stamp, and the ancestry to a child's state.

    The park an unattributed child took goes with the link that attributes it,
    exactly as the initial mode's orphan repair does. A child created into a
    crash is on GitHub with no parent recorded, and the poll order is the
    repository's rather than this transaction's -- GitHub sorts by most
    recently updated, so the child it just created can be dispatched before
    the write that records it -- and a `blocked` issue nobody claims is parked
    for a human. Leaving that park standing would hand the child an
    `awaiting_human` it never earned: the parent activates it, the implementing
    stage reads the flag, and it waits for a reply nobody owes it.

    Cleared only where this write is the one that first attributes the child.
    A child that already records a parent has been attributed, so any park on
    it is its own -- something it hit while running -- and not this
    transaction's to take back.

    The read is a request, so the poll can observe the close inside it -- and
    what stands immediately behind it is the one write this transaction makes
    to a child's OWN pinned comment. A cancelled cycle leaves every child that
    already exists entirely untouched, so the latch is asked between the two,
    and the answer travels back rather than stopping here: this is the LAST
    step of one child's turn, so a caller told it succeeded would open the
    next slice's issue against a cycle that has just ended.
    """
    child_state = context.gh.read_pinned_state(child_issue)
    if _late_owner._latch_stops(context) is not None:
        log.warning(
            "issue=#%d was observed closed while child #%d was being read; "
            "writing nothing to it", context.issue.number, child_issue.number,
        )
        return False
    if not child_state.get(_state._PARENT_NUMBER):
        child_state.set(_state._PARENT_NUMBER, context.issue.number)
        child_state.set(_state._AWAITING_HUMAN, False)
        child_state.set(_state._PARK_REASON, None)
    if child_state.get(_state._CREATED_AT) is None:
        child_state.set(_state._CREATED_AT, _usage._now_iso())
    _lineage.write_late_ancestry(
        child_state, _late_child_content._child_ancestry(context, child, walk.snapshot_ref),
    )
    context.gh.write_pinned_state(child_issue, child_state)
    return True


def _parked(context: _LateContext, described: str) -> None:
    """Hand the issue back, naming the child that could not be established."""
    _late_outcome._emit_failure(context, LateFailure.CHILD_CREATE_FAILED)
    _late_parks._park(
        context,
        _CHILD_CREATE_PARK.format(child=described),
        reason=_late_park_state.PARK_CHILDREN_FAILED,
    )
