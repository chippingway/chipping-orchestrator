# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Checkout removal after re-reading the identity and the exact commit the verdict cleared.

Both are checked immediately before removal. A checkout no longer proven the
issue's own -- switched onto another branch, or reached through a symlink --
and a moved or unreadable HEAD each stop the candidate before any remaining
artifact can be touched."""
from __future__ import annotations

from pathlib import Path

from orchestrator.git.worktrees import (
    candidates as _candidates,
    evidence,
    maintenance_results as _maintenance_results,
    models as _models,
    reclaim,
    tip_evidence as _tip_evidence,
)


def _checkout_stop(
    artifacts: _candidates.IssueArtifacts, worktree: Path, proven: str | None,
) -> _maintenance_results.MaintenanceReason | None:
    """Whether the checkout is still the issue's own, on the commit that was cleared.

    The last readings before the tree comes down. The identity is read again
    because the classification's reading of it is seconds old: a checkout
    switched onto the flat branch, or onto any other, at the very commit that
    was proved -- or a path swapped for a symlink to another tree -- carries
    the same commit and is no longer the issue's checkout, so it is answered
    as an artifact that moved. The commit is read because a linked worktree
    holds its HEAD and reflog on its own, so removing it takes whatever that
    HEAD names -- and between the proof and here, an agent committing moves it
    to something nobody cleared.

    A candidate with no proof for its checkout is refused rather than removed.
    An eligible verdict always carries one, so reaching this means the two
    halves disagree, and the only safe reading of that is that nothing was
    established.
    """
    identity = evidence._checkout_identity(artifacts.spec, artifacts.issue_number, worktree)
    if identity is _models.ProbeAnswer.REFUTED:
        return _maintenance_results.MaintenanceReason.TIP_MOVED
    if identity is not _models.ProbeAnswer.CONFIRMED:
        return _maintenance_results.MaintenanceReason.TIP_UNREADABLE
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

    Only the checkout the scan reported is taken: the issue's own
    per-repository one. A flat checkout an earlier layout left is no
    candidate's, so it stays on disk for manual disposition.
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
    stopped = _checkout_stop(candidate.artifacts, worktree, cleared.get(str(worktree)))
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
