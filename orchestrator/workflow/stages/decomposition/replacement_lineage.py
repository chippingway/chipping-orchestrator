# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The late lineage an ordinary split would seed its children with, or why it may not.

An ordinary decomposition of an issue a late split made, or of one whose own
late split a genuine edit is replacing, creates its children inside a lineage
the bound already counts. Which lineage that is, is `late_split/provenance.py`'s
decision; this owner turns it into what each child would be seeded with.

Each child is born one level below its parent under the same root, never as a
fresh root at depth 0 and never past `MAX_LINEAGE_DEPTH`: a parent already at
the bound has no room for children, so it is refused rather than given any. The
ancestry names the parent and an adjudication to correlate by -- the parent's
own cycle where its record keeps one, the one its own ancestry names otherwise,
and the cycle a retirement dropped where neither does. None of that is a claim
about a snapshot.

A pointer is. A child may be pointed only at the snapshot the parent's own
split still holds, and only once the parent's consumer ledger records it --
written onto the state that records the child in `children`, so the
reclamation that could take the ref counts the child as one more consumer that
has to end first. Its body would carry the same pointer as instructions,
rendered the way a late split's own children are told, since the body is what
its implementer reads -- and they name that ref and this repository's mirror of
it, the only two names a child's text may give a snapshot. A mirror under
another repository's segment is that repository's copy of the same numbers,
kept by no ledger here. A snapshot another issue holds is protected by a ledger
only that issue writes, so a child is born without that pointer rather than
with one nothing keeps. A parent whose own split's record cannot say whether
its snapshot is still there for a new consumer is not the same as one whose ref
is settled gone, and it is refused rather than read as the second -- as is one
holding it with no base recorded, since the instructions name what the
candidate adds as the range from that base, and a range from nothing is read
against whatever a checkout holds.

What a seed never carries is anything of the parent's own size gate -- its
measurement, its exemption, or an exact-commit authorization. Each is a claim
about one commit on one issue, and a child is neither, so nothing here reads
any of them.

A child already recorded is held to the same answer by `repair`, read off
the parent's record rather than the child's text: while this split still
holds its snapshot every recorded child is owed the pointer, so one the
ledger lost is to be recorded on it again and one carrying no ancestry, or a
pointer at anything else, seeded with it; once the snapshot has passed to a
reclamation the lineage alone is owed, and a pointer is dropped with its
ordering stamp. One carrying exactly what it was owed needs nothing. A child
this split cannot recognize as its own -- a pinned comment that would not
parse, a link to anything but this issue's number, text naming any snapshot
ref it cannot keep, or any other ancestry: a partial group, a field its
reader would drop, another lineage -- is a refusal, with nothing written over
what it carries. A child of an ordinary split is owed no lineage and no
snapshot, so it is recognized only where its comment parses, its link names
this issue or is not carried at all, it carries none of the group, and its
text names no snapshot ref. `park_unproved` is the park every refusal here
would take.

Dormant: no decomposition asks this yet. Ordinary child creation, the park an
unproved lineage would take, the recovery of an interrupted split, and the
release of its children all run without it, so replacement children are still
created with no ancestry and no pointer, and recovered or released with no
repair, until the split reads this before its first child.
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
from orchestrator.workflow.stages.decomposition import late_child_content as _late_child_content, state as _state

log = logging.getLogger("orchestrator.workflow")

# The reason the `park_awaiting_human` audit record carries for a split whose
# children's lineage -- or the snapshot it would point them at, or tell them to
# reuse -- could not be proved.
PARK_LINEAGE_UNPROVED = "replacement_lineage_unproved"

_NO_ADJUDICATION = "its late record keeps no cycle a child's ancestry could be correlated by"

_UNREADABLE_CHILD = "child #{child} carries a pinned comment that would not parse, so nothing it records can be checked"

_OTHER_PARENT = "child #{child} records `parent_number` {parent!r}, which is not this issue's number"

_UNPROMISED = (
    "child #{child} names in its title or body a snapshot this issue's split cannot keep for it -- one it does "
    "not hold, or another repository's copy of one"
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

_BASE_NOTICE = (
    "the late lineage this issue's children inherit is proved, and the snapshot its own split holds for them is "
    "recorded with no base its candidate was cut against. A child pointed at it is told to read what that "
    "candidate adds as a diff from its base, and a diff from no base is read against whatever the child's checkout "
    "holds; seeded without it, a child would give up work it may still be owed. So none is created or started "
    "while that stands. Repair `late_base_sha` on this issue's late record, or ask the decomposer not to split it."
)

_CHILD_NOTICE = (
    "this issue's split recorded its children, and one of them is not a child it can say it seeded: {reason}. "
    "Starting it would run a child whose lineage, parent, or snapshot nothing vouches for, so no child of this "
    "split is started -- by a recovery's finalize or a later release -- while that stands. Repair or close that "
    "child."
)


@dataclass(frozen=True)
class SeedRepair:
    """What a recovery would write onto one recorded child's ancestry before it finalizes.

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
    """What one ordinary split would seed its children with.

    The defaults are the ordinary issue, whose children carry a parent link
    and nothing more. An ancestry is the lineage every child is born into,
    with no pointer on it; a snapshot is the one this issue's own split holds
    and may protect, beside the reuse instructions a child pointed at it is
    told -- see `born_under`; and a refusal is the sentence a park would post
    saying why neither could be told -- never beside either.
    """

    ancestry: LateAncestry | None = None
    snapshot: _entitlement.SnapshotEntitlement | None = None
    instructions: str = ""
    refusal: str | None = None

    @classmethod
    def unproved(cls, reason: str | None) -> ReplacementLineage:
        """The ordinary lineage where nothing is refused, else the refusal of an unreadable one."""
        if reason is None:
            return cls()
        return cls(refusal=_LINEAGE_NOTICE.format(reason=reason))

    @classmethod
    def born_under(
        cls,
        ancestry: LateAncestry,
        held: _entitlement.SnapshotEntitlement | None,
        base_sha: str,
        spec: config.RepoSpec,
    ) -> ReplacementLineage:
        """The lineage `ancestry` names, pointed at `held` only where this issue's ledger keeps it.

        Held to the exact identity the child's ancestry names, owner included,
        because that is what every later reading of the pointer mints the ref
        from and whose ledger it asks: a pointer at another split's ref would
        name a consumer ledger this issue never wrote a child onto. `base_sha`
        is what that split's candidate was cut against, and the instructions
        name the candidate's change as the range from it -- so a record
        keeping none beside a held snapshot is refused rather than read as a
        pointer with instructions nobody can follow, or as no pointer at all.
        """
        if held is None:
            return cls(ancestry=ancestry)
        named = (ancestry.parent_issue, ancestry.cycle_id, ancestry.generation)
        if (held.owner_issue, held.cycle_id, held.generation) != named:
            return cls(ancestry=ancestry)
        if not base_sha:
            return cls(refusal=_BASE_NOTICE)
        kept = cls(ancestry=ancestry, snapshot=held)
        return replace(kept, instructions=_late_child_content._reuse_block(spec, kept.pointed(), base_sha))

    @property
    def told(self) -> frozenset[str]:
        """Every name a child's title or body may give a snapshot: the ones its instructions give it.

        Read back through the reader a child's own text is held to, so the
        two can never disagree about a spelling: the ref on the remote and
        this repository's mirror of it. Another repository sharing the clone
        mirrors the same three numbers under its own segment, and that copy
        may hold other work and is kept by no ledger this issue writes -- so
        no other name is one, and a lineage pointing at nothing permits none.
        """
        return _late_child_content._named_snapshots(self.instructions)

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
        """The ancestry the ledger, as it stands, lets one child carry.

        The pointer rides only on a child the consumer ledger names, so a
        seed written right behind `protect` carries it, and one whose slot
        the ledger lost carries the lineage alone rather than a pointer
        nothing keeps -- which is how `repair` tells that slot was lost.
        """
        pointed = self.pointed()
        consumers = _late_state.read_late_generation(state).obligations.consumers
        if pointed is None or child_number not in consumers:
            return self.ancestry
        return pointed

    def repair(
        self,
        state: PinnedState,
        parent: int,
        child_number: int,
        child_state: PinnedState,
        instructed: frozenset[str],
    ) -> SeedRepair:
        """What a recovered split of `parent` would do with one recorded child's ancestry.

        A deferred release would ask the same of each child it starts, and
        start only one that needs nothing: no refusal, and nothing to write.

        What a child is owed is read off the parent's own record, never off
        the child: while this issue's split still holds its snapshot, every
        child it recorded was owed the pointer -- the split protected each
        one in the write that recorded it -- and a ledger that no longer names
        one has lost a slot rather than settled it. So that child is recorded
        on the consumer ledger again, before its seed and before anything
        could start it, and seeded with the pointer, whatever its text now
        says. Once the snapshot has passed to a reclamation, the lineage is
        all any child is owed, and a pointer one still carries is dropped --
        with the ordering stamp, which is a claim about that ref; a stamp
        standing alone, what the child's own guard leaves when it drops a
        pointer, names no ref and is left as it is.

        `instructed` is every snapshot ref the child's title and body name,
        read as a slice is read before it is created, and it can only refuse:
        the text is what its implementer reads, so a child naming any ref but
        the one this split still holds -- by the names in `told` -- names a
        snapshot nothing keeps for it. That includes every child of an
        ordinary split that names one at all.

        Every child has to be one this split can recognize as its own -- see
        `_unrecognized` -- before anything is written to it or it is
        finalized, a child of an ordinary split included: that one is owed
        no lineage, so it is left as it stands once recognized. Any other
        one carrying none of the group is then seeded with what it was owed,
        and one carrying the group carries exactly the lineage it was owed
        and has its pointer written to be the one it is owed.
        """
        pointed = self.pointed()
        owed = self.ancestry if pointed is None else pointed
        refusal = _unrecognized(
            child_state,
            owed or LateAncestry(),
            parent,
            child_number,
            promised=instructed <= self.told,
        )
        if refusal is not None:
            return SeedRepair(refusal=_CHILD_NOTICE.format(reason=refusal))
        if owed is None:
            return SeedRepair()
        # Owed the pointer, and the ledger lost the slot that protects it.
        protect = self.child_ancestry(state, child_number) != owed
        if not any(child_state.carries(key) for key in _lineage.LATE_ANCESTRY_KEYS):
            return SeedRepair(ancestry=owed, protect=protect)
        recorded = _lineage.read_late_ancestry(child_state)
        if (recorded.snapshot_ref, recorded.snapshot_sha) == (owed.snapshot_ref, owed.snapshot_sha):
            return SeedRepair(protect=protect)
        return SeedRepair(ancestry=owed, protect=protect)


def read_replacement_lineage(state: PinnedState, issue: Issue, spec: config.RepoSpec) -> ReplacementLineage:
    """Decide what this issue's children would be seeded with, or why they may not be.

    Read off the record the caller already holds, so it costs no request. An
    issue no late split charged answers the ordinary lineage, and a refused
    provenance answers its own refusal, since reading either as the other is
    how a lineage starts over at 0. The bound is asked before anything is
    named, because a child it forbids has no ancestry to be given. A split of
    this issue's own whose snapshot cannot be told held or released is a
    refusal too, though the lineage beside it is proved: seeding its children
    without a pointer would read a record nobody can read as one that settled
    the ref gone.
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
    ), provenance.snapshot, generation.base_sha, spec)


def park_unproved(gh: GitHubClient, issue: Issue, state: PinnedState, notice: str) -> None:
    """Hand the issue to a human, with the notice its refusal carries.

    The issue is a split whose children's lineage cannot be proved, or a
    child whose seed is not the one its receipt owes; either runs nothing
    until it is.
    """
    log.warning(
        "issue=#%s runs nothing until its lineage is proved: %s", issue.number, notice,
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


def _unrecognized(
    child_state: PinnedState, owed: LateAncestry, parent: int, child_number: int, *, promised: bool,
) -> str | None:
    """Why a recorded child of `parent` is not one this split can say it seeded, or None.

    A pinned comment that would not parse reads back empty, exactly as a
    child nobody seeded does, and writing a seed over it would take whatever
    it carried with it -- so it is refused before anything is read off it. A
    child whose text names a snapshot this split cannot keep for it is not
    `promised`. A link proves parentage only as this issue's number: one
    naming another is a child another tree claims, and a float, a bool, a
    `null`, or any other value a hand edit leaves is no issue number, whatever
    it compares equal to. Only a link the comment does not carry at all is
    the one a crash deferred. And an ancestry has to be the whole group,
    written back exactly as the comment carries it -- a field its reader would
    drop, a `null`, or a key it answers with its empty value comes back
    different -- naming the lineage it was `owed`, its pointer aside; a child
    of an ordinary split is owed the empty ancestry, which no group names, so
    any of the group on it is one this split never wrote. A child carrying
    none of the group is recognized: it is the seed a crash deferred, or all
    an ordinary split ever seeds.
    """
    if not child_state.parsed:
        return _UNREADABLE_CHILD.format(child=child_number)
    if not promised:
        return _UNPROMISED.format(child=child_number)
    linked = child_state.get(_state._PARENT_NUMBER)
    if child_state.carries(_state._PARENT_NUMBER) and not _state._links_to(linked, parent):
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
