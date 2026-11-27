# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Locate the original commits after a squash refusal for the workflow's park notice."""
from __future__ import annotations

from pathlib import Path

from orchestrator.git.measurement import commits as measurement_commits
from orchestrator.git.publication import models, resume
from orchestrator.git.verification import probes as verification_probes


def _where_the_branch_stands(worktree: Path, recorded_head: str | None) -> str:
    """Locate the approved commits for the park notice after a squash refusal.

    The caller supplies the original head from the pinned collapse record, or
    `None` if the record is unreadable. A missing head on either side leaves
    the location unknown. Matching heads leave the approved commits intact.

    If the checkout moved, the recorded head must still resolve locally for
    the notice to direct the operator to it. An ancestor of HEAD places the
    commits in the branch's history, buried under later work. Otherwise the
    notice directs the operator to the reflog for the collapsed history.
    """
    head = verification_probes._head_sha(worktree)
    if recorded_head is None or not head:
        return models.BRANCH_UNKNOWN
    if head == recorded_head:
        return models.BRANCH_INTACT
    named = measurement_commits._prove_candidate_commit(
        worktree, recorded_head,
    )
    if not named.is_frozen:
        return models.BRANCH_UNKNOWN
    if resume._is_ancestor(worktree, recorded_head, head):
        return models.BRANCH_BURIED
    return models.BRANCH_COLLAPSED
