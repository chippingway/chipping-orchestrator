# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Checkout removal after re-reading the exact commit the verdict cleared.

The proven tip is checked immediately before removal. A moved or unreadable
HEAD stops the candidate before any remaining artifact can be touched."""
from __future__ import annotations

from pathlib import Path

from orchestrator.git.worktrees import (
    candidates as _candidates,
    maintenance_results as _maintenance_results,
    models as _models,
    reclaim,
    tip_evidence as _tip_evidence,
)


def _checkout_stop(
    worktree: Path, proven: str | None,
) -> _maintenance_results.MaintenanceReason | None:
    """Whether the checkout is still standing on the commit that was cleared.

    The last reading before the tree comes down, and it is about the commit
    rather than the tree: a linked worktree holds its HEAD and reflog on its
    own, so removing it takes whatever that HEAD names -- and between the proof
    and here, an agent committing moves it to something nobody cleared.

    A candidate with no proof for its checkout is refused rather than removed.
    An eligible verdict always carries one, so reaching this means the two
    halves disagree, and the only safe reading of that is that nothing was
    established.
    """
    tip = _tip_evidence._checkout_tip(worktree)
    if proven is None or tip.answer is not _models.ProbeAnswer.CONFIRMED:
        return _maintenance_results.MaintenanceReason.TIP_UNREADABLE
    if tip.sha != proven:
        return _maintenance_results.MaintenanceReason.TIP_MOVED
    return None


def _take_checkouts(
    candidate: _candidates.MaintenanceCandidate, cleared: dict[str, str],
) -> _maintenance_results.MaintenanceResult | None:
    """Take every checkout of this candidate down, or say where the pass stops.

    None is the step being done -- every tree removed, or none of them there in
    the first place -- and a result is the pass ending on one of them. They all
    run before any branch because git refuses to delete a branch a worktree
    still has checked out, so a pass that took the branches first would leave
    the trees standing and the branches beside them undeletable.

    Both layouts are taken, in the order the scan reported them. An issue that
    was in flight when slug namespacing landed can be sitting in the flat
    checkout it started in and the per-repository one the next tick made, and a
    pass that took only one of them would report the issue cleaned with a tree
    still on disk that nothing would ever discover again.
    """
    for worktree in candidate.artifacts.worktrees:
        stopped = _take_checkout(candidate, worktree, cleared)
        if stopped is not None:
            return stopped
    return None


def _take_checkout(
    candidate: _candidates.MaintenanceCandidate,
    worktree: Path,
    cleared: dict[str, str],
) -> _maintenance_results.MaintenanceResult | None:
    """Take one checkout down, or say why the pass stops on it."""
    stopped = _checkout_stop(worktree, cleared.get(str(worktree)))
    if stopped is not None:
        return _maintenance_results._answered(candidate, stopped, str(worktree))
    removed = reclaim._remove_recognized_worktree(
        candidate.artifacts.spec, worktree,
    )
    if removed:
        return None
    return _maintenance_results._answered(
        candidate, _maintenance_results.MaintenanceReason.WORKTREE_REMOVAL_FAILED, str(worktree),
    )
