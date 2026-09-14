# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Remote and local branch removal at the commits a verdict proved.

A complete checkout listing gates branch deletion; each transport rechecks
the expected tip, and any refusal stops the remaining candidate actions."""
from __future__ import annotations

from orchestrator.git.worktrees import (
    candidates as _candidates,
    checkout_listing as _checkout_listing,
    maintenance_results as _maintenance_results,
    models as _models,
    reclaim,
    tip_evidence as _tip_evidence,
)


def _take_remote_branch(
    candidate: _candidates.MaintenanceCandidate, branch: str, proven: str,
) -> _maintenance_results.MaintenanceResult | None:
    """Take one branch off the remote, or say why the pass stops here.

    The remote is asked what it carries before the delete is sent, so the three
    answers stay apart: a branch that is not there is a step already done -- the
    ordinary shape of a merged pull request's head -- a branch at another commit
    is a push nobody here cleared, and a reading that failed is not permission
    to delete anything.

    The delete itself is leased to the same commit, so the answer above is not
    what the deletion rests on: between this read and that push the branch can
    move again, and the remote is what refuses it then.
    """
    spec = candidate.artifacts.spec
    published = _tip_evidence._published_tip(spec, branch)
    if published.answer is _models.ProbeAnswer.UNREADABLE:
        return _maintenance_results._answered(candidate, _maintenance_results.MaintenanceReason.TIP_UNREADABLE, branch)
    if published.answer is _models.ProbeAnswer.REFUTED:
        return None
    if published.sha != proven:
        return _maintenance_results._answered(candidate, _maintenance_results.MaintenanceReason.TIP_MOVED, branch)
    if reclaim._delete_remote_branch_at(spec, branch, proven):
        return None
    return _maintenance_results._answered(
        candidate, _maintenance_results.MaintenanceReason.REMOTE_DELETE_FAILED, branch,
    )


def _take_local_branch(
    candidate: _candidates.MaintenanceCandidate, branch: str, proven: str,
) -> _maintenance_results.MaintenanceResult | None:
    """Take one branch out of the clone, or say why the pass stops here.

    Reached only once the remote's copy is gone, which is what keeps a failed
    pass discoverable: the local ref is the cheapest thing the next discovery
    finds, so it is the last artifact of a candidate to go.

    A branch the clone no longer has is a step already done. Anything else is
    put to the pinned delete, which refuses the branch that has moved -- the
    reading here only decides whether there is a deletion to attempt at all.
    """
    spec = candidate.artifacts.spec
    tip = _tip_evidence._local_branch_tip(spec, branch)
    if tip.answer is _models.ProbeAnswer.REFUTED:
        return None
    if tip.answer is _models.ProbeAnswer.UNREADABLE:
        return _maintenance_results._answered(candidate, _maintenance_results.MaintenanceReason.TIP_UNREADABLE, branch)
    if tip.sha != proven:
        return _maintenance_results._answered(candidate, _maintenance_results.MaintenanceReason.TIP_MOVED, branch)
    if reclaim._delete_local_ref_at(spec, branch, proven):
        return None
    return _maintenance_results._answered(candidate, _maintenance_results.MaintenanceReason.LOCAL_DELETE_FAILED, branch)


def _take_branches(
    candidate: _candidates.MaintenanceCandidate, cleared: dict[str, str],
) -> _maintenance_results.MaintenanceResult | None:
    """Take every cleared branch of this candidate, in the order it was named.

    Each branch goes remote-side first and then locally, rather than every
    remote and then every local, so a candidate carrying both layouts leaves
    one whole branch behind rather than two half-taken ones when a pass stops.

    A branch nothing cleared ENDS the pass rather than being passed over. It
    is a branch the discovery named and the classification found on neither
    host, so nothing about it was established -- and a name that is gone at one
    reading can be back at the next, pushed by a run this pass never saw. The
    candidate is kept, which costs one more pass of an artifact that has really
    gone: the next discovery does not name it, and that pass reports the rest
    cleaned.

    Which branches some tree of this clone is still standing on is read once
    here, after every checkout of this candidate has come down and before any
    branch goes. It is read at all because the plumbing delete does not ask:
    `branch -D` refuses a branch a worktree is on and `update-ref -d` takes it
    without a word, leaving that tree holding a HEAD nothing resolves. The
    trees that can be on it are not only this candidate's -- an operator's own
    `worktree add` is on the branch just as squarely, and so is a checkout this
    scan could not attribute.

    The first stop ends the candidate. What is left is exactly what the next
    discovery finds, and going on past a refusal would spend deletions on a
    host that has just said it is not in the state anybody read.
    """
    standing = _checkout_listing._checked_out_branches(candidate.artifacts.spec)
    for branch in candidate.artifacts.branches:
        stopped = _take_branch(candidate, branch, cleared, standing)
        if stopped is not None:
            return stopped
    return None


def _take_branch(
    candidate: _candidates.MaintenanceCandidate,
    branch: str,
    cleared: dict[str, str],
    standing: frozenset[str] | None,
) -> _maintenance_results.MaintenanceResult | None:
    """Take one branch off both hosts, or say why the pass stops on it.

    A listing that could not be taken keeps the branch, as every unread
    question here does: without it nothing establishes that no tree is standing
    on the ref about to be deleted.
    """
    proven = cleared.get(branch)
    if proven is None:
        return _maintenance_results._answered(candidate, _maintenance_results.MaintenanceReason.TIP_UNREADABLE, branch)
    if standing is None:
        return _maintenance_results._answered(candidate, _maintenance_results.MaintenanceReason.TIP_UNREADABLE, branch)
    if branch in standing:
        return _maintenance_results._answered(
            candidate, _maintenance_results.MaintenanceReason.BRANCH_CHECKED_OUT, branch,
        )
    return (
        _take_remote_branch(candidate, branch, proven)
        or _take_local_branch(candidate, branch, proven)
    )
