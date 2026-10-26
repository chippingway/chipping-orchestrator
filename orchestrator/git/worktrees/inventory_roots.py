# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Group configured repositories by the ref store whose local artifacts they share.

A group is one git common directory, whatever path each entry reaches it by:
two targets that are linked worktrees of one repository read and write the
same branches. An entry whose store cannot be identified is refused and still
counted a claimant on every store, so its possible claims cannot be mistaken
for evidence that another repository owns an artifact. Both local and remote
inventory scans use this same grouping.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import probes

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a repository this scan will not answer
# for says so where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# The specs on each ref store a scan reads, keyed by the git common directory
# they share: one group is one store, and everyone in it is a claimant to what
# that store holds.
CloneGroups = dict[Path, tuple[_config_models.RepoSpec, ...]]


def _ref_store(spec: _config_models.RepoSpec) -> Path | None:
    """The git common directory this spec's clone keeps its refs in, or None.

    The identity the checkout checks already test a tree by, and the only one
    that answers equal for every path onto one store: the clone itself, a
    spelling of it through a symlink or a trailing `.`, and a linked worktree
    of it configured as a target of its own. Grouping on the path instead
    would put two linked-worktree targets in two groups, and a branch name
    both derive would read as each one's alone.

    `None` when the store cannot be read at all -- a path that will not
    resolve, a git that cannot be run, a directory that is no repository --
    which is answered here rather than let out, because grouping runs before
    any repository has been read and an exception escaping it ends the whole
    scan, every healthy repository in it included.
    """
    store = probes._checkout_clone(spec.target_root)
    if store is None:
        log.warning(
            "could not tell which repository %s is configured at (%s); "
            "refusing it and counting it a claimant on every clone",
            spec.slug, spec.target_root,
        )
    return store


def _specs_by_clone(
    specs: Sequence[_config_models.RepoSpec],
) -> tuple[CloneGroups, tuple[str, ...]]:
    """The specs grouped by the ref store they share, and whose store did not read.

    Grouped on the git common directory, so entries reaching one store by
    different paths land in one group, where a branch name two of them derive
    is ambiguous between them, instead of separate groups each claiming that
    branch for itself. The reads still run against a path a spec configures,
    which is the one the rest of the worktree owners lock and run git in.

    An entry whose store would not read is added to every group rather than
    dropped: nothing established which store it shares, so it is still one of
    the repositories that could have published what any clone holds, and the
    second half of the answer is what says the scan will not report for it.
    """
    grouped: CloneGroups = {}
    unresolved: list[_config_models.RepoSpec] = []
    for spec in specs:
        store = _ref_store(spec)
        if store is None:
            unresolved.append(spec)
        else:
            grouped[store] = (*grouped.get(store, ()), spec)
    return (
        {store: (*members, *unresolved) for store, members in grouped.items()},
        tuple(unread.slug for unread in unresolved),
    )
