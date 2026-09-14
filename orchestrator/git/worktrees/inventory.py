# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Build one read-only local artifact inventory from branch and checkout evidence.

inventory_roots groups repositories by clone, and legacy_inventory attributes
flat checkouts. This owner combines those claims with repository-scoped paths
and branches, withholding every ambiguous issue and refusing unreadable roots.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import chain
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import (
    attribution,
    branch_probes,
    checkout_attribution,
    inventory_roots as _inventory_roots,
    legacy_inventory as _legacy_inventory,
    paths,
    probes,
)
from orchestrator.git.worktrees.candidates import ArtifactInventory, IssueArtifacts


def _held_checkouts(
    spec: _config_models.RepoSpec,
    issue_number: int,
    checkouts: frozenset[int],
    legacy: frozenset[int],
) -> tuple[Path, ...]:
    """Which of this issue's two checkout paths the host is actually holding.

    Filtered out of what this issue's own derivations produce rather than
    assembled from the directory names the scan read, which does what the
    branch side's own recording does: a path neither derivation writes cannot
    enter the answer, and an issue holding both layouts always reads
    current-first, the order a teardown takes them in.
    """
    held = set()
    if issue_number in checkouts:
        held.add(paths._worktree_path(spec, issue_number))
    if issue_number in legacy:
        held.add(paths._legacy_worktree_path(issue_number))
    return tuple(
        path for path in paths._issue_worktree_paths(spec, issue_number)
        if path in held
    )


def _issue_artifacts(
    spec: _config_models.RepoSpec,
    issue_number: int,
    checkouts: tuple[frozenset[int], frozenset[int]],
    branched: Mapping[int, tuple[str, ...]],
) -> IssueArtifacts:
    """One issue's entry: the checkouts it still has, and the branches naming it.

    The two checkout sets arrive as one pair because they are one question read
    in two places: the per-repository root this spec owns, and the flat
    directory every entry once shared.
    """
    return IssueArtifacts(
        spec=spec,
        issue_number=issue_number,
        worktrees=_held_checkouts(spec, issue_number, *checkouts),
        branches=branched.get(issue_number, ()),
    )


def _spec_inventory(
    spec: _config_models.RepoSpec,
    branched: Mapping[int, tuple[str, ...]],
    legacy: _legacy_inventory.LegacyCheckouts,
) -> ArtifactInventory:
    """Every issue one repository has an artifact for, or a refusal for it.

    The union of all three sides is what makes a candidate: an issue is
    reported once whether a checkout, the branches, or any of them named it.
    The per-repository checkouts are read for one repository at a time because
    the directory they sit in is this spec's alone -- an entry that shares it
    with another was refused before the scan reached here. The flat ones were
    read once for the whole host and are handed in already attributed, since
    the directory they sit in is nobody's alone.

    An issue whose flat checkout could be this repository's or a sibling's is
    left out of the answer whole -- its branches with it, and whether or not
    this repository holds anything else for it. What makes that necessary is
    what the checkout IS rather than what it is called: a live worktree
    standing on one of that issue's branches. Reporting the branch while the
    tree stayed unattributable would hand a teardown a ref to delete under a
    checkout nobody may remove, and `update-ref` does exactly that without
    complaint -- leaving the tree holding a HEAD that resolves to nothing.
    """
    checkouts = probes._worktree_issue_numbers(spec)
    if checkouts is None:
        return ArtifactInventory(issues=(), refused=(spec.slug,))
    held = legacy.held.get(spec, frozenset())
    ambiguous = legacy.ambiguous.get(spec, frozenset())
    reportable = (checkouts | held | branched.keys()) - ambiguous
    return ArtifactInventory(
        issues=tuple(
            _issue_artifacts(
                spec, issue_number, (checkouts, held), branched,
            )
            for issue_number in sorted(reportable)
        ),
        refused=(),
        withheld=tuple(
            (spec.slug, issue_number) for issue_number in sorted(ambiguous)
        ),
    )


def _root_inventory(
    root_specs: tuple[_config_models.RepoSpec, ...],
    refused: frozenset[str],
    legacy: _legacy_inventory.LegacyCheckouts,
) -> ArtifactInventory:
    """Every issue the repositories sharing one clone hold artifacts for.

    One listing per clone rather than one per repository: the specs on it
    share a ref store, so a second read would return the same refs and
    attribute them the same way.

    Every spec on the clone is put to the attribution, the already-refused
    ones included, and only the rest are reported. Refusing a repository says
    this scan will not answer for it, not that it never published here: drop
    it from the claimants and the flat `orchestrator/issue-<n>` this clone
    holds loses an owner it could equally have, which is how a branch that
    belongs to nobody ends up charged to whichever entry was left.

    A listing that could not be taken refuses every repository still standing
    on that clone, checkouts included, even though those were never read for.
    What a caller does with an issue turns on the shape of its artifacts -- a
    checkout with no branch and a checkout whose branch simply could not be
    read are different situations with the same appearance -- so reporting the
    checkouts alone would hand out that shape as if it had been established.
    """
    reportable = tuple(
        spec for spec in root_specs if spec.slug not in refused
    )
    if not reportable:
        return ArtifactInventory(issues=(), refused=())
    branches = branch_probes._local_orchestrator_branches(
        reportable[0].target_root,
    )
    if branches is None:
        return ArtifactInventory(
            issues=(), refused=tuple(spec.slug for spec in reportable),
        )
    owned = attribution._attributed_issues(branches, root_specs)
    return _merged(tuple(
        _spec_inventory(spec, owned.get(spec, {}), legacy)
        for spec in reportable
    ))


def _merged(
    inventories: tuple[ArtifactInventory, ...],
) -> ArtifactInventory:
    """One answer over several scans, in an order two runs can be compared by.

    Each issue is produced by exactly one repository's scan, so this
    concatenates rather than combines: the deduplication a single issue needs
    has already happened where its two sides were read.
    """
    return ArtifactInventory(
        issues=tuple(sorted(
            chain.from_iterable(scan.issues for scan in inventories),
            key=lambda artifacts: (artifacts.spec.slug, artifacts.issue_number),
        )),
        refused=tuple(sorted({
            slug for scan in inventories for slug in scan.refused
        })),
        withheld=tuple(sorted({
            held for scan in inventories for held in scan.withheld
        })),
    )


def _scanned(
    configured: tuple[_config_models.RepoSpec, ...], legacy: _legacy_inventory.LegacyCheckouts,
) -> ArtifactInventory:
    """The scan proper, once the host-wide flat checkouts have been attributed.

    Two refusals are settled here, before a repository is read, because both
    are answers about the configuration rather than about a host: the entries
    sharing a derived checkout directory, which is ``checkout_attribution``'s
    collision rule, and the entries whose clone would not resolve. Neither is
    read, and neither is reported -- but both stay in the group their clone
    holds, because a repository this scan will not answer for is still one that
    could have published what is on the clone it names.
    """
    colliding = checkout_attribution._colliding_worktree_slugs(configured)
    grouped, unresolved = _inventory_roots._specs_by_clone(configured)
    refused = frozenset(colliding) | frozenset(unresolved)
    return _merged((
        ArtifactInventory(issues=(), refused=(*colliding, *unresolved)),
        *(
            _root_inventory(root_specs, refused, legacy)
            for root_specs in grouped.values()
        ),
    ))


def _local_issue_inventory(
    specs: Sequence[_config_models.RepoSpec],
) -> ArtifactInventory:
    """Every issue this host holds an orchestrator-owned artifact for.

    The entry point to the scan, taking the configured specs rather than
    reading them, so a caller with a narrower list -- one repository, or the
    ones a tick actually drives -- asks about exactly those.

    An issue appears here because of what is on this host, which is a
    different question from what GitHub would say about it: a candidate may
    name an issue that is closed, merged, or was never this orchestrator's to
    begin with. Deciding that is the caller's, and the repositories named in
    `refused` are the ones it cannot decide anything about from this answer.

    The flat pre-namespacing checkouts are read first and once, because they
    are the one artifact that belongs to no repository by its name: they sit
    directly under `WORKTREES_DIR`, which every entry shares. A listing that
    could not be taken refuses every configured repository, since a flat
    checkout that was not read is one any of them could still be holding --
    and a caller acting on the absence of one would be acting on a reading
    nobody took.
    """
    configured = tuple(specs)
    flat = probes._legacy_checkout_numbers()
    if flat is None:
        return ArtifactInventory(
            issues=(),
            refused=tuple(sorted({spec.slug for spec in configured})),
        )
    return _scanned(configured, _legacy_inventory._attributed_legacy(configured, flat))
