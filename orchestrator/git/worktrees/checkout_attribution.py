# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Which configured repositories cannot be told apart by their checkout directory.

Every repository's checkouts hang off one `WORKTREES_DIR`, whatever clone the
repository is on, under the per-repository parent `paths._repo_worktrees_root`
derives. The path sanitizer that names that parent is lossy, so two entries
whose slugs differ only in a character it rewrites are handed one directory to
keep their checkouts in, and an `issue-<n>` in it names an issue in whichever
of them created it. This owner finds those entries so the scan refuses them
whole, and it is asked across every configured entry at once for that reason.

A flat `WORKTREES_DIR/issue-<n>` directory is not asked about at all. No
configured entry derives it, so it is attributed to nobody and never reaches a
candidate; a tree standing there on one of an issue's branches still keeps
that branch, through the clone-wide checkout listing every branch deletion
reads first.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
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


def _slugs_by_worktrees_root(
    specs: Iterable[_config_models.RepoSpec],
) -> dict[Path, tuple[str, ...]]:
    """Group the configured slugs by the checkout directory each derives."""
    by_root: dict[Path, tuple[str, ...]] = {}
    for spec in specs:
        root = paths._repo_worktrees_root(spec)
        by_root[root] = (*by_root.get(root, ()), spec.slug)
    return by_root


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
    which of them created it -- the same unanswerable question a branch name
    two entries derive asks in ``attribution``.

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
