# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Repository-configuration data types.

``RepoSpec`` is the per-repo identity threaded through the workflow;
``RepoEnvEntry`` is the intermediate record produced while tokenizing one
``REPOS`` entry. ``repositories`` parses environment strings and constructs
these records. The package's ``default_repo_specs`` accessor returns the
configured list resolved at import.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RepoSpec:
    """Per-repo identity threaded through the workflow.

    Each workflow tick carries its repository identity explicitly so several
    repositories can run in one process without mutating global settings.

    `remote_name` is the name of the git remote in `target_root` that points
    at this repo on GitHub. Defaults to `origin`; override when the local
    clone uses several remotes (e.g. a public `origin` and a private fork
    under a different remote name) and the orchestrator should drive the
    non-default one.

    `parallel_limit` caps how many issues this repo may advance in parallel
    on a single tick. Defaults to 1 (legacy one-at-a-time behavior); each
    `REPOS` entry can override it via the optional fifth pipe-separated
    field. The global `MAX_PARALLEL_ISSUES_GLOBAL` ceiling applies across
    all repos to cap-counted handlers regardless of any one repo's
    `parallel_limit`; no-agent family buckets (`blocked` / `umbrella`) are
    cap-exempt by design (a parent dep-graph walk must always get its turn)
    and are excluded from both `parallel_limit` and
    `MAX_PARALLEL_ISSUES_GLOBAL`.
    """

    slug: str
    target_root: Path
    base_branch: str
    remote_name: str = "origin"
    parallel_limit: int = 1


@dataclass(frozen=True)
class RepoEnvEntry:
    """Required fields and raw options from one ``REPOS`` entry."""

    entry_no: int
    slug: str
    target_root: str
    base_branch: str
    remote_name: str
    parallel_limit_raw: str | None
