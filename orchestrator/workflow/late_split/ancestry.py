# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Frozen inherited ancestry and the child and release receipt identities.

An ancestry describes the split that created an issue. Snapshot transforms
return a new record, and a body supplies lineage only when it carries one
well-formed child receipt. The persisted key reader lives on lineage.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

from orchestrator.git.snapshots import namespace as _namespace


@dataclass(frozen=True)
class LateAncestry:
    """Where one issue came from, when it came from a late split.

    Frozen for the reason the generation is: every field is evidence a later
    tick acts on rather than re-derives. The snapshot the child reuses, the
    depth its own splitting is bounded by, and the adjudication its records
    correlate to are all facts about an event that has already happened.
    """

    root_issue: int = 0
    lineage_depth: int | None = None
    parent_issue: int = 0
    cycle_id: int = 0
    generation: int = 0
    snapshot_ref: str = ""
    snapshot_sha: str = ""
    mirror_first: bool = False
    base_branch: str = ""
    scope: str = ""

    @property
    def is_present(self) -> bool:
        """Whether this issue was born of a late split at all."""
        return self.parent_issue > 0 and self.cycle_id > 0

    @property
    def trusts_the_mirror(self) -> bool:
        """Whether a surviving local copy of the ref proves anything here.

        False for every pointer written before the reclamation put this
        host's copy ahead of the remote ref, and that is not a detail of an
        upgrade: an orchestrator that deleted the remote first and dropped the
        mirror afterwards could leave a copy standing beside a ref that is
        gone, which is exactly the world the shortcut would misread. The
        stamp is what separates the two, and an unstamped ancestry pays one
        read-only ask instead.
        """
        return self.mirror_first and self.has_snapshot

    @property
    def has_snapshot(self) -> bool:
        """Whether a usable pointer to the preserved candidate survived.

        Both halves or neither: a ref with no commit beside it cannot be
        verified against anything, and a commit with no ref names work nothing
        can fetch. A child that reads False here has lost the artifact it was
        meant to reuse, which is a thing to say out loud rather than to
        reconstruct.
        """
        return bool(self.snapshot_ref) and bool(self.snapshot_sha)

    def named_snapshot(self) -> LateAncestry:
        """This lineage with the snapshot ref its own identity names.

        The one fact a child whose ancestry write never landed can still
        recover about the ref it was cut from. The name is minted from the
        owner, the cycle, and the generation -- all three of which its BODY
        marker carries -- so re-deriving it here re-reads a fact rather than
        inventing one, and it is the same derivation the reclamation holds its
        own ledger to before it deletes anything.

        The COMMIT is not recoverable that way and stays empty: what the
        failed write was carrying is exactly what nobody wrote down. So what
        comes back still answers `has_snapshot` False, which is what keeps it
        out of every reading that needs the pair -- `vouched_lineage` is where
        the missing half comes from, and it comes from the owner's own record
        rather than from anything this issue says about itself.

        An identity that cannot produce a ref comes back unchanged -- a body
        edited into nonsense names no snapshot for anyone to ask about.
        """
        try:
            derived = _namespace.snapshot_ref(
                issue_number=self.parent_issue,
                cycle_id=self.cycle_id,
                generation=self.generation,
            )
        except _namespace.InvalidSnapshotRef:
            return self
        return replace(self, snapshot_ref=derived)

    def without_snapshot(self) -> LateAncestry:
        """The same lineage with the pointer to the candidate dropped.

        What a child is left with once the ref it named is one it may not use.
        The lineage itself survives -- which split made this issue, how deep it
        is, and what slice it owns are still true -- and only the pair that
        says "fetch this" goes, because an ancestry that goes on naming an
        unusable ref is one every later reader would follow.
        """
        return replace(self, snapshot_ref="", snapshot_sha="")


# Stamped into every child's body so the create that returned into a crash can
# be recognized again. It names the ISSUE as well as the adjudication and the
# slice, because a cycle identity is minted per issue and repeats across them:
# two parents adjudicating their first candidate are both cycle 1, generation
# 1, and their first slices would otherwise carry the same marker -- while the
# lookup that reads it is scoped to no parent at all, walking the repository's
# issues in every state and under no label, so one parent would adopt, reseed,
# and activate the other's child. An HTML comment, so it is invisible in the
# rendered issue.
#
# It lives beside the ancestry rather than with the transaction that writes it
# because it is the only durable record of a child's lineage the split writes
# OUTSIDE the pinned comment -- which is what makes it readable when the pinned
# write that would have recorded the same thing never landed. The prefix is its
# own name because two readings need it: the marker is built from it, and a
# candidate the orphan lookup returns is checked for carrying exactly one.
CHILD_RECEIPT = "<!--orchestrator-late-child:"

_CHILD_MARKER = CHILD_RECEIPT + (
    "issue={issue}:cycle={cycle}:generation={generation}:index={index}-->"
)

_CHILD_LINEAGE = re.compile(
    r"<!--orchestrator-late-child:"
    r"issue=(?P<issue>\d+):cycle=(?P<cycle>\d+):"
    r"generation=(?P<generation>\d+):index=\d+-->",
)


def child_marker(
    *, issue: int, cycle: int, generation: int, index: int,
) -> str:
    """The hidden marker naming one child's issue, adjudication, and slice."""
    return _CHILD_MARKER.format(
        issue=issue, cycle=cycle, generation=generation, index=index,
    )


def child_lineage(body: Any) -> LateAncestry | None:
    """The lineage a child's own body claims, or None when it claims none.

    The one reading of a child that costs nothing and survives everything. A
    split records a child on the parent's ledger BEFORE it seeds that child's
    ancestry -- a child on GitHub the parent does not record is a child
    nothing would come back to -- so the window between the two is durable:
    an ancestry write that failed leaves an issue whose BODY says which split
    made it and whose pinned comment says nothing at all.

    Identity only. The snapshot the child was pointed at is not in the marker,
    and deriving it here would be inventing a fact the failed write is exactly
    what did not record. What this answers is "whose child is this", which is
    all a receipt has to be matched against.

    A body carrying two receipts answers no. That is an issue an older binary
    created or a human edited, and a lineage read off one of two claims is a
    lineage nothing vouches for.
    """
    if not isinstance(body, str) or body.count(CHILD_RECEIPT) != 1:
        return None
    claimed = _CHILD_LINEAGE.search(body)
    if claimed is None:
        return None
    return LateAncestry(
        parent_issue=int(claimed.group("issue")),
        cycle_id=int(claimed.group("cycle")),
        generation=int(claimed.group("generation")),
    )


# The receipt one reclamation leaves on each child it was preserved for. It
# lives beside the ancestry because both ends key it the same way and neither
# may guess: the reclamation writes it from the generation it is settling, and
# the child reads it back from the lineage it was born with.
_RELEASE_MARKER = (
    "<!--orchestrator-late-release owner={owner} cycle={cycle} "
    "generation={generation}-->"
)


def release_marker(*, owner: int, cycle: int, generation: int) -> str:
    """The hidden marker a reclamation's receipt on one child carries.

    Named by the owner, the cycle, and the generation together, because none
    of the three is enough on its own: an issue splits more than once, a cycle
    holds more than one generation, and a child of a later reclamation must
    not read an earlier one's receipt as its own.

    It is a claim nothing can lose. A pinned comment is rewritten whole by
    whoever writes it, so a record left there can be undone by a writer the
    author cannot see; a comment is appended, and the reclamation that reached
    a child stays reached.
    """
    return _RELEASE_MARKER.format(
        owner=owner, cycle=cycle, generation=generation,
    )
