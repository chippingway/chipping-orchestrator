# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Stateful git-reading doubles driven by a workflow run context."""
from __future__ import annotations

from collections.abc import Mapping

from orchestrator.git.verification.status import _WorktreeStatus
from tests.workflow.patch_models import _WorkflowRunContext
from tests.workflow.repo_values import (
    BASE_TIP_SHA,
)


class _HeadReadings:
    """What the checkout's own head reads as, this reading.

    A tuple seeds a head that MOVES between readings -- one probe takes it
    before a run and another after -- and its last entry answers every reading
    past it, so a caller that asks once more than a test counted reads the
    head the test left the checkout on rather than running out of answers.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._readings = list(context.head_shas)
        self._reads = 0

    def __call__(self, worktree):
        reading = min(self._reads, len(self._readings) - 1)
        self._reads += 1
        return self._readings[reading]


class _TreeReadings:
    """What `git status` reports about the worktree, this reading.

    A tuple seeds a tree that CHANGES between readings -- clean when the
    disposition proves it and carrying something by the time the publication
    proves it again -- and its last entry answers every reading past it, so a
    caller that asks once more than a test counted reads the tree the test
    left the checkout in rather than running out of answers.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._readings = list(context.tree_states) or [
            _WorktreeStatus(
                readable=context.tree_readable,
                paths=tuple(context.dirty_files),
            ),
        ]
        self._reads = 0

    def __call__(self, worktree):
        reading = min(self._reads, len(self._readings) - 1)
        self._reads += 1
        return self._readings[reading]


class _ForkPoints:
    """The commit one revision's contribution is read over, this reading.

    A mapping answers per revision, which is what a rebase needs: the head it
    replayed and the head it produced fork from different commits, and that
    difference is the whole of what the two ends of one rewrite record say.
    Anything else answers every revision alike, so a case about a fork point
    nothing could read seeds "" once rather than per commit.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._seeded = context.fork_points

    def __call__(self, spec, worktree, revision: str):
        if isinstance(self._seeded, Mapping):
            return self._seeded.get(revision, "")
        return self._seeded


class _AnchorAnswers:
    """What the handoff's move of a branch onto a PR head reports.

    The SHA the branch ended up on, since that is what the baseline the spawn
    path reads back is then measured by. `True` is the ordinary answer -- it
    landed on the head that was asked for -- a string is a test naming a
    different tip (the base, where a plan branch the remote no longer has sends
    it), and `None` is the move that established nothing, which holds the
    handoff.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._context = context

    def __call__(self, spec, issue_number, *, branch: str, head_sha: str):
        landed = self._context.anchor_pr_head
        if landed is True:
            # No head named is the caller asking for the base outright, which
            # is where a finished pull request's branch ends up.
            return head_sha or BASE_TIP_SHA
        return landed or None


class _RemoteTipAnswers:
    """Answer the remote-tip read by which branch it is asked about.

    One seam, two questions: the base a round pins its diff against, and the
    per-issue branch a publication is about to move. A single value would
    answer both with the same SHA, so no test could seed one without seeding
    the other -- and the publication gate reads the second to decide whether
    the branch is still one it may overwrite.
    """

    def __init__(self, context: _WorkflowRunContext) -> None:
        self._context = context

    def __call__(self, spec, worktree, branch: str):
        if branch == spec.base_branch:
            return self._context.remote_base_tip
        return self._context.remote_branch_tip
