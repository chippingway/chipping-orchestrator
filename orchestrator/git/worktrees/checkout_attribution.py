# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which configured repository a checkout directory belongs to, if it settles.

Every repository's checkouts hang off one `WORKTREES_DIR`, whatever clone the
repository is on, so a directory cannot be attributed the way a branch is:
what the name says is not enough on its own. Two shapes reach this owner, and
both take the whole set of configured specs for that reason.

The flat pre-namespacing checkout, `WORKTREES_DIR/issue-<n>`, carries no slug
at all -- every configured entry derived it identically -- so the repository
the directory is OF settles it instead: the git directory the checkout and its
clone share, which is the same identity the classification tests a named
checkout by. That answers every host whose entries keep their own clones and
leaves exactly one case open, which is the case a shared ref store leaves open
for a branch too: two entries on one clone.

The per-repository checkout directory is the same ambiguity one derivation
over. The path sanitizer that names it is lossy, so two entries whose slugs
differ only in a character it rewrites are handed one directory to keep their
checkouts in, and an `issue-<n>` in it names an issue in whichever of them
created it.

Both fail closed, and they cost more to get wrong than the branch rules in
``attribution`` do. A checkout is a live worktree standing on one of that
issue's branches, so an unsettled claim names its claimants rather than
nobody: a caller has to withhold the whole issue -- the branches beside the
tree included -- because reporting a branch whose tree nobody may remove hands
a teardown a ref to delete under a checkout that is still holding it.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import paths

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so the refusals below report where their
# filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# How a refusal lists the several things it will not choose between.
_LISTED = ", "


@dataclass(frozen=True)
class CheckoutClaim:
    """What a flat checkout's clone identity settled, and what it did not.

    `owner` is the one repository the directory was PROVEN to be a worktree of,
    and it is set only when nothing else could be: one claimant, whose clone
    was read and matched. `claimants` is every repository it could belong to,
    which is what a caller withholds the issue from when the question was not
    settled -- the two overlap by design, since a settled claim is a claimant
    that happens to be alone.
    """

    owner: _config_models.RepoSpec | None
    claimants: tuple[_config_models.RepoSpec, ...]


def _slugs_by_worktrees_root(
    specs: Iterable[_config_models.RepoSpec],
) -> dict[Path, tuple[str, ...]]:
    """Group the configured slugs by the checkout directory each derives."""
    by_root: dict[Path, tuple[str, ...]] = {}
    for spec in specs:
        root = paths._repo_worktrees_root(spec)
        by_root[root] = (*by_root.get(root, ()), spec.slug)
    return by_root


def _countable_legacy_checkouts(
    specs: Iterable[_config_models.RepoSpec], found: frozenset[int],
) -> frozenset[int]:
    """The flat `issue-<n>` directories that are checkouts rather than roots.

    A number whose flat path is also some entry's per-repository worktrees root
    is dropped, which takes a `REPOS` slug that sanitizes to an `issue-<n>` of
    its own: what sits at that path is then a directory full of checkouts
    rather than a checkout, and the two must not be confused whichever of them
    the scan reached first.
    """
    roots = {paths._repo_worktrees_root(spec) for spec in specs}
    return frozenset(
        issue_number for issue_number in found
        if paths._legacy_worktree_path(issue_number) not in roots
    )


def _legacy_checkout_claim(
    clone: Path | None,
    clones: Mapping[_config_models.RepoSpec, Path | None],
    subject: str,
) -> CheckoutClaim:
    """Who a flat checkout could be a worktree of, and whether that was settled.

    The flat layout carries no slug, so unlike a branch the question cannot be
    settled by re-deriving a name: `WORKTREES_DIR/issue-<n>` is what every
    configured entry produced, identically. What settles it instead is the same
    identity the classification tests a named checkout by -- the git directory
    the checkout and its clone share -- so a host driving several repositories
    on several clones still attributes each flat checkout to the one entry
    whose clone it is a worktree of.

    An entry whose OWN clone could not be read claims the checkout too. Nothing
    established that it is not the one, and dropping it from the claimants is
    how a checkout on a shared clone reads as uniquely owned: the sibling that
    would have made it ambiguous simply did not answer. The same reading covers
    the checkout whose own clone could not be read, which claims every entry
    there is.

    An owner therefore comes back only where the whole question was answered:
    one claimant, and that claimant's clone read and matched. Every other shape
    hands the claimants over instead, because a tree none of them may take is
    standing on one of that issue's branches -- so the caller has to withhold
    the issue rather than merely drop the directory.
    """
    if clone is None:
        log.warning(
            "could not tell which clone the flat checkout %s is of; leaving "
            "every repository's copy of that issue alone", subject,
        )
        return CheckoutClaim(owner=None, claimants=tuple(clones))
    claimants = tuple(
        spec for spec, configured_at in clones.items()
        if configured_at is None or configured_at == clone
    )
    if len(claimants) == 1 and clones[claimants[0]] is not None:
        return CheckoutClaim(owner=claimants[0], claimants=claimants)
    _report_unsettled(claimants, subject)
    return CheckoutClaim(owner=None, claimants=claimants)


def _report_unsettled(
    claimants: tuple[_config_models.RepoSpec, ...], subject: str,
) -> None:
    """Say why a flat checkout was not charged to anybody.

    Three shapes, and an operator settles each differently: a clone nobody
    could read is a repository to go and look at, several claimants is a
    configuration whose entries share a store, and no claimant at all is a
    directory that is simply not this orchestrator's -- which is the one shape
    that costs nothing and says so at debug.
    """
    named = _LISTED.join(spec.slug for spec in claimants)
    if len(claimants) > 1:
        log.warning(
            "the flat checkout %s could belong to any of %s; refusing to "
            "attribute it, and leaving that issue's artifacts alone in all "
            "of them", subject, named,
        )
    elif claimants:
        log.warning(
            "could not tell whether the flat checkout %s is %s's; leaving "
            "that issue's artifacts alone", subject, named,
        )
    else:
        log.debug(
            "the flat checkout %s is no configured repository's; leaving it "
            "alone", subject,
        )


def _colliding_worktree_slugs(
    specs: Iterable[_config_models.RepoSpec],
) -> tuple[str, ...]:
    """The slugs whose checkout directory is not theirs alone.

    The path counterpart of the branch rules in ``attribution``, and it has to
    be asked across every configured entry rather than per clone: the checkouts
    hang off one `WORKTREES_DIR` whatever clone their repository is on, and the
    slug sanitizer that names the per-repo directory under it rewrites every
    character it cannot keep. Two entries it cannot tell apart therefore get
    one directory, and an `issue-<n>` checkout in it carries nothing that says
    which of them created it -- the same unanswerable question a shared
    clone's legacy branch asks.

    Refusing those repositories outright rather than only their checkouts is
    the honest reading of it: what a caller does with a candidate turns on the
    artifacts under it, and half a picture of a repository whose other half
    cannot be attributed is not one to act on. It costs nothing a healthy
    configuration has -- a real `owner/name` pair sanitizes injectively, so
    reaching this needs a `REPOS` entry carrying a character GitHub does not
    allow in a repository name.
    """
    colliding: list[str] = []
    for root, slugs in _slugs_by_worktrees_root(specs).items():
        if len(slugs) > 1:
            log.warning(
                "the checkout directory %s is derived by %s; refusing to "
                "attribute anything under it to any of them",
                root, _LISTED.join(slugs),
            )
            colliding.extend(slugs)
    return tuple(sorted(colliding))
