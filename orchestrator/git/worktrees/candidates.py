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

from orchestrator.config import models as _config_models


@dataclass(frozen=True)
class IssueArtifacts:
    """The orchestrator-owned artifacts one issue left in one repository.

    An issue is in a scan because its `issue-<n>` checkout under the spec's
    own root still stands, because the clone or its remote carries the issue's
    repository-scoped branch, or because both do -- which is why either half
    may be empty. Never both: an entry with no checkout and no branch is an
    issue nothing on this host attests to, and the scan does not invent one.

    Each half holds at most the one name the current layout derives for the
    issue -- `paths._worktree_path` and `naming._branch_name` -- and is a
    tuple so an absent artifact is the empty one rather than a sentinel. A
    flat checkout or branch an earlier layout left is never on it: nothing
    attributes one to a repository, so no reclamation is spent on it.
    """

    spec: _config_models.RepoSpec
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

    `issues` is ordered by slug and then issue number, and so is the refusal,
    so two scans of an unchanged host produce equal answers.
    """

    issues: tuple[IssueArtifacts, ...]
    refused: tuple[str, ...]


class CandidateLayout(StrEnum):
    """Where a candidate's current-layout artifacts were found.

    Named on the candidate rather than worked out again by every reader,
    because it is a reading only the discovery can take. `CURRENT` is a
    candidate this host still holds its repository-scoped checkout or branch
    for; `REMOTE_ONLY` is one whose branch only the remote still carries,
    which leaves an operator nothing on this host to look at.
    """

    CURRENT = "current"
    REMOTE_ONLY = "remote_only"


@dataclass(frozen=True)
class MaintenanceCandidate:
    """One issue's artifacts, and where the discovery found them.

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
