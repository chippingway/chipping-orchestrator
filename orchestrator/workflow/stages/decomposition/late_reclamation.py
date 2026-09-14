# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Select owed cleanup work and retain the attempted and changed resource entries.

Every obligation is preceded by the close barrier. Branch reclamation
also requires the publication to remain superseded, and unchanged failures
remain distinguishable from state changes that require a pinned write.
"""
from __future__ import annotations

import logging

from orchestrator.workflow.late_split.models import (
    LateGeneration,
    LateResource,
    LateResourceKind,
)
from orchestrator.workflow.stages.decomposition import (
    late_branch_reclamation as _late_branch_reclamation,
    late_cleanup_proof as _late_cleanup_proof,
    late_cleanup_reading as _late_cleanup_reading,
    late_cleanup_state as _late_cleanup_state,
    late_publication as _late_publication,
    late_snapshot_reclamation as _late_snapshot_reclamation,
)

log = logging.getLogger("orchestrator.workflow")


# What is logged where a branch is owed and the change it was superseded under
# is open again. Said on every visit that holds, for the reason the held
# terminal is: a reclamation that will not happen and never says why is the
# one shape an operator cannot act on.
_HELD_BACK_BRANCH = (
    "issue=#%d %s, so branch %s was left on the ledger rather than deleted "
    "out from under a change that points at it"
)


def _asked_of(
    walk: _late_cleanup_state._Pass, generation: LateGeneration,
) -> tuple[tuple[LateResourceKind, str], ...]:
    """What this pass will ask the remote about, in the order it asks.

    A branch is asked about whenever it is owed. A snapshot is asked about
    once every recorded direct consumer is proved ended -- the rule that owns
    it -- or, past that proof, only for a ref the remote no longer has.

    Nothing at all while the RESOURCE ledger is opaque. The typed view is a
    projection of the entries this binary could read, and the write puts the
    verbatim copy back -- so a reclamation recorded against that view would be
    dropped at the next write and asked for again forever.

    An opaque CONSUMER ledger stops only what it is about. It is the thing a
    snapshot's proof is taken from, so no ref may be reclaimed while it cannot
    be read -- but a branch owes no consumer anything, and freezing the two
    together would leave a superseded branch on the remote for as long as a
    hand-edited consumer list stayed hand-edited. The two are preserved and
    written independently, and they are refused independently here.
    """
    if _late_cleanup_reading._unwritable(generation):
        return ()
    owed = tuple((_late_cleanup_state._BRANCH, target) for target in _late_cleanup_reading._owed_branches(generation))
    return owed + tuple(
        (_late_cleanup_reading._SNAPSHOT, target) for target in _asked_snapshots(walk, generation)
    )


def _asked_snapshots(
    walk: _late_cleanup_state._Pass, generation: LateGeneration,
) -> tuple[str, ...]:
    """The held refs this pass may act on, and what qualifies each of them.

    Every held ref qualifies once the consumers are proved ended, which is the
    rule that owns the snapshot.

    Past that proof there is exactly one more way in, and it is narrow on
    purpose. An entry reading `reclaiming` or `failed` records a decision that
    was taken against a proof, and half of what a retry has to finish is not
    repeatable: the ledger may be behind a delete that already landed, and a
    child told against it, while the consumers a fresh reading finds are
    whoever a human has reopened since. So the ref itself is asked about
    first, and the entry qualifies only if the remote no longer has it. A ref
    the remote still holds is a ref a reopened consumer may still be cutting
    from -- and the decision to take it, however durably recorded, does not
    outrank the reading in front of it.
    """
    if _late_cleanup_proof._reclaimable(walk.state, generation, walk.scan):
        return _late_cleanup_reading._held_snapshots(generation)
    return tuple(
        entry.target
        for entry in generation.resources
        if entry.kind == _late_cleanup_reading._SNAPSHOT
        and entry.resource_state in _late_snapshot_reclamation._ORDERED
        and _late_snapshot_reclamation._already_gone(walk, generation, entry.target)
    )


def _reclaimed(walk: _late_cleanup_state._Pass, generation: LateGeneration) -> _late_cleanup_state._Reclamation:
    """Settle everything this issue owes that can be settled right now.

    The latch is asked between the obligations rather than once for the pass,
    because each of them is a request -- a branch delete, then a ref delete
    with a receipt on every child cut from it -- and a poll can observe the
    close between any two. What the mark changes is not WHETHER the rest is
    settled (a cancellation buys no shortcut through the reclamation rules)
    but what the settling owes anybody: a cancelled cycle tells its consumers
    nothing, and its owner takes no terminal until its own ending has run.
    """
    settled = generation
    acted = []
    for owed in _asked_of(walk, generation):
        settled = _late_cleanup_state._observed_close(walk, settled)
        reclaimed = _reclaimed_one(walk, settled, *owed)
        if reclaimed is not None:
            settled = reclaimed
            acted.append(owed)
    entries = _settled_entries(settled, tuple(acted))
    return _late_cleanup_state._Reclamation(
        generation=settled,
        entries=entries,
        moved=_moved_entries(generation, entries),
    )


def _reclaimed_one(
    walk: _late_cleanup_state._Pass,
    generation: LateGeneration,
    kind: LateResourceKind,
    target: str,
) -> LateGeneration | None:
    """Settle one obligation, or None where this pass may not touch it.

    The branch is the one that can be refused here, and it is refused HERE
    rather than where the work list was assembled because of what stands
    between the two: the snapshot rule may spend a remote probe deciding
    whether an ordered ref is already gone, and a human can reopen the pull
    request inside it. An answer good enough to build a list with is not one
    good enough to delete on.

    What it protects is the one act on this pass nothing could undo. A split
    closed that pull request and this delete is what takes its branch away, so
    a human who reopened it has a change pointing at a ref this would remove
    out from under them. The record is what still names it: the retirement
    keeps the publication group for exactly this.

    Declined rather than recorded `failed`, and the difference matters.
    Nothing was attempted, so there is nothing to report and nothing to write;
    the entry stays owed, which holds the umbrella's terminal open, and the log
    line is what says why. A `failed` entry would claim a delete that never
    went out.
    """
    if kind != _late_cleanup_state._BRANCH:
        return _late_snapshot_reclamation._reclaim_snapshot(walk, generation, target)
    undone = _late_publication._publication_undone(
        walk.gh, walk.issue, generation,
    )
    if undone:
        log.error(_HELD_BACK_BRANCH, walk.issue.number, undone, target)
        return None
    return _late_branch_reclamation._reclaim_branch(
        walk.gh, walk.spec, walk.issue.number, generation, target,
    )


def _settled_entries(
    generation: LateGeneration,
    asked: tuple[tuple[LateResourceKind, str], ...],
) -> tuple[LateResource, ...]:
    """What the record now says about each obligation this pass acted on.

    Read back off the record rather than inferred from what the remote said,
    because the two are not the same claim: a delete that landed while a
    child could not be told leaves a ref that is gone and an obligation
    that is not, and the entry is the only thing that carries both.
    """
    recorded = {
        (entry.kind, entry.target): entry for entry in generation.resources
    }
    return tuple(recorded[owed] for owed in asked if owed in recorded)


def _moved_entries(
    before: LateGeneration, entries: tuple[LateResource, ...],
) -> tuple[LateResource, ...]:
    """The acted-on obligations whose recorded state this visit changed.

    Asked against the record the pass OPENED with, so what counts as movement
    is what a reader of the ledger would see happen -- a first attempt, a
    refusal that became a reclamation, a reclamation a reopened consumer put
    back. A retry that reaches the same answer moves nothing, and there is
    nothing about it a second record could say that the first did not.
    """
    was = {
        (entry.kind, entry.target): entry.resource_state
        for entry in before.resources
    }
    return tuple(
        entry for entry in entries
        if was.get((entry.kind, entry.target)) != entry.resource_state
    )
