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
take the ref counts the child as one more consumer that has to end first. Its
body carries the same pointer as instructions, rendered the way a late
split's own children are told, since the body is what its implementer reads. A
snapshot another issue holds is protected by a ledger only that issue writes,
so a child is born without that pointer rather than with one nothing keeps; a
child whose parent record never landed has no pointer to lose. A parent whose
own split's record cannot say whether its snapshot is still there for a new
consumer is not the same as one whose ref is settled gone, and it is refused
rather than read as the second.

What a seed never carries is anything of the parent's own size gate -- its
measurement, its exemption, or an exact-commit authorization. Each is a claim
about one commit on one issue, and a child is neither.

A lineage the record cannot prove is a refusal, and it parks the parent before
any child exists, or -- where a crash left children recorded -- before the
split is finalized and anything could start them. That recovery holds every
recorded child to the same answer: a child carrying no ancestry is seeded,
one carrying exactly what it was owed is left alone, a pointer the ledger no
longer protects is dropped with its ordering stamp and the lineage beside it
kept -- unless the child's title or body names the snapshot this split still
holds, since that text is what its implementer reads: that child is recorded
on the ledger again and pointed at the ref -- and a child this split cannot
recognize as its own -- a pinned comment that would not parse, a link to
another parent, text naming any snapshot ref it cannot keep, or any other
ancestry: a partial group, a field its reader would drop, another lineage --
refuses the finalize that would start it, with nothing written over what it
carries.
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
    entitlement as _entitlement,
    identity as _identity,
    keys as _keys,
    ledger_encoding as _ledger_encoding,
    lineage as _lineage,
    provenance as _provenance,
    state as _late_state,
)
from orchestrator.workflow.late_split.ancestry import LateAncestry
from orchestrator.workflow.late_split.models import MAX_LINEAGE_DEPTH
from orchestrator.workflow.stages.decomposition import state as _state

log = logging.getLogger("orchestrator.workflow")

# The reason the `park_awaiting_human` audit record carries for a split whose
# children's lineage -- or the snapshot it would point them at, or tell them to
# reuse -- could not be proved.
PARK_LINEAGE_UNPROVED = "replacement_lineage_unproved"

_NO_ADJUDICATION = "its late record keeps no cycle a child's ancestry could be correlated by"

_UNREADABLE_CHILD = "child #{child} carries a pinned comment that would not parse, so nothing it records can be checked"

_OTHER_PARENT = "child #{child} records `parent_number` {parent!r}, not this issue"

_UNPROMISED = (
    "child #{child} names in its title or body a snapshot this issue's split cannot keep for it -- one it no "
    "longer holds, or not its own"
)

_FOREIGN_SEED = (
    "child #{child} carries a late ancestry this split did not seed -- part of the group, a field its reader would "
    "drop, or another lineage"
)

# What a park says, one sentence per thing that did not hold, because each
# asks a human for something different: a lineage nobody can read, a bound
# already reached, a snapshot nobody can promise, and a recorded child nobody
# can vouch for.
_LINEAGE_NOTICE = (
    "this issue's children cannot be seeded with the late lineage they inherit: {reason}. A child seeded "
    "without it would read as a fresh lineage at depth 0 and buy the split a generation past the bound, so none "
    "is created or started while that stands. Repair this issue's pinned record, or ask the decomposer not to "
    "split it."
)

_BOUND_NOTICE = (
    "this issue already sits at lineage depth {depth}, and no split may create a child past depth {bound}, so "
    "none of the children the decomposer proposed is created. Its work lands as one change: ask the decomposer "
    "not to split it."
)

_SNAPSHOT_NOTICE = (
    "the late lineage this issue's children inherit is proved, and the snapshot its own split preserved is not "
    "one a child can safely be promised: {reason}. Pointed at that ref, a child could lose it while it works; "
    "seeded without it, a child would give up work it may still be owed. So none is created or started while "
    "that stands. Repair this issue's late record so the snapshot reads as held or released, or ask the "
    "decomposer not to split it."
)

_CHILD_NOTICE = (
    "this issue's split recorded its children, and one of them is not a child it can say it seeded: {reason}. "
    "Finalizing would start children whose lineage or parent nothing vouches for, so none of them is started "
    "while that stands. Repair or close that child."
)


@dataclass(frozen=True)
class SeedRepair:
    """What recovery writes onto one recorded child's ancestry before it finalizes.

    The defaults are a child that needs nothing: seeded as it was owed, or
    owed no lineage at all. An ancestry is the group to write, `protect` says
    the parent's consumer ledger has to record the child again before that
    group or any finalize lands, and a refusal is the notice saying why this
    child may not be finalized -- never beside either of the others.
    """

    ancestry: LateAncestry | None = None
    protect: bool = False
    refusal: str | None = None


@dataclass(frozen=True)
class ReplacementLineage:
    """What one ordinary split seeds its children with.

    The defaults are the ordinary issue, whose children carry a parent link
    and nothing more. An ancestry is the lineage every child is born into,
    with no pointer on it; a snapshot is the one this issue's own split holds
    and may protect, beside the base its candidate was cut against; and a
    refusal is the notice saying why neither could be told -- never beside
    either.
    """

    ancestry: LateAncestry | None = None
    snapshot: _entitlement.SnapshotEntitlement | None = None
    base_sha: str = ""
    refusal: str | None = None

    @classmethod
    def unproved(cls, reason: str | None) -> ReplacementLineage:
        """The ordinary lineage where nothing is refused, else the refusal of an unreadable one."""
        if reason is None:
            return cls()
        return cls(refusal=_LINEAGE_NOTICE.format(reason=reason))

    @classmethod
    def born_under(
        cls, ancestry: LateAncestry, held: _entitlement.SnapshotEntitlement | None, base_sha: str,
    ) -> ReplacementLineage:
        """The lineage `ancestry` names, pointed at `held` only where this issue's ledger keeps it.

        Held to the exact identity the child's ancestry names, owner included,
        because that is what every later reading of the pointer mints the ref
        from and whose ledger it asks: a pointer at another split's ref would
        name a consumer ledger this issue never wrote a child onto. `base_sha`
        is what that split's candidate was cut against, kept only beside a
        snapshot a child is pointed at.
        """
        if held is None:
            return cls(ancestry=ancestry)
        named = (ancestry.parent_issue, ancestry.cycle_id, ancestry.generation)
        if (held.owner_issue, held.cycle_id, held.generation) != named:
            return cls(ancestry=ancestry)
        return cls(ancestry=ancestry, snapshot=held, base_sha=base_sha)

    def pointed(self) -> LateAncestry | None:
        """The lineage with the pointer a protected child carries, or None where none is owed."""
        if self.ancestry is None or self.snapshot is None:
            return None
        return replace(
            self.ancestry,
            snapshot_ref=self.snapshot.snapshot_ref,
            snapshot_sha=self.snapshot.snapshot_sha,
            mirror_first=self.snapshot.mirror_first,
        )

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
        pointed = self.pointed()
        consumers = _late_state.read_late_generation(state).obligations.consumers
        if pointed is None or child_number not in consumers:
            return self.ancestry
        return pointed

    def repair(
        self, state: PinnedState, child_number: int, child_state: PinnedState, instructed: frozenset[str],
    ) -> SeedRepair:
        """What a recovered split does with one recorded child's ancestry.

        `instructed` is every snapshot ref the child's title and body name,
        read as a slice is read before it is created, and it outranks the
        ledger: the text is written before the record that protects the
        child, and is what its implementer reads whatever the pinned comment
        says. A child naming only the one snapshot this issue's split can
        still promise is owed that pointer, and is recorded on the consumer
        ledger again where the ledger lost it -- before its seed, and before
        anything could start it. A child naming any other ref, or one this
        split can no longer promise, is refused: its text names a snapshot
        nothing keeps for it.

        A child owed no lineage is left alone. Every other one has to be a
        child this split can recognize as its own -- see `_unrecognized` --
        before anything is written to it: one carrying none of the group is
        then seeded with what it was owed, and one carrying the group carries
        exactly the lineage it was owed. An instructed child's pointer is
        written to be the one it was told about. Any other child's is kept
        where it is none or the one the ledger protects it for, and dropped
        otherwise -- with the ordering stamp, which is a claim about that ref;
        a stamp standing alone, what the child's own guard leaves when it
        drops a pointer, names no ref and is left as it is.
        """
        if self.ancestry is None:
            return SeedRepair()
        owed = self._owed(state, child_number, instructed)
        refusal = _unrecognized(child_state, owed, child_number)
        if refusal is not None:
            return SeedRepair(refusal=_CHILD_NOTICE.format(reason=refusal))
        # Owed a pointer the ledger does not name: only an instructed child.
        protect = bool(instructed) and self.child_ancestry(state, child_number) != owed
        if not any(child_state.carries(key) for key in _lineage.LATE_ANCESTRY_KEYS):
            return SeedRepair(ancestry=owed, protect=protect)
        recorded = _lineage.read_late_ancestry(child_state)
        kept = {(owed.snapshot_ref, owed.snapshot_sha)}
        if not instructed:
            kept.add(("", ""))
        if (recorded.snapshot_ref, recorded.snapshot_sha) in kept:
            return SeedRepair(protect=protect)
        return SeedRepair(ancestry=owed if instructed else _unpointed(recorded), protect=protect)

    def _owed(self, state: PinnedState, child_number: int, instructed: frozenset[str]) -> LateAncestry | None:
        """The ancestry one recorded child is owed, or None where its instructions name a ref it cannot be.

        A child told about no snapshot is owed what the ledger protects it
        for, and one told about exactly the snapshot this split holds is owed
        that pointer whatever the ledger says -- the repair records it there.
        """
        if not instructed:
            return self.child_ancestry(state, child_number)
        pointed = self.pointed()
        if pointed is None or instructed != {pointed.snapshot_ref}:
            return None
        return pointed


def read_replacement_lineage(state: PinnedState, issue: Issue) -> ReplacementLineage:
    """Decide what this issue's children are seeded with, or why they may not be.

    Read off the record the tick already holds, so it costs no request. An
    issue no late split charged answers the ordinary lineage, and a refused
    provenance answers its own refusal, since reading either as the other is
    how a lineage starts over at 0. The bound is asked before anything is
    named, because a child it forbids has no ancestry to be given. A split of
    this issue's own whose snapshot cannot be told held or released is a
    refusal too, though the lineage beside it is proved: seeding its children
    without a pointer would read a record nobody can read as one that settled
    the ref gone. Each refusal is the notice its park posts.
    """
    provenance = _provenance.read_provenance(state, issue.number, issue.body)
    if not provenance.is_inherited:
        return ReplacementLineage.unproved(provenance.refusal)
    try:
        depth = _identity.child_lineage_depth(provenance.lineage_depth)
    except _identity.LineageDepthExceeded:
        return ReplacementLineage(refusal=_BOUND_NOTICE.format(
            depth=provenance.lineage_depth, bound=MAX_LINEAGE_DEPTH,
        ))
    adjudication = _adjudication_of(state)
    if adjudication is None:
        return ReplacementLineage.unproved(_NO_ADJUDICATION)
    generation = _late_state.read_late_generation(state)
    unsettled = _entitlement.unsettled_snapshot(generation, issue.number)
    if unsettled is not None:
        return ReplacementLineage(refusal=_SNAPSHOT_NOTICE.format(reason=unsettled))
    return ReplacementLineage.born_under(LateAncestry(
        root_issue=provenance.root_issue,
        lineage_depth=depth,
        parent_issue=issue.number,
        cycle_id=adjudication[0],
        generation=adjudication[1],
    ), provenance.snapshot, generation.base_sha)


def park_unproved(gh: GitHubClient, issue: Issue, state: PinnedState, notice: str) -> None:
    """Hand the split to a human, with the notice its refusal carries."""
    log.warning(
        "issue=#%s may create or start no child: %s", issue.number, notice,
    )
    _guards._park_awaiting_human(
        gh, issue, state, f"{config.HITL_MENTIONS} {notice}", reason=PARK_LINEAGE_UNPROVED,
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
    written beside a pointer -- see `ReplacementLineage.born_under`.
    """
    generation = _late_state.read_late_generation(state)
    if generation.is_present:
        return generation.cycle_id, generation.generation
    ancestry = _lineage.read_late_ancestry(state)
    if ancestry.is_present:
        return ancestry.cycle_id, ancestry.generation
    retired = _endings.read_retired_cycle(state)
    return (retired, 0) if retired else None


def _unrecognized(child_state: PinnedState, owed: LateAncestry | None, child_number: int) -> str | None:
    """Why a recorded child is not one this split can say it seeded, or None.

    A pinned comment that would not parse reads back empty, exactly as a
    child nobody seeded does, and writing a seed over it would take whatever
    it carried with it -- so it is refused before anything is read off it. No
    owed ancestry at all is a child whose text names a snapshot this split
    cannot keep for it. A link to another parent is a child another tree claims. And
    an ancestry has to be the whole group, written back exactly as the comment
    carries it -- a field its reader would drop, a `null`, or a key it answers
    with its empty value comes back different -- naming the lineage it was
    owed, its pointer aside. A child carrying none of the group is recognized:
    it is the seed a crash deferred.
    """
    if not child_state.parsed:
        return _UNREADABLE_CHILD.format(child=child_number)
    if owed is None:
        return _UNPROMISED.format(child=child_number)
    linked = child_state.get(_state._PARENT_NUMBER)
    if linked and linked != owed.parent_issue:
        return _OTHER_PARENT.format(child=child_number, parent=linked)
    if not any(child_state.carries(key) for key in _lineage.LATE_ANCESTRY_KEYS):
        return None
    recorded = _lineage.read_late_ancestry(child_state)
    rewritten = PinnedState()
    _lineage.write_late_ancestry(rewritten, recorded)
    carried = {
        key: child_state.get(key)
        for key in _lineage.LATE_ANCESTRY_KEYS
        if child_state.carries(key)
    }
    owned = recorded.is_present and _unpointed(recorded) == _unpointed(owed)
    return None if owned and carried == rewritten.data else _FOREIGN_SEED.format(child=child_number)


def _unpointed(ancestry: LateAncestry) -> LateAncestry:
    """What places an ancestry in a lineage: everything but the pointer and its ordering stamp."""
    return replace(ancestry, snapshot_ref="", snapshot_sha="", mirror_first=False)
