# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Read and attribute published issue branches for the maintenance scan.

A remote that cannot be listed refuses the whole repository. Branch ownership
uses every spec sharing the clone, including specs whose local inventory was
refused, because absence of a reading cannot establish a unique owner.
"""
from __future__ import annotations

import logging

from orchestrator.config import models as _config_models
from orchestrator.git import ref_discovery
from orchestrator.git.worktrees import (
    attribution,
    inventory_roots as _inventory_roots,
)

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a remote this discovery will not answer
# for says so where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# The namespace every branch this orchestrator publishes lives under, in the
# pattern form `ls-remote` matches by. git's glob crosses `/` here, so the one
# pattern covers the flat legacy name and the slug-namespaced one a component
# deeper alike, and the trailing separator keeps a ref called
# `refs/heads/orchestrator` itself out of the answer.
_ORCHESTRATOR_REMOTE_REFS = "refs/heads/orchestrator/*"

_REMOTE_BRANCH_PREFIX = "refs/heads/"

# What the remote carries, by the repository that published it and the issue it
# names: the remote-side counterpart of the clone's own attributed listing.
PublishedBranches = dict[_config_models.RepoSpec, attribution.IssueBranches]


def _remote_orchestrator_branches(
    spec: _config_models.RepoSpec,
) -> tuple[str, ...] | None:
    """Every branch this repository's remote carries under the owned namespace.

    Named as the derivations in ``paths`` spell them, so the attribution that
    re-derives each spec's own name can compare against them without either
    side adjusting; a refname the listing reports outside `refs/heads/` is not
    a branch and is left out rather than trimmed into one.

    `None` when the remote would not answer, which is not the empty tuple a
    repository whose branches have all been deleted gives. The read runs in the
    clone rather than in a per-issue checkout, because the transport-config
    refusal in front of it has to inspect the repository this discovery is
    about -- and a checkout a candidate names may already be gone.

    The boundary around it is total, for the reason every probe with a fixed
    set of answers carries one: the listing answers `None` for the failures it
    recognizes and raises for the ones underneath them -- a git that cannot
    be spawned, a host that will not let this process write the askpass script,
    a clone that has been removed since the configuration named it. An
    exception out of one repository's listing would end the discovery for every
    other repository in it, which is the one way an unreachable remote could
    cost more than the artifacts it is about.
    """
    try:
        listed = ref_discovery._remote_ref_names(
            spec, spec.target_root, pattern=_ORCHESTRATOR_REMOTE_REFS,
        )
    except Exception:
        log.warning(
            "could not ask %s what it still carries under the orchestrator "
            "namespace", spec.slug, exc_info=True,
        )
        return None
    if listed is None:
        log.warning(
            "could not list what %s still carries under the orchestrator "
            "namespace; leaving its artifacts alone", spec.slug,
        )
        return None
    return tuple(
        refname[len(_REMOTE_BRANCH_PREFIX):] for refname in listed
        if refname.startswith(_REMOTE_BRANCH_PREFIX)
    )


def _remote_issue_branches(
    spec: _config_models.RepoSpec, root_specs: tuple[_config_models.RepoSpec, ...],
) -> attribution.IssueBranches | None:
    """Which of this remote's branches belong to this repository, by issue.

    Put to every claimant on the clone rather than to this spec alone, which is
    what keeps the ambiguous legacy name unattributed: the remote says which
    repository the branch was pushed to, and nothing says which of the entries
    sharing a clone created it -- so a name more than one of them could own
    stays nobody's here as it does locally.

    A name attributed to a SIBLING on that clone is dropped rather than
    reported under it: what this repository's remote carries is evidence about
    this repository, and a branch spelled for another entry that turned up here
    is not something either of them can be charged for.
    """
    listed = _remote_orchestrator_branches(spec)
    if listed is None:
        return None
    owned = attribution._attributed_issues(listed, root_specs)
    return owned.get(spec, {})


def _group_published(
    root_specs: tuple[_config_models.RepoSpec, ...], refused: frozenset[str],
) -> tuple[PublishedBranches, frozenset[str]]:
    """What the remotes of the repositories on one clone carry, and whose would not say.

    One listing per repository rather than per clone, because a remote is the
    one thing entries sharing a clone do not share: two `REPOS` entries over a
    single checkout are a public and a private repository, and asking one of
    them what the other holds would attribute a branch to a repository that
    never carried it.

    A repository the local scan already refused is not listed for, since
    nothing about it will be reported either way -- and it stays in the group
    put to the attribution, because a repository this discovery will not answer
    for is still one the flat legacy branch on its clone could belong to.
    """
    listed = {
        spec: _remote_issue_branches(spec, root_specs)
        for spec in root_specs if spec.slug not in refused
    }
    return (
        {
            spec: branched for spec, branched in listed.items()
            if branched is not None
        },
        frozenset(
            spec.slug for spec, branched in listed.items()
            if branched is None
        ),
    )


def _published_branches(
    grouped: _inventory_roots.CloneGroups, refused: frozenset[str],
) -> tuple[PublishedBranches, frozenset[str]]:
    """What every repository's remote still carries, over every clone at once."""
    published: PublishedBranches = {}
    unreachable: frozenset[str] = frozenset()
    for root_specs in grouped.values():
        listed, missed = _group_published(root_specs, refused)
        published.update(listed)
        unreachable |= missed
    return published, unreachable


def _remote_half(
    configured: tuple[_config_models.RepoSpec, ...], refused: frozenset[str],
) -> tuple[PublishedBranches, frozenset[str]]:
    """What every reachable remote carries, and who is left out of the answer.

    The grouping is taken again here rather than carried over from the scan,
    because what it decides is not the same question: the scan groups to know
    which repositories claim one ref store, and this groups to know which of
    them a name on one remote could equally have come from. Both answers are
    the same clone map, and neither is worth threading through a record that
    exists to describe a host.
    """
    grouped, _unresolved = _inventory_roots._specs_by_clone(configured)
    published, unreachable = _published_branches(grouped, refused)
    return published, refused | unreachable
