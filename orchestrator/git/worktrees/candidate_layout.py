# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Classify a discovered candidate by its current, legacy, and remote-only names.

Layout is read from the full set of discovered refs and checkout paths, so a
host spanning the namespace migration retains its mixed-layout identity.
"""
from __future__ import annotations

from orchestrator.git.worktrees import (
    naming as _naming,
    paths,
)
from orchestrator.git.worktrees.candidates import CandidateLayout, IssueArtifacts


def _candidate_layout(
    artifacts: IssueArtifacts, local: tuple[str, ...],
) -> CandidateLayout:
    """Which layout this candidate's artifacts were published under.

    `REMOTE_ONLY` is answered first and on where the artifacts are rather than
    on what they are called: an issue this host holds no checkout and no branch
    for leaves an operator nothing here to look at, whichever name the remote's
    copy carries, and that is the fact the reading is spent on.

    The rest is the artifacts' own names. Every one of them is a name `paths`
    derives, on both sides -- the slug-namespaced branch and the checkout under
    the per-repository root, or the flat branch and the checkout directly under
    `WORKTREES_DIR` -- so the question is only which layouts are represented.
    Both is the shape a migration leaves and no single derivation produces; the
    flat one alone is an issue that was in flight when namespacing landed.
    """
    if not artifacts.worktrees and not local:
        return CandidateLayout.REMOTE_ONLY
    held = frozenset(artifacts.branches) | frozenset(
        str(worktree) for worktree in artifacts.worktrees
    )
    legacy = bool(held & frozenset(_legacy_names(artifacts)))
    current = bool(held & frozenset(_current_names(artifacts)))
    if legacy and current:
        return CandidateLayout.MIXED
    return CandidateLayout.LEGACY if legacy else CandidateLayout.CURRENT


def _current_names(artifacts: IssueArtifacts) -> tuple[str, ...]:
    """What this issue's artifacts are called under the layout in use now."""
    return (
        _naming._branch_name(artifacts.spec, artifacts.issue_number),
        str(paths._worktree_path(artifacts.spec, artifacts.issue_number)),
    )


def _legacy_names(artifacts: IssueArtifacts) -> tuple[str, ...]:
    """What they were called before slug namespacing landed."""
    return (
        _naming._legacy_branch_name(artifacts.issue_number),
        str(paths._legacy_worktree_path(artifacts.issue_number)),
    )
