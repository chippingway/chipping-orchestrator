# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Combine local and remote artifact inventories into maintenance candidates.

remote_inventory reports published branches and unreachable repositories;
candidate_layout classifies the resulting names. This owner merges evidence
per issue, preserves withheld claims, and orders the candidates deterministically.
"""
from __future__ import annotations

from collections.abc import Sequence

from orchestrator import config
from orchestrator.git.worktrees import (
    candidate_layout as _layouts,
    inventory,
    naming as _naming,
    remote_inventory as _remote_inventory,
)
from orchestrator.git.worktrees.candidates import IssueArtifacts, MaintenanceCandidate, MaintenanceScan

# One issue of one repository, as both halves of a discovery key it.
CandidateKey = tuple[config.RepoSpec, int]


def _widened(
    artifacts: IssueArtifacts, published: tuple[str, ...],
) -> MaintenanceCandidate:
    """One candidate: the artifacts as the host and the remote together hold them.

    The two lists are merged through `naming._issue_branch_names` rather than
    concatenated, which does what the local scan's own recording does one level
    up: an issue carrying both layouts always reads namespaced-first, the order
    a teardown takes them in, one name cannot arrive twice because it is on
    both hosts, and a name neither derivation produces cannot enter through
    this door either.

    The layout is decided here because this is the last place both halves are
    still apart. Afterwards the branches are one list by design, and nothing
    downstream could say which of them the clone was actually holding.
    """
    held = frozenset(artifacts.branches) | frozenset(published)
    branches = tuple(
        name for name in _naming._issue_branch_names(
            artifacts.spec, artifacts.issue_number,
        )
        if name in held
    )
    widened = IssueArtifacts(
        spec=artifacts.spec,
        issue_number=artifacts.issue_number,
        worktrees=artifacts.worktrees,
        branches=branches,
    )
    return MaintenanceCandidate(
        artifacts=widened,
        layout=_layouts._candidate_layout(widened, artifacts.branches),
    )


def _candidate_order(key: CandidateKey) -> tuple[str, int]:
    """One key as the pair a discovery's whole answer is ordered by."""
    spec, issue_number = key
    return spec.slug, issue_number


def _candidate_keys(
    local: dict[CandidateKey, IssueArtifacts],
    published: _remote_inventory.PublishedBranches,
    withheld: frozenset[tuple[str, int]],
) -> tuple[CandidateKey, ...]:
    """Every repository and issue either half of the discovery named, in order.

    Sorted by slug and then issue number, so a candidate found only on the
    remote lands where the same issue would have landed had this host still
    held it -- which is what lets two discoveries of an unchanged world be
    compared.

    An issue the scan withheld is dropped from BOTH halves. The scan withholds
    one because something on this host is standing on that issue's artifacts
    and nobody can be charged for it, and the remote knows nothing about that:
    left in, its copy of the branch would come back as a remote-only candidate
    and a teardown spending it would take the local ref beneath a live
    checkout.
    """
    keyed = set(local) | {
        (spec, issue_number)
        for spec, branched in published.items()
        for issue_number in branched
    }
    return tuple(sorted(
        (
            key for key in keyed
            if (key[0].slug, key[1]) not in withheld
        ),
        key=_candidate_order,
    ))


def _keyed_candidate(
    key: CandidateKey,
    local: dict[CandidateKey, IssueArtifacts],
    published: _remote_inventory.PublishedBranches,
) -> MaintenanceCandidate:
    """The candidate one repository-and-issue key stands for.

    A key the local scan never named is an issue whose artifacts are all on the
    remote, and it is built with the empty local shape rather than skipped:
    what makes it a candidate is the branch out there, and the widening beside
    this is what puts that branch on it.
    """
    spec, issue_number = key
    artifacts = local.get(key) or IssueArtifacts(
        spec=spec, issue_number=issue_number, worktrees=(), branches=(),
    )
    return _widened(artifacts, published.get(spec, {}).get(issue_number, ()))


def _maintenance_candidates(
    specs: Sequence[config.RepoSpec],
) -> MaintenanceScan:
    """Every candidate a reclamation may consider, over host and remote.

    The entry point, taking the configured specs rather than reading them, so a
    caller driving one repository still hands over the whole set: attribution
    is a question about every entry at once -- which of them share a clone,
    which of them derive one checkout directory -- and a scan told about one
    would attribute a name several could own to the only claimant it knew.

    A candidate here is an issue this host or its remote holds something for,
    which is a different question from what GitHub would say about it: it may
    be open, may never have been this orchestrator's, may not exist. Deciding
    that is the classification's, and the repositories in `refused` are the
    ones nothing can be decided about from this answer at all.
    """
    configured = tuple(specs)
    scanned = inventory._local_issue_inventory(configured)
    published, refused = _remote_inventory._remote_half(
        configured, frozenset(scanned.refused),
    )
    local = {
        (artifacts.spec, artifacts.issue_number): artifacts
        for artifacts in scanned.issues
        if artifacts.spec.slug not in refused
    }
    return MaintenanceScan(
        candidates=tuple(
            _keyed_candidate(key, local, published)
            for key in _candidate_keys(
                local, published, frozenset(scanned.withheld),
            )
        ),
        refused=tuple(sorted(refused)),
    )
