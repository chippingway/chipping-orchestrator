# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The late lineage an ordinary split seeds its children with, or the park when it cannot.

An ordinary decomposition of an issue a late split made, or of one whose own
late split a genuine edit is replacing, creates its children inside a lineage
the bound already counts. Which lineage that is, is `late_split/provenance.py`'s
decision; this owner turns it into what each child is seeded with, and it is
asked twice: before the first child is created, and again before a recovered
split is finalized -- the step that hands the children to the walk that starts
them.

Each child is born one level below its parent under the same root, never as a
fresh root at depth 0 and never past `MAX_LINEAGE_DEPTH`: a parent already at
the bound has no room for children, so its split parks rather than creating
any. The ancestry names the parent and an adjudication to correlate by -- the
parent's own cycle where its record keeps one, the one its own ancestry names
otherwise, and the cycle a retirement dropped where neither does. None of that
is a claim about a snapshot.

A pointer is. A child may be pointed only at the snapshot the parent's own
split still holds, and only once the parent's consumer ledger records it, in
the same write that records it in `children` -- so the reclamation that could
take the ref counts the child as one more consumer that has to end first. A
snapshot another issue holds is protected by a ledger only that issue writes,
so a child is born without that pointer rather than with one nothing keeps; a
child whose parent record never landed has no pointer to lose.

What a seed never carries is anything of the parent's own size gate -- its
measurement, its exemption, or an exact-commit authorization. Each is a claim
about one commit on one issue, and a child is neither.

A lineage the record cannot prove is a refusal, and it parks the parent before
any child exists, or -- where a crash left children recorded -- before the
split is finalized and anything could start them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from github.Issue import Issue

from orchestrator import config
from orchestrator.github.client import GitHubClient
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.engine import guards as _guards
from orchestrator.workflow.late_split import (
    endings as _endings,
    identity as _identity,
    keys as _keys,
    ledger_encoding as _ledger_encoding,
    lineage as _lineage,
    provenance as _provenance,
    state as _late_state,
)
from orchestrator.workflow.late_split.ancestry import LateAncestry
from orchestrator.workflow.late_split.entitlement import SnapshotEntitlement
from orchestrator.workflow.late_split.models import MAX_LINEAGE_DEPTH

log = logging.getLogger("orchestrator.workflow")

# The reason the `park_awaiting_human` audit record carries for a split whose
# children's lineage could not be proved.
PARK_LINEAGE_UNPROVED = "replacement_lineage_unproved"

_AT_THE_BOUND = "it already sits at lineage depth {depth}, and no split may create a child past {bound}"

_NO_ADJUDICATION = "its late record keeps no cycle a child's ancestry could be correlated by"

_UNPROVED_PARK = (
    "{mentions} this issue's children cannot be seeded with the late lineage "
    "they inherit: {refusal}. A child seeded without it would start a fresh "
    "lineage at depth 0 and buy the split a generation past the bound, so none "
    "is created or started while that stands. Repair this issue's pinned "
    "record, or ask the decomposer not to split it."
)


@dataclass(frozen=True)
class ReplacementLineage:
    """What one ordinary split seeds its children with.

    The defaults are the ordinary issue, whose children carry a parent link
    and nothing more. An ancestry is the lineage every child is born into,
    with no pointer on it; a snapshot is the one this issue's own split holds
    and may protect; and a refusal says why neither could be told -- never
    beside either.
    """

    ancestry: LateAncestry | None = None
    snapshot: SnapshotEntitlement | None = None
    refusal: str | None = None

    def protect(self, state: PinnedState, child_number: int) -> None:
        """Record one child on the consumer ledger of the snapshot it is owed.

        On the caller's state, for the write that records the child in
        `children`: the two are one fact to the reclamation, and a child the
        parent tracks that the ledger does not is one whose ref could go while
        it works. Only that ledger's key is written, so nothing else of the
        late record is rewritten through a reader that would normalize it.
        """
        if self.snapshot is None:
            return
        recorded = _late_state.read_late_generation(state).obligations
        owed = recorded.with_consumers((child_number,))
        state.set(_keys.CONSUMERS, _ledger_encoding.ledger_fields(owed)[_keys.CONSUMERS])

    def child_ancestry(self, state: PinnedState, child_number: int) -> LateAncestry | None:
        """The ancestry one child is seeded with, off the parent's record as it stands.

        The pointer rides only on a child the consumer ledger names, which is
        the rule itself rather than a memory of having protected it: the seed
        a crash deferred is repaired from the same record, and a child created
        before that record could protect it is seeded without one.
        """
        if self.ancestry is None:
            return None
        consumers = _late_state.read_late_generation(state).obligations.consumers
        if self.snapshot is None or child_number not in consumers:
            return self.ancestry
        return replace(
            self.ancestry,
            snapshot_ref=self.snapshot.snapshot_ref,
            snapshot_sha=self.snapshot.snapshot_sha,
            mirror_first=self.snapshot.mirror_first,
        )


def read_replacement_lineage(state: PinnedState, issue: Issue) -> ReplacementLineage:
    """Decide what this issue's children are seeded with, or why they may not be.

    Read off the record the tick already holds, so it costs no request. An
    issue no late split charged answers the ordinary lineage, and a refused
    provenance answers its own refusal, since reading either as the other is
    how a lineage starts over at 0. The bound is asked before anything is
    named, because a child it forbids has no ancestry to be given.
    """
    provenance = _provenance.read_provenance(state, issue.number, issue.body)
    if not provenance.is_inherited:
        return ReplacementLineage(refusal=provenance.refusal)
    try:
        depth = _identity.child_lineage_depth(provenance.lineage_depth)
    except _identity.LineageDepthExceeded:
        return ReplacementLineage(refusal=_AT_THE_BOUND.format(
            depth=provenance.lineage_depth, bound=MAX_LINEAGE_DEPTH,
        ))
    adjudication = _adjudication_of(state)
    if adjudication is None:
        return ReplacementLineage(refusal=_NO_ADJUDICATION)
    ancestry = LateAncestry(
        root_issue=provenance.root_issue,
        lineage_depth=depth,
        parent_issue=issue.number,
        cycle_id=adjudication[0],
        generation=adjudication[1],
    )
    return ReplacementLineage(ancestry=ancestry, snapshot=_protectable(provenance.snapshot, ancestry))


def park_unproved(gh: GitHubClient, issue: Issue, state: PinnedState, refusal: str) -> None:
    """Hand the split to a human, naming the evidence that did not hold."""
    log.warning(
        "issue=#%s may create or start no child: %s", issue.number, refusal,
    )
    _guards._park_awaiting_human(
        gh, issue, state,
        _UNPROVED_PARK.format(mentions=config.HITL_MENTIONS, refusal=refusal),
        reason=PARK_LINEAGE_UNPROVED,
    )
    gh.write_pinned_state(issue, state)


def _adjudication_of(state: PinnedState) -> tuple[int, int] | None:
    """The cycle and generation a child's ancestry is correlated by, or None.

    The parent's own cycle wherever its record keeps one: that is the split
    whose children an edit is replacing, and the only one whose ledger a
    pointer can be protected on. An issue with no cycle of its own was cut by
    the adjudication its ancestry names, and a record a retirement took the
    identity off still says which cycle that was. A pair taken anywhere but
    the parent's own record names no ref this issue minted, and it is never
    written beside a pointer -- see `_protectable`.
    """
    generation = _late_state.read_late_generation(state)
    if generation.is_present:
        return generation.cycle_id, generation.generation
    ancestry = _lineage.read_late_ancestry(state)
    if ancestry.is_present:
        return ancestry.cycle_id, ancestry.generation
    retired = _endings.read_retired_cycle(state)
    return (retired, 0) if retired else None


def _protectable(
    held: SnapshotEntitlement | None, ancestry: LateAncestry,
) -> SnapshotEntitlement | None:
    """The snapshot a child may be pointed at, where this issue's ledger keeps it.

    Held to the exact identity the child's ancestry names, owner included,
    because that is what every later reading of the pointer mints the ref
    from and whose ledger it asks: a pointer at another split's ref would
    name a consumer ledger this issue never wrote a child onto.
    """
    if held is None:
        return None
    named = (ancestry.parent_issue, ancestry.cycle_id, ancestry.generation)
    return held if (held.owner_issue, held.cycle_id, held.generation) == named else None
