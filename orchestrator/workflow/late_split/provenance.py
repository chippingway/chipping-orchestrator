# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What an ordinary decomposition inherits from the late lineage it runs in.

An ordinary decomposer re-deriving a manifest for an issue a late split made,
or for one whose own late split it is replacing, is creating children inside a
lineage the bound already counts. Children it created as ordinary issues would
each be a fresh root at depth 0, which is exactly how a lineage buys itself
generations past `MAX_LINEAGE_DEPTH`. So before any of them is created the
issue's own record is asked what it is, and it answers one of three things.

An ordinary issue carries no lineage: no ancestry key, no child receipt in its
body, and no late record with any evidence of a split. Its children are
ordinary too.

An inherited lineage names the root, the depth late splits have already
charged this issue at -- its replacement children are born one past it -- and
the one snapshot, if any, they could be pointed at. The depth comes off the
ancestry wherever one is recorded, because that is the record the split that
made this issue wrote; an issue with none whose own late record proves a split
made children is that lineage's root at depth 0. Which snapshot that is, and
what proves the split, are the `entitlement` owner's. Recording who else now
consumes the snapshot is the caller's, as is everything it creates.

Every other reading is a refusal with the reason, never a guess: a pinned
comment that would not parse, an ancestry with no readable parent and cycle or
carrying any field its reader would drop, a `null` one included, one whose
root or depth is missing or disagrees with itself, a body claiming a split
made the issue while no ancestry landed, a late record carrying an identity or
a piece of split evidence -- its phase or the one a cancellation kept, its
register, its announcement, a ledger -- that its reader would drop, a live
cycle missing its root, issue, or depth, a record whose cycle is gone beside
fields it still carries, one still creating children or cancelled while it
was, one naming a child that is no other issue, one whose split cannot be told
from a failed one or whose announced children it no longer names, one written
for another issue, one naming a lineage no ancestry carries, one naming a root
its ancestry does not, and a split whose depth disagrees with the ancestry's.
Each of those could hide a depth already charged, and reading one as an
ordinary issue would start the lineage over at 0.

Read-only and local: the pinned comment and the body the caller already holds
are the whole of the evidence, and nothing here writes either.

Dormant: its one caller is `stages/decomposition/replacement_lineage.py`,
which turns this answer into what each replacement child would be seeded with
and is not asked by any decomposition yet, so replacement children are still
created without a lineage until the split that seeds them reads that first.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import (
    ancestry as _ancestry,
    entitlement as _entitlement,
    keys as _keys,
    ledgers as _ledgers,
    lineage as _lineage,
    payloads as _payloads,
    phases as _late_phases,
    state as _late_state,
)
from orchestrator.workflow.late_split.models import LateGeneration

# Every field this decision reads off a late record, each with the test a value
# the comment carries -- `null` included -- has to pass. The typed record reads
# a value that fails back as no value at all: a cycle as no record, a phase or
# a cancelled boundary as none, a register as no children, an announcement as
# never made, a `null` ledger as an empty one. Each of those is a lineage
# elsewhere, an in-flight child, or a split that would go unasked. A ledger
# carried as anything else is kept verbatim by its reader, and the split
# evidence answers for that one.
_READABLE = MappingProxyType({
    _keys.CYCLE_ID: lambda raw: _payloads.as_identity(raw) is not None,
    _keys.GENERATION: lambda raw: _payloads.as_count(raw) is not None,
    _keys.ROOT_ISSUE: lambda raw: _payloads.as_identity(raw) is not None,
    _keys.CURRENT_ISSUE: lambda raw: _payloads.as_identity(raw) is not None,
    _keys.LINEAGE_DEPTH: lambda raw: _payloads.as_depth(raw) is not None,
    _keys.PHASE: lambda raw: _payloads.as_member(_late_phases.LatePhase, raw) is not None,
    _keys.SPLIT_CHILDREN: lambda raw: bool(_ledgers.read_register(raw)),
    _keys.RESOURCES: lambda raw: raw is not None,
    _keys.CONSUMERS: lambda raw: raw is not None,
    _keys.LINKS_ANNOUNCED: lambda raw: raw is True,
    _keys.CANCELLED_PHASE: lambda raw: _payloads.as_member(_late_phases.LatePhase, raw) is not None,
})

# What every live cycle records, since each is what places it in a lineage. The
# counter is not among them: a restarted cycle's is 0, and that is dropped.
_REQUIRED_KEYS = (_keys.ROOT_ISSUE, _keys.CURRENT_ISSUE, _keys.LINEAGE_DEPTH)

# What a late record with no identity may still carry: the two ledgers and the
# route bookkeeping a retirement writes beside the clear. Anything else there
# is a record whose identity was lost rather than retired.
_IDENTITYLESS_KEYS = frozenset((_keys.RESOURCES, _keys.CONSUMERS, _keys.SPENDS))

_UNPARSED = "its pinned comment could not be parsed, so nothing it records can be read"

_UNREADABLE_ANCESTRY = "its pinned ancestry is recorded but names no parent and cycle this binary can read"

_DROPPED_ANCESTRY = "its pinned ancestry carries a `{key}` this binary cannot read"

_UNSEEDED_CHILD = (
    "its body carries a late split's child receipt, and the ancestry that split seeds was never recorded"
)

_NO_ROOT = "its ancestry names no root"

_NO_DEPTH = "its ancestry records depth {depth}, and a child of a split is born at depth 1 or deeper"

_SELF_ANCESTOR = "its ancestry names this issue as its own root or parent"

_ROOT_PARENT_DEPTH = (
    "its ancestry names root #{root} and parent #{parent} at depth {depth}, "
    "and only a depth-1 child's parent is its root"
)

_UNREADABLE_FIELD = "its late record carries a `{key}` this binary cannot read"

_MISSING_FIELD = "its live late cycle {cycle} records no `{key}`"

_UNIDENTIFIED_RECORD = "its late record carries `{key}` beside no cycle identity"

_IN_FLIGHT = "late split cycle {cycle} is still creating its children"

_CANCELLED_IN_FLIGHT = "late split cycle {cycle} was cancelled while it was creating its children"

_AMBIGUOUS_SPLIT = (
    "its late record holds a snapshot, an announcement of its children, or a ledger entry this binary cannot "
    "read, and names no child, so what its split made cannot be told"
)

_INVALID_CHILD = "its late ledgers name a child that is not an issue, or that is this issue itself"

_FOREIGN_RECORD = "its late record was written for issue #{recorded}"

_OTHER_ROOT = "its late record names root #{recorded}, and its ancestry names root #{root}"

_UNANCESTORED_LINEAGE = (
    "its late record names root #{root} at depth {depth}, and no ancestry records a lineage above this issue"
)


@dataclass(frozen=True)
class LateProvenance:
    """Where an issue an ordinary decomposer is about to split stands.

    The defaults are the ordinary issue. A root marks an inherited lineage,
    and a refusal says why neither can be told -- the two never together.
    """

    root_issue: int = 0
    lineage_depth: int | None = None
    snapshot: _entitlement.SnapshotEntitlement | None = None
    refusal: str | None = None

    @property
    def is_inherited(self) -> bool:
        """Whether this issue's children are born inside a late lineage."""
        return self.root_issue > 0

    @property
    def is_refused(self) -> bool:
        """Whether the evidence could not say which lineage this issue is in."""
        return self.refusal is not None


def read_provenance(state: PinnedState, issue_number: int, body: Any) -> LateProvenance:
    """Decide which late lineage, if any, this issue's children inherit.

    A comment that would not parse reads back empty, which is exactly what an
    issue no split touched reads back as, so it is refused before anything is
    read off it. The ancestry is asked next because it outranks everything: it is
    the record the split that made this issue wrote, and what the size gate
    mints this issue's own generations from. The late record beside it is
    asked second -- whether it is whole, whether this issue split itself, and
    whether that split agrees with the lineage the ancestry names.
    """
    if not state.parsed:
        return LateProvenance(refusal=_UNPARSED)
    ancestry = _lineage.read_late_ancestry(state)
    generation = _late_state.read_late_generation(state)
    refusal = (
        _ancestry_record_refusal(state, ancestry, body)
        or _ancestry_refusal(ancestry, issue_number)
        or _record_refusal(state, generation)
        or _generation_refusal(state, generation, ancestry, issue_number)
    )
    if refusal is not None:
        return LateProvenance(refusal=refusal)
    snapshot = _entitlement.SnapshotEntitlement.for_replacements(generation, ancestry, issue_number)
    if ancestry.is_present:
        return LateProvenance(
            root_issue=ancestry.root_issue, lineage_depth=ancestry.lineage_depth, snapshot=snapshot,
        )
    if _entitlement.split_evidence(generation, issue_number) is _entitlement.SplitEvidence.PROVED:
        return LateProvenance(root_issue=issue_number, lineage_depth=0, snapshot=snapshot)
    return LateProvenance()


def _ancestry_record_refusal(state: PinnedState, ancestry: _ancestry.LateAncestry, body: Any) -> str | None:
    """Why this issue's ancestry cannot be read whole, or None.

    An absent ancestry is only an ordinary issue when nothing says one was
    meant to be there. A key left behind is a record this binary cannot read,
    and a child receipt in the body is the crash window between recording a
    child and seeding it -- the split's own marker, standing where the ancestry
    it carries never landed. Neither is read as depth 0.

    A present one is asked field by field, since its reader answers a value
    it cannot use -- a generation that is not a count, a flag that is not
    `true`, a ref outside the namespace -- with the field's empty value rather
    than a refusal, and the ancestry that comes back names a lineage, a cycle,
    or a pointer nobody wrote. Whatever the record would not write back the
    way the comment carries it is one of those, and a `null` it would leave
    out is too: the key is asked after as well as the value.
    """
    carried = [key for key in _lineage.LATE_ANCESTRY_KEYS if state.carries(key)]
    if not carried:
        receipted = isinstance(body, str) and _ancestry.CHILD_RECEIPT in body
        return _UNSEEDED_CHILD if receipted else None
    if not ancestry.is_present:
        return _UNREADABLE_ANCESTRY
    rewritten = PinnedState()
    _lineage.write_late_ancestry(rewritten, ancestry)
    written = rewritten.data.items()
    dropped = [key for key in carried if (key, state.get(key)) not in written]
    return _DROPPED_ANCESTRY.format(key=dropped[0]) if dropped else None


def _ancestry_refusal(ancestry: _ancestry.LateAncestry, issue_number: int) -> str | None:
    """Why a recorded ancestry cannot place this issue in a lineage, or None.

    Held to the shape every split seeds: a root, a depth of at least 1, an
    issue that is neither its own root nor its own parent, and a parent that
    is the root exactly when the depth is 1. A body receipt beside it is not
    asked about, since the pinned record is the one only this orchestrator
    writes. An absent ancestry has no shape to hold.
    """
    if not ancestry.is_present:
        return None
    checks = (
        (not ancestry.root_issue, _NO_ROOT),
        (not ancestry.lineage_depth, _NO_DEPTH.format(depth=ancestry.lineage_depth)),
        (issue_number in {ancestry.root_issue, ancestry.parent_issue}, _SELF_ANCESTOR),
        (
            (ancestry.lineage_depth == 1) != (ancestry.root_issue == ancestry.parent_issue),
            _ROOT_PARENT_DEPTH.format(
                root=ancestry.root_issue, parent=ancestry.parent_issue, depth=ancestry.lineage_depth,
            ),
        ),
    )
    return next((reason for failed, reason in checks if failed), None)


def _record_refusal(state: PinnedState, generation: LateGeneration) -> str | None:
    """Why this issue's late record cannot be read whole, or None.

    Asked of the raw fields, because the typed record reads a damaged value
    back as no value at all: a cycle nobody can read leaves a record that is
    not present, and every root, depth, and register beside it would then go
    unasked -- an issue whose record names a lineage elsewhere would read as
    ordinary, and a split contradicting its ancestry would read as none. A
    field that is missing is asked about too, where one has to be there: a
    live cycle names its root, its issue, and its depth, and a record the
    retirements left is the one shape with no identity, carrying nothing but
    its ledgers and route bookkeeping.
    """
    recorded = frozenset(key for key in _keys.LATE_STATE_KEYS if state.carries(key))
    for key, readable in _READABLE.items():
        if key in recorded and not readable(state.get(key)):
            return _UNREADABLE_FIELD.format(key=key)
    if generation.is_present:
        missing = [required for required in _REQUIRED_KEYS if required not in recorded]
        return _MISSING_FIELD.format(cycle=generation.cycle_id, key=missing[0]) if missing else None
    stray = sorted(recorded - _IDENTITYLESS_KEYS)
    return _UNIDENTIFIED_RECORD.format(key=stray[0]) if stray else None


def _generation_refusal(
    state: PinnedState, generation: LateGeneration, ancestry: _ancestry.LateAncestry, issue_number: int,
) -> str | None:
    """Why this issue's own late record cannot place it, or None.

    One mid-split may have created a child its ledger does not name yet, and
    so may one cancelled mid-split, whose interrupted boundary the
    cancellation keeps beside its own. One whose ledgers name a child that is
    no other issue would prove a split on damage alone. One holding a
    snapshot or an unreadable entry and no child may be a split that made
    children or one that failed before its first, and one holding the
    announcement of its children's links and no child made them and lost
    which; the difference is a level of the lineage. One written for another
    issue is damage.
    """
    evidence = _entitlement.split_evidence(generation, issue_number)
    checks = (
        (generation.phase in _late_phases.IN_FLIGHT_PHASES, _IN_FLIGHT.format(cycle=generation.cycle_id)),
        (
            generation.cancelled_phase in _late_phases.IN_FLIGHT_PHASES,
            _CANCELLED_IN_FLIGHT.format(cycle=generation.cycle_id),
        ),
        (evidence is _entitlement.SplitEvidence.INVALID, _INVALID_CHILD),
        (evidence is _entitlement.SplitEvidence.AMBIGUOUS, _AMBIGUOUS_SPLIT),
        (
            generation.is_present and generation.current_issue != issue_number,
            _FOREIGN_RECORD.format(recorded=generation.current_issue),
        ),
    )
    first = next((reason for failed, reason in checks if failed), None)
    return first or _lineage_refusal(state, generation, ancestry, issue_number)


def _lineage_refusal(
    state: PinnedState, generation: LateGeneration, ancestry: _ancestry.LateAncestry, issue_number: int,
) -> str | None:
    """Why this issue's own late record names another lineage, or None.

    A record with no identity says nothing about a lineage. Without an
    ancestry the record is all that remains of where this issue sits, so it
    has to name this issue as a root at depth 0 -- anything else is a lineage
    whose ancestry was lost. With one, every record has to name its root,
    since every road that mints or rebuilds a descendant's cycle takes the
    root off it. Only a record that proves a split is held to its depth too,
    since the children it made were minted from both; a record that never
    split charged nothing, and a restarted cycle's depth of 0 is not a claim
    about the lineage.
    """
    if not generation.is_present:
        return None
    if ancestry.is_present:
        if _entitlement.split_evidence(generation, issue_number) is _entitlement.SplitEvidence.PROVED:
            return _lineage.contradicted_lineage(state, generation)
        rooted = generation.root_issue == ancestry.root_issue
        return None if rooted else _OTHER_ROOT.format(recorded=generation.root_issue, root=ancestry.root_issue)
    if (generation.root_issue, generation.lineage_depth) == (issue_number, 0):
        return None
    return _UNANCESTORED_LINEAGE.format(root=generation.root_issue, depth=generation.lineage_depth)
