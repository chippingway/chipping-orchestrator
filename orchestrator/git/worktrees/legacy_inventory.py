# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Attribute flat legacy checkouts to configured repositories before inventory.

One owner records both held checkouts and every claimant of an ambiguous
checkout, so the local scan can withhold an issue rather than report only the
branch that it must not reclaim beneath a possibly live checkout.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import (
    checkout_attribution,
    paths,
    probes,
)

# The flat pre-namespacing checkouts, by the repository each concerns.
# A repository nothing was found for is absent from either map rather than
# present with an empty entry, so a caller reads the same shape whether the
# host holds one entry's flat checkouts or several entries'.
IssueNumbers = dict[_config_models.RepoSpec, frozenset[int]]


@dataclass(frozen=True)
class LegacyCheckouts:
    """What the flat pre-namespacing checkouts mean for each repository.

    `held` is the attribution: the issues whose flat checkout is a worktree of
    exactly that repository's clone, reported as its artifacts. `ambiguous` is
    the refusal beside it: the issues whose flat checkout could be that
    repository's or a sibling's on the same clone, which are left out of the
    scan entirely rather than reported without the tree nobody may take.

    The two are kept apart rather than collapsed into "attributed or not",
    because they cost a caller different things. What is held is something to
    act on; what is ambiguous is something no repository may act on at all, and
    a scan that merely dropped it would report the branches beside it as an
    issue with nothing standing on them.
    """

    held: IssueNumbers
    ambiguous: IssueNumbers


def _legacy_claim(
    issue_number: int,
    clones: dict[_config_models.RepoSpec, Path | None],
) -> checkout_attribution.CheckoutClaim:
    """Which configured repository one flat checkout is a worktree of, if any."""
    worktree = paths._legacy_worktree_path(issue_number)
    return checkout_attribution._legacy_checkout_claim(
        probes._checkout_clone(worktree), clones, str(worktree),
    )


def _attributed_legacy(
    configured: tuple[_config_models.RepoSpec, ...], flat: frozenset[int],
) -> LegacyCheckouts:
    """Which repository each flat pre-namespacing checkout concerns, and how.

    Two answers rather than one, because a checkout nobody can be charged for
    is not the same as one that is not there. A single claimant HOLDS it, and
    the checkout is reported as that repository's artifact. Several claimants
    hold an issue this scan must not report at all: the tree is standing on one
    of that issue's branches, and reporting the branch without the tree hands a
    teardown a ref to delete out from under a live checkout.

    The clones are resolved once for the whole host and only when there is
    something to attribute, because that read costs a git process per
    configured entry and the layout it settles is one nothing has written to
    for a long time: a host with no flat checkouts left pays nothing at all.
    """
    counted = checkout_attribution._countable_legacy_checkouts(
        configured, flat,
    )
    if not counted:
        return LegacyCheckouts(held={}, ambiguous={})
    legacy = LegacyCheckouts(held={}, ambiguous={})
    clones = {
        spec: probes._checkout_clone(spec.target_root) for spec in configured
    }
    for issue_number in sorted(counted):
        _file_claim(legacy, issue_number, _legacy_claim(issue_number, clones))
    return legacy


def _file_claim(
    legacy: LegacyCheckouts,
    issue_number: int,
    claim: checkout_attribution.CheckoutClaim,
) -> None:
    """File one flat checkout under every repository it concerns.

    A settled claim holds it; anything short of one means nobody may act on
    that issue at all, and each repository that could own the tree has to be
    told which issue to leave alone.
    """
    if claim.owner is not None:
        legacy.held[claim.owner] = legacy.held.get(
            claim.owner, frozenset(),
        ) | {issue_number}
        return
    for spec in claim.claimants:
        legacy.ambiguous[spec] = legacy.ambiguous.get(
            spec, frozenset(),
        ) | {issue_number}
