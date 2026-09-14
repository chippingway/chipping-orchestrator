# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Settle a cancelled cycle's pull request, branches, snapshots, and child receipts.

The preserved publication is settled before adopting an unrecorded branch
obligation. Snapshot cleanup uses a fresh consumer scan, and publication
proof is repeated after the remaining obligations have been discharged.
"""
from __future__ import annotations

import logging

from github.Issue import Issue

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github import (
    client as _client,
    pinned_state as _pinned_state,
)
from orchestrator.workflow.late_split import (
    models as _late_models,
    obligations as _obligations,
)
from orchestrator.workflow.stages.decomposition import (
    late_cancellation_pr as _late_cancellation_pr,
    late_cancellation_reading as _late_cancellation_reading,
    late_cancellation_state as _late_cancellation_state,
    late_cleanup as _late_cleanup,
    late_cleanup_reading as _late_cleanup_reading,
    late_cleanup_state as _late_cleanup_state,
)
from orchestrator.workflow.stages.decomposition.models import _ChildScan

log = logging.getLogger("orchestrator.workflow")


_BRANCH = _obligations.LateResourceKind.BRANCH


def _reconciled(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Settle everything one cancelled cycle owes that can be settled now.

    The order is the contract. The cancellation is durable before any external
    call, so nothing below can happen against a record that does not already
    say the cycle is over; the held pull request is settled before the branch
    and the ref, because it is the only obligation here a human is still
    looking at.

    Every step is idempotent, and each is skipped where the record already
    says what this visit would say -- so the pass a refusal keeps bringing
    back costs only the obligations that are actually still owed.

    And the held pull request is asked once more at the end, because the
    steps between the two asks are a branch delete, a ref delete, and a
    consumer read apiece -- long enough for a human to reopen it inside them.
    """
    marked = _late_cancellation_state._marked(gh, issue, state, generation)
    reconciled = _late_cancellation_pr._plan_pr_settled(gh, issue, state, marked)
    owed = _superseded_branch(gh, spec, issue, state, reconciled)
    scan = _proof_scan(gh, issue, owed)
    settled = _late_cleanup._settle(gh, spec, issue, state, scan)
    return _late_cancellation_pr._reverified(
        gh, issue, state, _children_discharged(gh, issue, state, settled),
    )


def _children_discharged(
    gh: _client.GitHubClient,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Say on the ledger that the children this cycle made owe it nothing.

    A child entry is the split's own receipt -- this generation created issue
    #N -- and it is written `pending` because the create comes before
    anything that could confirm it. Nothing has ever moved one since: the
    reclamation does not look at child entries, and rightly, because a child
    is a live issue somebody is working rather than an object to reclaim.

    A cancellation has to move them, and for a reason outside itself.
    `rejected` is what authorizes a restart, and a restart projects its fresh
    cycle only over a ledger with nothing unreconciled left on it -- child
    entries included, correctly, since the projection drops the ledger and
    may not discharge an obligation by forgetting it. Retiring over them
    would hand an operator a terminal whose restart then refuses for good.

    So the ending records what is already true rather than inventing it: the
    children exist, this cycle is over, and nothing further about them is
    owed. Not one of them is touched on GitHub -- what moves is the parent's
    own account of what it made.
    """
    pending = _pending_children(generation)
    if not pending:
        return generation
    discharged = generation
    for target in pending:
        discharged = _late_cleanup_state._recorded(
            discharged, _obligations.LateResourceKind.CHILD, target,
            _obligations.LateResourceState.RECONCILED,
        )
    _late_cancellation_state._persisted(gh, issue, state, discharged)
    return discharged


def _pending_children(
    generation: _late_models.LateGeneration,
) -> tuple[str, ...]:
    """The child receipts this record has not yet said it owes nothing on."""
    if _late_cleanup_reading._unwritable(generation):
        return ()
    return tuple(
        entry.target
        for entry in generation.obligations.resources
        if entry.kind == _obligations.LateResourceKind.CHILD
        and entry.resource_state != _obligations.LateResourceState.RECONCILED
    )


def _superseded_branch(
    gh: _client.GitHubClient,
    spec: _config_models.RepoSpec,
    issue: Issue,
    state: _pinned_state.PinnedState,
    generation: _late_models.LateGeneration,
) -> _late_models.LateGeneration:
    """Take on the branch a supersession left behind but never wrote down.

    The transaction settles the held pull request and records the branch
    that pull request carried in two separate writes, and it must: the second
    is the retirement that hands the parent to `umbrella`, and retiring ahead
    of a supersession that might not land would leave the children loose
    beside a change still carrying their work. A close landing in that window
    leaves a cycle whose candidate is preserved on the ref, whose held PR is
    closed, and whose branch nothing on the record names -- so the
    reclamation, which walks the record, would settle around it and retire
    the owner over a branch the remote keeps for good.

    Asked of the announcement's own receipt rather than of the phase. Both go
    down in one write, so they say the same thing the first time -- the
    children are made, the links are said, and the supersession is what comes
    next -- but only one of them survives a retry: a park at the supersession
    is resumed from the top of the transaction, which rewrites `snapshotting`
    and `splitting` over the boundary while the announcement, already made,
    is stepped over. So a second failed attempt stands at `splitting` with the
    receipt still set, and the phase no longer says what was reached.

    Not before that receipt, though, and that is the whole of the timing: the
    snapshot is created AND proved ahead of the first child, so the candidate
    stops being only on that branch by the time the announcement is made.
    Earlier, deleting it would take the one copy of somebody's work.

    Only where nothing is recorded yet, in any state. A record that already
    names a branch is the ordinary case the reclamation owns, and re-recording
    a `reconciled` one as owed would ask the remote to delete it again.

    And only once the pull request this pass was just asked to settle IS
    settled, which is the same order the transaction takes: it records the
    branch in the retirement that follows a supersession, never beside one
    that failed. `superseding` is the boundary written BEFORE that attempt,
    so a record standing there says the attempt was reached and nothing about
    whether it landed -- and inferring the branch from it while the pull
    request is still open would delete, out from under a change a human can
    still see, the branch that change is built on. The obligation is not lost
    by waiting: the held PR is re-asked on every visit, and the visit that
    closes it is the one that takes the branch on.
    """
    if not generation.links_announced:
        return generation
    if _late_cleanup_reading._unwritable(generation) or _names_a_branch(generation):
        return generation
    if _late_cancellation_reading._owed_plan_pr(generation):
        log.warning(
            "issue=#%d was cancelled at its supersession and its held PR is "
            "not settled; leaving the branch that PR carries alone until it "
            "is", issue.number,
        )
        return generation
    branch = _naming._resolve_branch_name(state, spec, issue.number)
    log.warning(
        "issue=#%d was cancelled between the supersession of its held PR and "
        "the write that records the branch it superseded; taking %r on as "
        "owed rather than retiring over it", issue.number, branch,
    )
    owed = _late_cleanup_state._recorded(
        generation, _BRANCH, branch, _obligations.LateResourceState.PENDING,
    )
    _late_cancellation_state._persisted(gh, issue, state, owed)
    return owed


def _names_a_branch(generation: _late_models.LateGeneration) -> bool:
    """Whether this record already holds the superseded branch, any state."""
    return any(entry.kind == _BRANCH for entry in generation.obligations.resources)


def _proof_scan(
    gh: _client.GitHubClient,
    issue: Issue,
    generation: _late_models.LateGeneration,
) -> _ChildScan:
    """Read the consumers a held ref has to be proved against, if any.

    The reclamation rule needs a fresh reading of every recorded consumer, and
    that reading costs one request each. It buys nothing where no ref is held:
    a branch owes no consumer anything, and an owner whose refs are all
    reconciled has nothing a fresh disposition could unlock. So the scan is
    taken only where its answer can change one, which is what keeps a sweep
    over a repository's closed owners affordable.
    """
    if not _late_cleanup_reading._held_snapshots(generation):
        return _ChildScan([], {}, {})
    return _late_cleanup_reading._consumer_scan(gh, issue, generation)
