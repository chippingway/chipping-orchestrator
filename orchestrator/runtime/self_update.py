# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Git probes for detecting self-modifying upstream merges.

They run only in the orchestrator's own source checkout -- an ordinary clone,
a linked worktree, or an editable install of either, the checkout `run.sh`
relaunches on new code -- as `config.layout.is_source_checkout` proves it at
`REPO_ROOT` itself. An installed package's root is an environment's
`site-packages`, where git would discover whatever repository happens to
enclose it, so an installed package gets no restart baseline: it never runs
these probes, never fetches, and never exits for a merge. Its version changes
only through an explicit upgrade or reinstall.

The base branch probed here is the orchestrator's own
(`ORCHESTRATOR_BASE_BRANCH`), not the target repository's, so a target whose
default branch differs never reads as the orchestrator having been updated.
Only a forward move that touched `orchestrator/` counts: anything else the
loop keeps polling through.
"""
from __future__ import annotations

import subprocess

from orchestrator import config
from orchestrator.config import layout as _config_layout

_RUNTIME_SOURCE_PREFIX = "orchestrator/"


def git(*args: str) -> subprocess.CompletedProcess:
    """Run a captured git command against the orchestrator checkout."""
    return subprocess.run(
        ["git", *args],
        cwd=str(config.REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def own_head_sha() -> str | None:
    """Return the orchestrator source checkout's HEAD when resolvable.

    Outside a source checkout no HEAD is asked for, so an enclosing
    repository's never stands in, and the ``None`` returned there keeps the
    loop from probing for a merge at all.
    """
    if not _config_layout.is_source_checkout(config.REPO_ROOT):
        return None
    head_revision = git("rev-parse", "HEAD")
    return (
        head_revision.stdout.strip()
        if head_revision.returncode == 0
        else None
    )


def self_modifying_merge_happened(start_sha: str) -> bool:
    """Detect a forward upstream move that touched runtime source files."""
    git("fetch", "--quiet", "origin", config.ORCHESTRATOR_BASE_BRANCH)
    current_sha = git(
        "rev-parse",
        f"origin/{config.ORCHESTRATOR_BASE_BRANCH}",
    ).stdout.strip()
    if not current_sha or current_sha == start_sha:
        return False
    if git(
        "merge-base",
        "--is-ancestor",
        start_sha,
        current_sha,
    ).returncode != 0:
        return False
    changed_paths = git(
        "diff",
        "--name-only",
        start_sha,
        current_sha,
    ).stdout
    return any(
        changed_path.startswith(_RUNTIME_SOURCE_PREFIX)
        for changed_path in changed_paths.splitlines()
    )
