# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Durable inherited lineage, its snapshot fields, and parent corroboration.

An issue retains ancestry after its own generation is retired. Each pinned
field is read fail-closed, and snapshot refs must belong to the snapshot
namespace. Parent corroboration checks the cycle, generation, and recorded
consumer before supplying the snapshot SHA. Wire keys and write omission
rules live here beside the reader that interprets them.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from orchestrator.git.snapshots import namespace as _namespace
from orchestrator.github.pinned_state import PinnedState
from orchestrator.workflow.late_split import ancestry as _ancestry, formats as _formats, payloads as _payloads
from orchestrator.workflow.late_split.models import LateGeneration

_ROOT_ISSUE = "late_ancestry_root_issue"
_DEPTH = "late_ancestry_depth"
_PARENT_ISSUE = "late_ancestry_parent"
_CYCLE_ID = "late_ancestry_cycle_id"
_GENERATION = "late_ancestry_generation"
_SNAPSHOT_REF = "late_ancestry_snapshot_ref"
_SNAPSHOT_SHA = "late_ancestry_snapshot_sha"
_MIRROR_FIRST = "late_ancestry_mirror_first"
_BASE_BRANCH = "late_ancestry_base_branch"
_SCOPE = "late_declared_scope"

LATE_ANCESTRY_KEYS = (
    _ROOT_ISSUE,
    _DEPTH,
    _PARENT_ISSUE,
    _CYCLE_ID,
    _GENERATION,
    _SNAPSHOT_REF,
    _SNAPSHOT_SHA,
    _MIRROR_FIRST,
    _BASE_BRANCH,
    _SCOPE,
)


def read_late_ancestry(state: PinnedState) -> _ancestry.LateAncestry:
    """Return the ancestry a pinned comment records for this issue.

    An issue that was never split into reads back as the defaults, which
    `is_present` answers False on -- the one reading that keeps every issue
    that reached this workflow another way out of every lineage decision
    without a migration.
    """
    return _ancestry.LateAncestry(
        root_issue=_payloads.as_identity(state.get(_ROOT_ISSUE)) or 0,
        lineage_depth=_payloads.as_depth(state.get(_DEPTH)),
        parent_issue=_payloads.as_identity(state.get(_PARENT_ISSUE)) or 0,
        cycle_id=_payloads.as_identity(state.get(_CYCLE_ID)) or 0,
        generation=_payloads.as_count(state.get(_GENERATION)) or 0,
        snapshot_ref=_snapshot_ref(state.get(_SNAPSHOT_REF)),
        snapshot_sha=_payloads.as_hex(
            state.get(_SNAPSHOT_SHA), _formats.COMMIT_LENGTHS,
        ) or "",
        mirror_first=_payloads.as_flag(state.get(_MIRROR_FIRST)),
        base_branch=_payloads.as_text(state.get(_BASE_BRANCH)) or "",
        scope=_payloads.as_text(state.get(_SCOPE)) or "",
    )


def write_late_ancestry(state: PinnedState, ancestry: _ancestry.LateAncestry) -> None:
    """Record one ancestry, replacing whatever ancestry keys were there.

    Every key is dropped first, so a field a caller cleared leaves no stale
    value for the next tick to read: a child re-seeded against a snapshot that
    no longer exists must not keep pointing at the old one. Keys outside this
    group are untouched -- the pinned comment is shared with every stage, and
    this write is only ever about its own fields.
    """
    clear_late_ancestry(state)
    for key, written in _written_fields(ancestry).items():
        state.set(key, written)


def clear_late_ancestry(state: PinnedState) -> None:
    """Drop every ancestry field, leaving the rest of the state alone."""
    for key in LATE_ANCESTRY_KEYS:
        state.data.pop(key, None)


def contradicted_lineage(
    state: PinnedState, generation: LateGeneration,
) -> str | None:
    """Why this generation's lineage disagrees with the ancestry, or None.

    The one production reading of an ancestry, and it is a refusal rather than
    a substitution. What a child's own generation is minted from is this
    record; if the two ever disagree, the generation was minted without it --
    and the failure that matters is the one that reads the child as shallower
    or rooted elsewhere than it is, which is exactly how a lineage buys itself
    another generation past the cap the bound exists to enforce.

    Refusing rather than correcting is deliberate. A generation whose depth
    was minted wrong has already been adjudicated under a prompt that told the
    agent how much room it had, so quietly deepening it here would act on a
    verdict nobody asked for at that depth. An issue with no recorded ancestry
    is a root and contradicts nothing.
    """
    ancestry = read_late_ancestry(state)
    if not ancestry.is_present:
        return None
    if ancestry.root_issue != generation.root_issue:
        return (
            f"it was created by issue #{ancestry.parent_issue} under root "
            f"#{ancestry.root_issue}, and the generation names root "
            f"#{generation.root_issue}"
        )
    if ancestry.lineage_depth != generation.lineage_depth:
        return (
            f"it was created at lineage depth {ancestry.lineage_depth}, and "
            f"the generation names depth {generation.lineage_depth}"
        )
    return None


def vouched_lineage(
    claimed: _ancestry.LateAncestry, consumer: int, generation: LateGeneration,
) -> _ancestry.LateAncestry | None:
    """The lineage a body claims, as the owner's own generation vouches for it.

    The body marker is the one lineage claim in this workflow that comes out
    of a field the world can write, and every other claim it competes with is
    authenticated: a pinned comment only this orchestrator writes, a receipt
    checked against its author. So it is corroborated rather than believed,
    and the record that corroborates it is the SPLIT's -- read from the owner
    the marker names, where nothing but this orchestrator writes.

    Three things have to agree, because each is a different way for a claim to
    be about something else: the cycle, the generation inside it, and the
    consumer list carrying this issue's number. A marker from another
    adjudication of the same owner, from another generation of the same cycle,
    or on an issue that owner never cut anything for fails one of them.

    What comes back is the whole pointer the failed seed never wrote -- the
    ref the identity mints and the commit the owner recorded preserving -- so
    a caller can ask whether THIS candidate is still obtainable rather than
    whether some ref is occupied. A record that vouches for the consumer and
    not for a commit answers None with the rest: half a pointer is not one.

    None is "this record does not vouch for that claim", which is not the same
    as "this record refutes it": a ledger nobody could read, or one whose
    consumers this binary cannot type, vouches for nothing either. The caller
    holds the record and can tell those apart, which is why it is passed in
    rather than read here.
    """
    if generation.cycle_id != claimed.cycle_id:
        return None
    if generation.generation != claimed.generation:
        return None
    if consumer not in generation.consumers:
        return None
    return replace(
        claimed.named_snapshot(), snapshot_sha=generation.candidate_sha,
    )


def _snapshot_ref(raw: Any) -> str:
    """Return a recorded snapshot ref, or "" unless it is one of ours.

    Checked against the namespace rather than for being a string, because what
    this field is FOR is telling a child which ref to fetch: a value outside
    the namespace names a branch, a tag, or nothing, and handing one to a
    child is worse than handing it none.
    """
    return raw if _namespace.is_snapshot_ref(raw) else ""


def _written_fields(ancestry: _ancestry.LateAncestry) -> dict[str, Any]:
    """Return the pinned fields this ancestry records, unset ones out.

    A field at its own empty value names itself None here and is dropped, so
    the pinned comment carries what the split actually knew. A lineage depth
    of 0 is not one of them: it is the root of a lineage and is written as
    itself, while an unknown depth is dropped -- a child whose depth nobody
    recorded may not read back as a root free to split again.
    """
    fields = {
        _ROOT_ISSUE: ancestry.root_issue or None,
        _DEPTH: ancestry.lineage_depth,
        _PARENT_ISSUE: ancestry.parent_issue or None,
        _CYCLE_ID: ancestry.cycle_id or None,
        _GENERATION: ancestry.generation or None,
        _SNAPSHOT_REF: ancestry.snapshot_ref or None,
        _SNAPSHOT_SHA: ancestry.snapshot_sha or None,
        _MIRROR_FIRST: ancestry.mirror_first or None,
        _BASE_BRANCH: ancestry.base_branch or None,
        _SCOPE: ancestry.scope or None,
    }
    return {
        key: written
        for key, written in fields.items()
        if written is not None
    }
