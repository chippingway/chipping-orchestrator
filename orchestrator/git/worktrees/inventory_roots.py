# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Group configured repositories by the clone whose local artifacts they share.

Unresolved roots stay represented in the grouping so their possible claims
cannot be mistaken for evidence that another repository owns an artifact.
Both local and remote inventory scans use this same grouping.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path

from orchestrator.config import models as _config_models

# The channel is named for the worktree-lifecycle domain rather than for this
# module's path: operators filter the rendered `orchestrator.worktree_lifecycle`
# prefix and attach handlers to it, so a repository this scan will not answer
# for says so where their filters already point.
log = logging.getLogger("orchestrator.worktree_lifecycle")

# The specs on each clone a scan reads, keyed by the path their spellings
# agree on: one group is one ref store, and everyone in it is a claimant to
# what that store holds.
CloneGroups = dict[Path, tuple[_config_models.RepoSpec, ...]]


def _resolved_root(spec: _config_models.RepoSpec) -> Path | None:
    """The clone this spec configures, as the one path its spellings agree on.

    `None` when the path cannot be resolved at all, which is a failure worth
    catching here rather than letting out: resolution is what says whether two
    entries are on one clone, it runs before any repository has been read, and
    an exception escaping it ends the whole scan -- every healthy repository
    in it included -- over one entry's `target_root`. What it costs to fail is
    also version-dependent, so it cannot be reasoned about from the value: a
    root reached through a symlink loop raises `RuntimeError` out of
    `Path.resolve` on Python 3.12 and comes back unchanged on 3.13.

    The caller refuses that entry -- nothing about it is reported -- while
    still grouping it under the path as written, because the two are different
    questions. Whether this scan can answer for a repository is one; whether
    that repository could have published what is on the clone it names is the
    other, and dropping it from its group answers the second wrongly: the
    legacy flat branch there would lose a claimant and read as unambiguously
    some other entry's.
    """
    try:
        return spec.target_root.resolve()
    except (OSError, RuntimeError) as resolve_error:
        log.warning(
            "could not resolve the clone %s is configured at (%s): %s",
            spec.slug, spec.target_root, resolve_error,
        )
        return None


def _specs_by_clone(
    specs: Sequence[_config_models.RepoSpec],
) -> tuple[CloneGroups, tuple[str, ...]]:
    """The specs grouped by the clone they name, and whose path did not resolve.

    Grouped on the resolved path, so two entries spelling one clone
    differently -- through a symlink, with a trailing `.` -- land in one group
    with one ambiguous legacy branch between them instead of two groups each
    claiming that branch for itself. The reads still run against a path a spec
    configures, which is the one the rest of the worktree owners lock and run
    git in.

    An entry whose path would not resolve is grouped under that path as
    written rather than dropped: it is still one of the repositories that
    could have published what its clone holds, and the second half of the
    answer is what says the scan will not report for it.
    """
    grouped: CloneGroups = {}
    unresolved: list[str] = []
    for spec in specs:
        resolved = _resolved_root(spec)
        if resolved is None:
            unresolved.append(spec.slug)
        clone = resolved or spec.target_root
        grouped[clone] = (*grouped.get(clone, ()), spec)
    return grouped, tuple(unresolved)
