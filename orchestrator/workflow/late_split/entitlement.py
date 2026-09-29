# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""What a late record proves its own split made, and the snapshot it still holds.

Two readings the provenance of an ordinary decomposition asks of an issue's
late record before naming the lineage its replacement children inherit.

Whether the record's own split made children is proved only by what children
leave behind: the ordered register, or a consumer or child entry on the
ledgers. No phase proves one. `splitting` is written before the first child is
created, and `cleaning_up` is also where a cancelled cycle that created none is
rebuilt to; a caller that has to tell a split still in flight from a settled
one asks the phase for that and nothing more. A snapshot entry is not that
evidence either -- the ref is recorded before any child exists, so a split that
failed at the snapshot or ahead of its first child leaves one behind with
nothing cut from it -- and a ledger this binary cannot type may or may not name
a child. The flag a split raises once it has announced its children's links is
the opposite case: it says children were made and names none of them, so a
record carrying it beside no child record has lost which ones. Each of those
alone is ambiguous, which the caller refuses rather than reading as a split or
as none. And a child that is no other issue -- a child entry whose target is
not an issue number, or any entry naming the issue itself -- is evidence of
nothing but damage, which the caller refuses too.

The snapshot a proved split entitles a replacement child to is the one ref its
own identity mints, and only while the ledger names that ref exactly once and
at `retained`. The ledger reader carries every entry it could type, so a ref
recorded twice -- held in one entry and reconciled in another -- is a ledger
disagreeing with itself, and it entitles nothing. An issue whose record never
split offers the pointer its ancestry carries instead, and only where that
pointer is the ref the ancestry's own identity mints.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from orchestrator.git.snapshots import namespace as _namespace
from orchestrator.workflow.late_split import ancestry as _ancestry
from orchestrator.workflow.late_split.models import LateGeneration
from orchestrator.workflow.late_split.obligations import LateResourceKind, LateResourceState


class SplitEvidence(Enum):
    """What a late record proves about whether its own split made children."""

    NONE = "none"
    PROVED = "proved"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


def split_evidence(generation: LateGeneration, issue_number: int) -> SplitEvidence:
    """Whether this record's split made children, read off what it kept.

    The ledgers as well as the register, because the ledgers are the one part
    a retirement keeps once the identity is gone. A child that is no other
    issue is asked about first, since it would otherwise prove a split on its
    own; then what proves a child, so an unreadable ledger or an announcement
    beside a register that names real children is still a split.
    """
    obligations = generation.obligations
    kinds = {entry.kind for entry in obligations.resources}
    named = [
        _child_number(entry.target)
        for entry in obligations.resources
        if entry.kind == LateResourceKind.CHILD
    ]
    children = {*generation.split_children, *obligations.consumers, *named}
    if children & {None, issue_number}:
        return SplitEvidence.INVALID
    if children:
        return SplitEvidence.PROVED
    if obligations.is_opaque or generation.links_announced or LateResourceKind.SNAPSHOT_REF in kinds:
        return SplitEvidence.AMBIGUOUS
    return SplitEvidence.NONE


def _child_number(target: str) -> int | None:
    """The issue a child entry names, or None unless it spells one exactly.

    Exactly as the split writes it -- the decimal number and nothing else --
    so `"007"`, a digit from another script, and a sentence are all no issue.
    """
    number = int(target) if target.isdecimal() else 0
    return number if number > 0 and str(number) == target else None


@dataclass(frozen=True)
class SnapshotEntitlement:
    """One preserved candidate a replacement child may be pointed at.

    Named by the split that preserved it -- the owner, the cycle, and the
    generation -- because that split's consumer ledger is what keeps the ref
    on the remote, and a pointer handed out without a consumer recorded there
    is one a reclamation may take out from under the child.
    """

    owner_issue: int
    cycle_id: int
    generation: int
    snapshot_ref: str
    snapshot_sha: str
    mirror_first: bool

    @classmethod
    def for_replacements(
        cls, generation: LateGeneration, ancestry: _ancestry.LateAncestry, issue_number: int,
    ) -> SnapshotEntitlement | None:
        """The snapshot this issue's replacement children could be pointed at.

        An issue that split itself answers with its own split's snapshot or
        with none: its ancestry's pointer is an earlier candidate than the one
        the replaced children were cut from. One whose split is ambiguous
        answers with none either way.
        """
        evidence = split_evidence(generation, issue_number)
        if evidence is SplitEvidence.PROVED:
            return cls.preserved_by(generation, issue_number)
        if evidence is SplitEvidence.NONE:
            return cls.inherited_from(ancestry)
        return None

    @classmethod
    def preserved_by(cls, generation: LateGeneration, issue_number: int) -> SnapshotEntitlement | None:
        """The snapshot this issue's own split still holds, or None.

        Held means the ledger's one entry for the ref this generation's
        identity mints is `retained`: proved at the candidate and kept on
        purpose. A pending or failed entry was never proved, a reclaiming or
        reconciled one is on its way out, a second entry for the same ref
        contradicts the first, and an opaque ledger is one nobody can add the
        next consumer to -- so none of them entitles anything.
        """
        if not generation.candidate_sha or generation.obligations.is_opaque:
            return None
        try:
            ref = _namespace.snapshot_ref(
                issue_number=issue_number, cycle_id=generation.cycle_id, generation=generation.generation,
            )
        except _namespace.InvalidSnapshotRef:
            return None
        recorded = tuple(
            entry.resource_state
            for entry in generation.obligations.resources
            if (entry.kind, entry.target) == (LateResourceKind.SNAPSHOT_REF, ref)
        )
        if recorded != (LateResourceState.RETAINED,):
            return None
        return cls(
            owner_issue=issue_number,
            cycle_id=generation.cycle_id,
            generation=generation.generation,
            snapshot_ref=ref,
            snapshot_sha=generation.candidate_sha,
            mirror_first=True,
        )

    @classmethod
    def inherited_from(cls, ancestry: _ancestry.LateAncestry) -> SnapshotEntitlement | None:
        """The pointer this issue's ancestry carries, or None.

        Both halves or none, and the ref has to be the one the ancestry's own
        split identity mints: a pointer at another split's ref is protected by
        a ledger this lineage never recorded a consumer on. An identity no ref
        can be minted from names no ref at all, so it entitles nothing rather
        than vouching for whatever pointer stands beside it.
        """
        if not ancestry.has_snapshot:
            return None
        try:
            minted = _namespace.snapshot_ref(
                issue_number=ancestry.parent_issue, cycle_id=ancestry.cycle_id, generation=ancestry.generation,
            )
        except _namespace.InvalidSnapshotRef:
            return None
        if minted != ancestry.snapshot_ref:
            return None
        return cls(
            owner_issue=ancestry.parent_issue,
            cycle_id=ancestry.cycle_id,
            generation=ancestry.generation,
            snapshot_ref=ancestry.snapshot_ref,
            snapshot_sha=ancestry.snapshot_sha,
            mirror_first=ancestry.mirror_first,
        )
