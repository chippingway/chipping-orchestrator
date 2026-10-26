# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Build one read-only local artifact inventory from branch and checkout evidence.

inventory_roots groups repositories by clone. This owner combines each
repository's own checkout root with the branches attributed to it, refusing
colliding and unreadable roots and withholding a checkout whose branch name
another repository on the clone derives too. Only current-layout names are
reported: a flat checkout or branch is no repository's artifact and never
becomes a candidate.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import chain

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import (
    attribution,
    branch_probes,
    checkout_attribution,
    inventory_roots as _inventory_roots,
    paths,
    probes,
)
from orchestrator.git.worktrees.candidates import ArtifactInventory, IssueArtifacts


def _issue_artifacts(
    spec: _config_models.RepoSpec,
    issue_number: int,
    checkouts: frozenset[int],
    branched: Mapping[int, tuple[str, ...]],
) -> IssueArtifacts:
    """One issue's entry: the checkout it still has, and the branch naming it.

    The checkout is this issue's own derivation rather than the directory name
    the scan read, so a path the current layout does not write cannot enter
    the answer.
    """
    held = issue_number in checkouts
    return IssueArtifacts(
        spec=spec,
        issue_number=issue_number,
        worktrees=(paths._worktree_path(spec, issue_number),) if held else (),
        branches=branched.get(issue_number, ()),
    )


def _spec_inventory(
    spec: _config_models.RepoSpec,
    branched: Mapping[int, tuple[str, ...]],
    root_specs: tuple[_config_models.RepoSpec, ...],
) -> ArtifactInventory:
    """Every issue one repository has an artifact for, or a refusal for it.

    The union of both sides is what makes a candidate: an issue is reported
    once whether a checkout, the branch, or both named it. The checkouts are
    read for one repository at a time because the directory they sit in is
    this spec's alone -- an entry that shares it with another was refused
    before the scan reached here.

    A checkout whose branch name another spec on this clone derives too is
    left out with its issue: the branch itself was refused by the attribution
    above, and the tree standing on it is no more this repository's than the
    name is, however distinct the directory it sits in.
    """
    checkouts = probes._worktree_issue_numbers(spec)
    if checkouts is None:
        return ArtifactInventory(issues=(), refused=(spec.slug,))
    contested = frozenset(
        issue_number for issue_number in checkouts
        if attribution._shared_branch(spec, issue_number, root_specs)
    )
    return ArtifactInventory(
        issues=tuple(
            _issue_artifacts(spec, issue_number, checkouts, branched)
            for issue_number in sorted((checkouts - contested) | branched.keys())
        ),
        refused=(),
    )


def _root_inventory(
    root_specs: tuple[_config_models.RepoSpec, ...],
    refused: frozenset[str],
) -> ArtifactInventory:
    """Every issue the repositories sharing one clone hold artifacts for.

    One listing per clone rather than one per repository: the specs on it
    share a ref store, so a second read would return the same refs and
    attribute them the same way.

    Every spec on the clone is put to the attribution, the already-refused
    ones included, and only the rest are reported. Refusing a repository says
    this scan will not answer for it, not that it never published here: drop
    it from the claimants and a branch name it derives identically to a
    sibling loses an owner it could equally have, which is how a branch that
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
        _spec_inventory(spec, owned.get(spec, {}), root_specs)
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
    )


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

    Two refusals are settled before a repository is read, because both are
    answers about the configuration rather than about a host: the entries
    sharing a derived checkout directory, which is ``checkout_attribution``'s
    collision rule, and the entries whose ref store could not be identified.
    Neither is read, and neither is reported -- but both stay claimants, the
    first in the group its store holds and the second in every group, because
    a repository this scan will not answer for is still one that could have
    published what is on the clone it shares.
    """
    configured = tuple(specs)
    colliding = checkout_attribution._colliding_worktree_slugs(configured)
    grouped, unresolved = _inventory_roots._specs_by_clone(configured)
    refused = frozenset(colliding) | frozenset(unresolved)
    return _merged((
        ArtifactInventory(issues=(), refused=(*colliding, *unresolved)),
        *(
            _root_inventory(root_specs, refused)
            for root_specs in grouped.values()
        ),
    ))
