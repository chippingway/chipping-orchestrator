# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Local artifact inventory and the candidates discovered across host and remote.

These records carry discovery evidence only. Eligibility verdicts belong to
models, and the outcome of actually reclaiming a candidate belongs to
maintenance_results.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from orchestrator import config


@dataclass(frozen=True)
class IssueArtifacts:
    """The orchestrator-owned artifacts one issue left in one repository.

    An issue is in a scan because an `issue-<n>` checkout of it still stands,
    because a branch in that clone's orchestrator-owned namespace names it, or
    because both do -- which is why either half may be empty. Never both: an
    entry with no checkout and no branch is an issue nothing on this host
    attests to, and the scan does not invent one.

    Both halves are tuples, and for the same reason: this orchestrator has
    published an issue under two layouts, and a host that was running across
    the migration can be holding both at once. `branches` carries the
    slug-namespaced name and the legacy flat one; `worktrees` carries the
    checkout under the spec's own root and the legacy one directly under
    `WORKTREES_DIR`. Each is ordered current-first, which is the order a
    teardown takes them in.

    Two entries for one issue therefore cannot happen -- the layouts are
    several names for one issue, not several issues.
    """

    spec: config.RepoSpec
    issue_number: int
    worktrees: tuple[Path, ...]
    branches: tuple[str, ...]


@dataclass(frozen=True)
class ArtifactInventory:
    """Every issue one scan attributed, and the repositories it would not answer for.

    `refused` names the slugs whose picture this scan does not stand behind:
    a ref store or worktrees root it could not read. Their issues are left out
    entirely rather than reported in part, because a partial list of one
    repository's artifacts is indistinguishable from a complete one and reads
    as the same fact. A caller that acts on absence -- nothing here, so
    nothing to adopt or clean up -- has to skip those repositories, and this
    field is how it knows which.

    `withheld` is the same refusal one granularity down: a repository and an
    issue number this scan will not answer for, while still answering for the
    rest of that repository. It exists for the artifact whose name says nothing
    -- the flat pre-namespacing checkout, which several entries on one clone
    derive identically -- because a tree nobody may take is standing on one of
    that issue's branches, and reporting the branch alone would hand a teardown
    a ref to delete out from under a live checkout. A caller reading only
    `issues` would see that issue absent and go looking for it somewhere else,
    which is exactly what a wider scan does.

    `issues` is ordered by slug and then issue number, and so are both
    refusals, so two scans of an unchanged host produce equal answers.
    """

    issues: tuple[IssueArtifacts, ...]
    refused: tuple[str, ...]
    withheld: tuple[tuple[str, int], ...] = ()


class CandidateLayout(StrEnum):
    """Which of the layouts this orchestrator has published a candidate under.

    Named on the candidate rather than worked out again by every reader,
    because it is the one thing about a candidate that says how it came to
    exist. `CURRENT` is the slug-namespaced branch this orchestrator publishes
    now and the per-repository checkout beside it; `LEGACY` is the flat
    `orchestrator/issue-<n>` an issue in flight when namespacing landed is
    still on; `MIXED` is an issue carrying both names at once, which a
    migration leaves behind and which no single derivation would ever produce.

    `REMOTE_ONLY` is where the artifact is rather than what it is called, and
    it wins over the other three when nothing local is left: a candidate this
    host holds no checkout and no branch for is one an operator has nothing to
    look at here for, whichever name the remote's copy carries.
    """

    CURRENT = "current"
    LEGACY = "legacy"
    REMOTE_ONLY = "remote_only"
    MIXED = "mixed"


@dataclass(frozen=True)
class MaintenanceCandidate:
    """One issue's artifacts, and the layout they were published under.

    The pair rather than the artifacts alone, because the layout is a reading
    taken where both halves of the discovery were still in hand -- what the
    clone holds and what the remote does -- and nothing downstream can
    reconstruct it: by the time a teardown has finished, the branch that said
    the candidate was remote-only is gone.
    """

    artifacts: IssueArtifacts
    layout: CandidateLayout


@dataclass(frozen=True)
class MaintenanceScan:
    """Every candidate the discovery found, and what it will not answer for.

    `refused` carries the same fact the scan's own does, one step wider: a
    repository whose checkout root, ref store, or remote listing could not be
    read is left out entirely rather than reported in part, because a partial
    list of what a repository still holds reads exactly like a complete one.

    `candidates` is ordered by slug and then issue number, so two discoveries
    of an unchanged host and remote produce equal answers.
    """

    candidates: tuple[MaintenanceCandidate, ...]
    refused: tuple[str, ...]
