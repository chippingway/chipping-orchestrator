# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Classify a discovered candidate by where its current-layout artifacts are.

The reading is taken while the clone's own branches are still apart from what
the remote carries, since nothing downstream can tell the two apart again.
"""
from __future__ import annotations

from orchestrator.git.worktrees.candidates import CandidateLayout, IssueArtifacts


def _candidate_layout(
    artifacts: IssueArtifacts, local: tuple[str, ...],
) -> CandidateLayout:
    """Whether this host still holds anything of the candidate it names.

    `REMOTE_ONLY` is answered on where the artifacts are rather than on what
    they are called: an issue this host holds no checkout and no branch for
    leaves an operator nothing here to look at. Every name a candidate can
    carry is the current layout's own derivation, so there is no other
    distinction left to draw.
    """
    if not artifacts.worktrees and not local:
        return CandidateLayout.REMOTE_ONLY
    return CandidateLayout.CURRENT
