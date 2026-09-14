# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""The identities a late generation is keyed by, and the content it re-reads.

Two kinds of identity sit together because both answer "is this the same thing
the last tick was working on". The monotonic pair -- a cycle and a generation
-- never repeats a number, so an audit record, a child's lineage, and a
restarted issue's predecessor link all name one attempt and only ever move
forward; the local fingerprints answer the same question about human content,
so a title/body edit and a trusted answer arriving after the late baseline are
told apart from each other rather than collapsed into one "something changed".

The fingerprints are deliberately local. The global `user_content_hash` on
`workflow/engine/drift.py` keeps its meaning and its single baseline; these
hash smaller inputs the late gate chooses -- the title and body alone, and the
trusted comment bodies a watermark the generation carries covers -- so reading
one of them tells the late coordinator WHICH kind of guidance arrived. Which
content goes in is the caller's; both digests are taken here, so one contract
has one implementation. The hashing discipline is the drift owner's: SHA-256
over the parts joined by a NUL, which no comment body can contain, so two
pieces of content cannot be concatenated into a third that hashes the same.

The lineage bound is enforced here at the one place a child's depth is
computed. `MAX_LINEAGE_DEPTH` is the record's invariant, so a caller asking
for a depth past it -- or for one off a generation whose own depth could not
be read -- gets `LineageDepthExceeded` rather than a number that would
silently create a fourth generation.

`resource_fingerprint` is the third identity here, and the only one written
into telemetry: an external resource's own name (a ref, a branch, an issue) is
not something a record may carry, but two cleanups of two different children
still have to be told apart from one cleanup retried. A bounded digest over
the entry's kind and target answers both -- stable across retries of the same
resource, distinct between two of the same kind, and carrying none of the name
it was taken over.
"""
from __future__ import annotations

import hashlib
from collections.abc import Iterable

from orchestrator.workflow.late_split import formats as _formats
from orchestrator.workflow.late_split.models import MAX_LINEAGE_DEPTH
from orchestrator.workflow.late_split.obligations import LateResource

# How much of the digest a telemetry record carries. Long enough that two
# resources of one generation cannot collide in practice, short enough to stay
# a bounded label rather than a second identifier of its own.
RESOURCE_FINGERPRINT_LENGTH = 12


class LineageDepthExceeded(Exception):
    """A child was asked for at or past `MAX_LINEAGE_DEPTH`."""


def next_identity(current: int | None) -> int:
    """Return the next value of a monotonic identity.

    One helper for both the cycle and the generation, because they are the
    same contract: an absent, non-positive, or unreadable predecessor starts
    at 1, and every other predecessor is followed by exactly one more. Nothing
    reuses a number, so a record naming cycle 2 always names the same attempt.

    A predecessor that is not a whole number is not one this ever counted, so
    it starts the sequence rather than being converted into a number nothing
    wrote -- `True` is not cycle 1, and 2.9 is not cycle 2.
    """
    previous = current if _formats.whole_number(current) else 0
    return max(previous, 0) + 1


def child_lineage_depth(depth: int | None) -> int:
    """Return the depth a child of a generation at `depth` is born at.

    Raises `LineageDepthExceeded` at the bound rather than returning a fourth
    generation's depth: an indivisible oversized child at the cap has to
    resolve as one change or ask a human, and that is the only outcome this
    refusal leaves. A depth that is unknown, or not a whole number at all,
    raises for the same reason -- a lineage that cannot say how deep it is
    cannot show it has room, and 2.5 is not a depth that may become 3.5.
    """
    if not _formats.whole_number(depth) or not 0 <= depth < MAX_LINEAGE_DEPTH:
        raise LineageDepthExceeded(
            f"lineage depth {depth} may not split; "
            f"the bound is {MAX_LINEAGE_DEPTH}",
        )
    return depth + 1


def title_body_fingerprint(title: str, body: str) -> str:
    """Return the fingerprint of an issue's declared scope as humans wrote it.

    Title and body only: this is the half of human content that redefines what
    the frozen candidate was supposed to be, and an edit to it parks the
    generation instead of resuming adjudication.
    """
    return _digest((title, body))


def comment_fingerprint(bodies: Iterable[str]) -> str:
    """Return the fingerprint of the trusted conversation a baseline covers.

    Paired with the watermark the generation carries, which names the last
    comment counted into it: a fingerprint that moved without that watermark
    moving means a comment already folded in was rewritten or deleted, which
    is a change to the requirements with no new comment to read it out of.
    Which bodies those are is the caller's to decide -- this owner is what a
    fingerprint IS, so the two the late gate keeps cannot drift apart in how
    they are taken.
    """
    return _digest(tuple(bodies))


def resource_fingerprint(resource: LateResource) -> str:
    """Return a bounded, name-free identifier for one ledger entry.

    Taken over the kind as well as the target so two entries that happen to
    share a target string -- a branch and a ref spelled the same -- are still
    two resources, and truncated because a telemetry record needs to tell them
    apart rather than to reconstruct either.
    """
    digest = _digest((str(resource.kind), resource.target))
    return digest[:RESOURCE_FINGERPRINT_LENGTH]


def _digest(parts: tuple[str, ...]) -> str:
    """SHA-256 over the parts joined by a separator none of them can hold."""
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()
