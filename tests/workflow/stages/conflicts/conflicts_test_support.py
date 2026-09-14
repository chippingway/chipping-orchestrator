# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Typed resolving-conflict scenarios for the stage's focused tests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

from orchestrator.workflow.engine import content_hash as _content_hash
from tests.support.fakes import (
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    make_issue,
)
from tests.workflow.git_owners import seam_patch
from tests.workflow.other_labels import LABEL_RESOLVING_CONFLICT
from tests.workflow.patch_models import _agent
from tests.workflow.patch_runner import _PatchedWorkflowMixin
from tests.workflow.repo_values import (
    BACKEND_CLAUDE,
    CONTRIBUTION_DIGEST,
    FORK_POINT_SHA,
    MEASURED_CANDIDATE_SHA,
    STATE_OPEN,
)
from tests.workflow.value_helpers import _issue_branch

_CONFLICT_ISSUE_NUMBER = 200
_CONFLICT_BRANCH = _issue_branch(_CONFLICT_ISSUE_NUMBER)
_CONFLICT_PR_NUMBER = 800
# The head the pull request is standing on, which is the same head this stage
# reads out of the checkout before it rebases and leases its force-push
# against: the branch is proved in sync with its remote before any of this
# runs, so the two are one fact and the size gate refuses a call whose two
# readings of it disagree. A whole git object id, because a commit field is
# read at its exact length -- an abbreviation is no head at all there.
CONFLICT_PR_HEAD_SHA = "be40e5ba" * 5
_CONFLICT_PR_HEAD_SHA = CONFLICT_PR_HEAD_SHA

# A pull request somebody else pushed to while this tick was in flight.
MOVED_PR_HEAD_SHA = "cafe1234" * 5

# The head a resolution leaves the checkout on. It IS the commit the size
# gate proves that checkout to, because in production they are one read of one
# worktree: the stage names the commit it means to publish and the gate
# refuses a checkout standing anywhere else, so a fixture that spelled them
# differently would be modelling the race rather than the tick.
RESOLVED_HEAD_SHA = MEASURED_CANDIDATE_SHA


@dataclass(frozen=True)
class _ConflictSeedContext:
    merge_succeeded: bool = True
    conflicted_files: tuple = ()
    head_shas: tuple = ("before", "after")
    push_branch: bool = True
    run_agent_result: Any = None
    pr_state: str = STATE_OPEN
    pr_merged: bool = False
    extra_state: Any = None


@dataclass(frozen=True)
class _ConflictRunContext:
    merge_succeeded: bool = True
    conflicted_files: tuple = ()
    head_shas: tuple = ("before", "after")
    push_branch: bool = True
    run_agent_result: Any = None
    fetch_returncode: int = 0
    # What `_authed_fetch` answers. A sequence answers one reading at a time,
    # which is what a tick whose branch fetch lands and whose base fetch does
    # not needs.
    authed_fetch_result: Any = None
    # What `git rev-list --count HEAD..origin/<base>` answers. The recovered
    # push is routed by it -- on base it completes a round of its own, behind
    # base it is the preamble to a rebase that owns one -- and it rides the
    # same `_git` seam the fetch does, which reads only the return code.
    behind_base: str = "0\n"
    dirty_files: tuple = ()
    # Whether the tree read HAPPENED at all. False is the checkout whose
    # `git status` established nothing, which names no paths -- exactly what
    # a tree with nothing in it names -- so a clean-rebase exit taken on it
    # would hand a reviewer a checkout nobody read.
    tree_readable: bool = True
    rebase_in_progress: bool = False
    # What the size gate's count reports for the resolution about to be
    # pushed. A resolution is a candidate for a pull request the remote
    # already carries, so a case about one past the ceiling seeds it here.
    added_lines: Any = 0
    # What the checkout's own head proves to. In sync with its remote is not
    # the same claim as CARRYING the commit a settled receipt names, so a case
    # about a replacement host rebuilt at a moved pull request says so here.
    candidate_commit: Any = None
    # Where the checkout stands against the remote PR head. In sync is the
    # ordinary reading a rebase runs from; ahead of it is the crash-recovery
    # shape, where commits an earlier tick made never reached the remote.
    branch_ahead_behind: tuple = (0, 0)
    # Whether that reading HAPPENED. A ref nothing could resolve answers zero
    # and zero, which is what an in-sync branch answers, so a case about a
    # probe that established nothing says so here.
    branch_divergence_readable: bool = True
    # What the two contributions a replay sits between fingerprint to. One
    # value answers both alike, which is the history-only rebase a transfer
    # is granted for; a mapping keyed on the commit seeds them apart, which
    # is what a replay that moved a byte reads as.
    contribution_digest: Any = CONTRIBUTION_DIGEST
    # Where each revision's branch forked from the base, which is the end each
    # side of a rewrite record is read over. A mapping tells the pre-replay
    # head's fork point from the replayed one's, and "" is the reading that
    # did not happen.
    fork_points: Any = FORK_POINT_SHA


@dataclass(frozen=True)
class _ConflictMocks:
    merge: MagicMock
    git: MagicMock
    git_hardened: MagicMock


def _seed_conflict(owner, context: _ConflictSeedContext):
    github = FakeGitHubClient()
    issue = make_issue(
        owner.issue_number,
        label=LABEL_RESOLVING_CONFLICT,
    )
    github.add_issue(issue)
    pull_request = FakePR(
        number=owner.pr_number,
        head_branch=owner.issue_branch,
        head=FakePRRef(sha=owner.pr_head_sha),
        mergeable=False,
        check_state="success",
        merged=context.pr_merged,
        state=context.pr_state,
    )
    github.add_pr(pull_request)
    state = {
        "pr_number": owner.pr_number,
        "branch": owner.issue_branch,
        "dev_agent": BACKEND_CLAUDE,
        "dev_session_id": "dev-sess",
        "review_round": 2,
        "conflict_round": 0,
    }
    if context.extra_state:
        state.update(context.extra_state)
    github.seed_state(owner.issue_number, **state)
    return github, issue, pull_request


def _build_conflict_mocks(context: _ConflictRunContext) -> _ConflictMocks:
    fetch_result = MagicMock(
        returncode=context.fetch_returncode,
        stdout=context.behind_base,
        stderr="",
    )
    return _ConflictMocks(
        merge=MagicMock(return_value=(
            context.merge_succeeded,
            list(context.conflicted_files),
        )),
        git=MagicMock(return_value=fetch_result),
        git_hardened=MagicMock(return_value=fetch_result),
    )


def _run_conflict_merge(owner, github, issue, context):
    agent_result = context.run_agent_result or _agent(
        session_id="dev-sess",
        last_message="resolved",
    )
    mocks = _build_conflict_mocks(context)
    with (
        seam_patch("_rebase_base_into_worktree", mocks.merge),
        seam_patch("_git", mocks.git),
        seam_patch("_git_hardened", mocks.git_hardened),
    ):
        workflow_mocks = owner._run_resolving_conflict(
            github,
            issue,
            run_agent=agent_result,
            push_branch=context.push_branch,
            head_shas=context.head_shas,
            dirty_files=context.dirty_files,
            tree_readable=context.tree_readable,
            rebase_in_progress=context.rebase_in_progress,
            added_lines=context.added_lines,
            branch_ahead_behind=context.branch_ahead_behind,
            branch_divergence_readable=context.branch_divergence_readable,
            candidate_commit=context.candidate_commit,
            authed_fetch_result=context.authed_fetch_result,
            contribution_digest=context.contribution_digest,
            fork_points=context.fork_points,
        )
    return workflow_mocks, mocks.merge, mocks.git


class _ResolvingConflictMixin(_PatchedWorkflowMixin):
    """Seed and run resolving-conflict scenarios without shelling out."""

    issue_number = _CONFLICT_ISSUE_NUMBER
    issue_branch = _CONFLICT_BRANCH
    pr_number = _CONFLICT_PR_NUMBER
    pr_head_sha = _CONFLICT_PR_HEAD_SHA

    def _run_resolving_conflict(self, github, issue, **run_options):
        """Run the handler over a world whose two head readings agree.

        The remote-tracking ref the ahead/behind comparison is taken against
        and the head the pull request reports are one commit in every
        ordinary world -- the fetch a line earlier is what put the first
        there. A recovered push is PINNED to the first and the gate checks it
        against the second, so a fixture that answered them differently would
        make every recovery read as a publication somebody moved. A case
        about one that really did move says so.
        """
        run_options.setdefault("fetched_branch_tip", self.pr_head_sha)
        return super()._run_resolving_conflict(github, issue, **run_options)

    def _pinned(self, github) -> dict:
        """What this issue's pinned comment says once a tick has finished."""
        return github.pinned_data(self.issue_number)

    def _seed(self, **seed_options):
        return _seed_conflict(
            self,
            _ConflictSeedContext(**seed_options),
        )

    def _run_with_merge(self, github, issue, **run_options):
        return _run_conflict_merge(
            self,
            github,
            issue,
            _ConflictRunContext(**run_options),
        )

    def _seed_with_baseline_hash(self, github, issue, **extra):
        state_data = github.pinned_data(self.issue_number)
        state_data.update(extra)
        state_data["user_content_hash"] = (
            _content_hash._compute_user_content_hash(issue, set())
        )
        github.seed_state(self.issue_number, **state_data)
