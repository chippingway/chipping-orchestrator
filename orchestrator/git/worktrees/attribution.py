# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which configured repository a local branch belongs to, and which issue.

A branch found in this host's orchestrator-owned namespace is not evidence of
anything on its own. Several ``REPOS`` entries may share one `target_root` --
a public and a private remote over a single checkout is the shape branch
namespacing exists for -- and their ref stores are one store, so a name there
is attributed by comparing it against every configured spec at once rather
than by reading it in isolation. Every function here takes that set.

Two rules, both exact and both failing closed:

* A name is attributed only when a spec's own `naming._branch_name` produces
  it character for character. Nothing is parsed back into a slug, so a
  segment no configured entry writes, an extra path component, a padded
  number, and the flat pre-namespacing `orchestrator/issue-<n>` -- which
  carries no slug at all -- are left alone rather than reconstructed into a
  repository, however few entries share the clone.
* A name several specs derive identically -- two slugs the ref sanitizer
  cannot tell apart -- is attributed to none of them.

The refusal costs one thing -- a branch this scan will not report -- and the
alternative costs more: a branch attributed to the wrong repository is one a
caller acts on against the wrong GitHub issue.

The checkouts those branches are standing in ask the same question of a
directory, and ``checkout_attribution`` answers it for the per-repository
parent a lossy sanitizer can hand to two entries. A checkout standing on a
branch name two entries derive is refused with the name (`_shared_branch`),
since a crafted slug can share another entry's branch while keeping a
checkout directory of its own; a teardown spending one issue's names
immediately rather than through a scan asks both rules at once
(`_sole_claimant`).
"""
from __future__ import annotations

import logging
from collections.abc import Iterable

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import checkout_attribution, naming as _naming, paths

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so the refusals below report where their
# filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

_REF_SEPARATOR = "/"

# How a refusal lists the several things it will not choose between.
_LISTED = ", "

# One repository's branches, keyed by the issue they name. A tuple because the
# candidate it feeds holds its branches as one, and it carries at most the
# issue's own current-layout name.
IssueBranches = dict[int, tuple[str, ...]]

# What one clone's branches say about the repositories sharing it.
AttributedIssues = dict[_config_models.RepoSpec, IssueBranches]


def _matching_owners(
    branch: str,
    issue_number: int,
    specs: tuple[_config_models.RepoSpec, ...],
) -> tuple[_config_models.RepoSpec, ...]:
    """Every spec on this clone whose own derivation produces `branch`.

    The current layout carries the publishing spec's ref-safe slug, so it is
    matched by re-deriving each spec's name for that issue and comparing:
    another repository's segment, a segment no ``REPOS`` entry produces, an
    `issue-<n>` tail hanging under two path components, and the flat name with
    no segment at all match nobody. More than one match is the sanitizer
    collision, handed to the caller in the only form that can express it.
    """
    return tuple(
        spec for spec in specs
        if _naming._branch_name(spec, issue_number) == branch
    )


def _branch_attribution(
    branch: str, specs: tuple[_config_models.RepoSpec, ...],
) -> tuple[_config_models.RepoSpec, int] | None:
    """The repository and issue one local branch belongs to, or None.

    None covers three different artifacts, deliberately answered the same
    way: a name carrying no readable issue number, a name no configured
    repository publishes, and a name more than one of them could. Only the
    last is worth an operator's attention -- the other two describe branches
    somebody else's tooling, a human, or an earlier layout left in the
    `orchestrator/` namespace for manual disposition, and a scan that ran
    every tick would say so every tick.
    """
    issue_number = paths._issue_segment_number(
        branch.rsplit(_REF_SEPARATOR, 1)[-1],
    )
    if issue_number is None:
        log.debug("local branch %r names no issue; leaving it alone", branch)
        return None
    owners = _matching_owners(branch, issue_number, specs)
    if len(owners) > 1:
        log.warning(
            "local branch %r could belong to any of %s; refusing to "
            "attribute it rather than charging one of them for it",
            branch, _LISTED.join(spec.slug for spec in owners),
        )
        return None
    if not owners:
        log.debug(
            "local branch %r belongs to no configured repository; leaving "
            "it alone", branch,
        )
        return None
    return owners[0], issue_number


def _record_attribution(
    owned: AttributedIssues,
    attribution: tuple[_config_models.RepoSpec, int],
    branch: str,
) -> None:
    """File one attributed branch under the repository and issue it names.

    One name per issue, because an attributed name is that issue's single
    derivation: a ref store lists it at most once.
    """
    spec, issue_number = attribution
    owned.setdefault(spec, {})[issue_number] = (branch,)


def _attributed_issues(
    branches: Iterable[str], specs: tuple[_config_models.RepoSpec, ...],
) -> AttributedIssues:
    """Group one clone's orchestrator branches by repository and issue.

    A repository with no branch of its own is absent from the answer rather
    than present with an empty entry, so a caller reading it back gets the
    same shape whether the clone holds one repository's branches or several.
    """
    owned: AttributedIssues = {}
    for branch in branches:
        attribution = _branch_attribution(branch, specs)
        if attribution is not None:
            _record_attribution(owned, attribution, branch)
    return owned


def _shared_branch(
    spec: _config_models.RepoSpec,
    issue_number: int,
    specs: Iterable[_config_models.RepoSpec],
) -> bool:
    """Whether another spec among `specs` derives this issue's branch name too.

    The branch rule asked of one repository and issue rather than of a name a
    listing turned up. A checkout standing on such a name is as unattributable
    as the name itself: the ref sanitizer's digest suffix lets a crafted slug
    land on another entry's branch name while the two keep distinct checkout
    directories, so the directory settles nothing about whose work the tree
    holds. `spec` itself is always a claimant, whether or not `specs` lists it.
    """
    claimants = (
        spec, *(other for other in specs if other.slug != spec.slug),
    )
    branch = _naming._branch_name(spec, issue_number)
    owners = _matching_owners(branch, issue_number, claimants)
    if len(owners) < 2:
        return False
    log.warning(
        "branch %r could belong to any of %s; refusing to attribute it "
        "rather than charging one of them for it",
        branch, _LISTED.join(owner.slug for owner in owners),
    )
    return True


def _sole_claimant(
    spec: _config_models.RepoSpec,
    issue_number: int,
    configured: Iterable[_config_models.RepoSpec],
) -> bool:
    """Whether this issue's current-layout branch and checkout are `spec`'s alone.

    The scan's two collision refusals, asked by a teardown that is handed one
    repository and one issue instead of a listing: a branch name another
    configured entry derives identically, and a checkout directory the path
    sanitizer hands another entry too. Either makes the issue's artifacts
    nobody's, so a caller about to delete them leaves them instead. `spec`
    itself is always a claimant, whether or not the configuration lists it.
    """
    claimants = (
        spec, *(other for other in configured if other.slug != spec.slug),
    )
    if _shared_branch(spec, issue_number, claimants):
        return False
    colliding = checkout_attribution._colliding_worktree_slugs(claimants)
    return spec.slug not in colliding
