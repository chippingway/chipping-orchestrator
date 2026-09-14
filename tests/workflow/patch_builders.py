# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Focused mock groups for the shared workflow runner."""
from __future__ import annotations

from unittest.mock import MagicMock

from orchestrator.git.publication import probes as _publication_probes
from orchestrator.git.verification.models import VerifyResult
from tests.workflow import patch_models as _support, patch_publication as _patch_publication
from tests.workflow.patch_measurement import _measurement_mocks
from tests.workflow.patch_models import _WorkflowRunContext
from tests.workflow.patch_readings import _AnchorAnswers, _ForkPoints, _HeadReadings, _RemoteTipAnswers, _TreeReadings
from tests.workflow.repo_values import _FAKE_WT


def _execution_mocks(context: _WorkflowRunContext) -> dict[str, object]:
    new_commits = MagicMock()
    commit_sequence = context.has_new_commits
    if isinstance(commit_sequence, (list, tuple)):
        new_commits.side_effect = list(commit_sequence)
    else:
        new_commits.return_value = bool(commit_sequence)
    return {
        "run_agent": _support._as_mock(context.run_agent),
        "_has_new_commits": new_commits,
        "_worktree_dirty_files": MagicMock(
            return_value=list(context.dirty_files),
        ),
        # The status form answers the same read for the caller that has to
        # prove a clean tree, so both are driven by one seed -- and a test
        # about an unreadable worktree flips `tree_readable` alone. A test
        # about a tree that changes UNDER a publication seeds the readings
        # themselves, since the whole point of that race is one reading
        # disagreeing with the next.
        "_worktree_status": MagicMock(side_effect=_TreeReadings(context)),
        "_committed_paths_since": MagicMock(
            return_value=list(context.committed_paths),
        ),
        "_revision_contains_path": MagicMock(
            return_value=context.head_contains_path,
        ),
    }


def _worktree_mocks(context: _WorkflowRunContext) -> dict[str, object]:
    return {
        # The handoff's own move of the branch onto a plan PR's live head,
        # answering with the tip it landed on: the head that was asked for by
        # default, and whatever a test about a deleted branch or a move that
        # could not be made names instead.
        "_anchor_pr_worktree": MagicMock(side_effect=_AnchorAnswers(context)),
        "_ensure_worktree": MagicMock(return_value=context.issue_worktree),
        "_ensure_pr_worktree": MagicMock(return_value=_FAKE_WT),
        "_ensure_decompose_worktree": MagicMock(return_value=_FAKE_WT),
        "_decompose_worktree_path": MagicMock(return_value=_FAKE_WT),
    }


def _cleanup_mocks(context: _WorkflowRunContext) -> dict[str, object]:
    return {
        "_cleanup_decompose_worktree": MagicMock(),
        "_cleanup_question_worktree": MagicMock(),
        "_cleanup_terminal_branch": MagicMock(),
        "_branch_has_unpushed_commits": MagicMock(
            return_value=context.unpushed_branch,
        ),
        "_branch_tip_sha": MagicMock(return_value=context.branch_tip_sha),
    }


def _publication_mocks(context: _WorkflowRunContext) -> dict[str, object]:
    if context.fallback_prefix is None:
        prefix_mock = MagicMock(
            side_effect=_support._default_infer_subject_prefix,
        )
    else:
        prefix_mock = MagicMock(return_value=context.fallback_prefix)
    return {
        # A bool is the ordinary seed -- the push lands, or it does not. A
        # callable is taken as the push itself, which is what a tick pushing
        # twice needs: the second push is leased against the head the first
        # left, so the pull request has to move under it.
        "_push_branch": _patch_publication._published_branch(context.push_branch),
        "_head_sha": MagicMock(side_effect=_HeadReadings(context)),
        "_head_on_branch": MagicMock(
            return_value=bool(context.head_on_branch),
        ),
        "_remote_branch_tip": MagicMock(
            side_effect=_RemoteTipAnswers(context),
        ),
        # The base a round pins is the remote's answer plus the object behind
        # it, so the presence probe and the fetch that would supply it are
        # neutralized beside the read. A tick here has whatever base it was
        # seeded with; what happens when the store really lacks one is pinned
        # against real repositories in the discussion stage's own tests.
        "_commit_present": MagicMock(return_value=True),
        # Whether one commit's history contains another. A bool answers both
        # directions the same, which is the ordinary branch a plan sits on top
        # of; a test about a branch somebody pushed to has to tell them apart,
        # since the published commit contains the remote tip in one direction
        # and is contained by it in the other -- so a callable answering
        # `(worktree, ancestor, revision)` is taken as the probe itself.
        "_commit_contains": _support._as_mock(context.commit_contains),
        "_authed_target_fetch": MagicMock(
            return_value=MagicMock(returncode=0, stdout="", stderr=""),
        ),
        "_first_commit_subject": MagicMock(
            return_value=context.first_commit_subject,
        ),
        "_infer_subject_prefix": prefix_mock,
    }


def _validation_mocks(context: _WorkflowRunContext) -> dict[str, object]:
    verify_result = context.verify_result
    if verify_result is None:
        verify_result = VerifyResult(status="ok")
    return {
        "_squash_and_force_push": _patch_publication._squashed(context.squash_result),
        "_run_verify_commands": MagicMock(return_value=verify_result),
        "_rebase_in_progress": MagicMock(
            return_value=bool(context.rebase_in_progress),
        ),
    }


def _conflict_mocks(context: _WorkflowRunContext) -> dict[str, object]:
    fetch_result = context.authed_fetch_result
    if fetch_result is None:
        fetch_result = MagicMock(returncode=0, stdout="", stderr="")
    return {
        "_authed_fetch": _patch_publication._fetched(fetch_result),
        # Where the checkout stands against the remote tip it was compared
        # with, as ONE reading: the counts, the head they were taken against
        # -- which is what the push they license is pinned to -- and whether
        # the reading happened at all.
        "_branch_divergence": MagicMock(
            return_value=_publication_probes._BranchDivergence(
                tip=context.fetched_branch_tip,
                ahead=context.branch_ahead_behind[0],
                behind=context.branch_ahead_behind[1],
                readable=context.branch_divergence_readable,
            ),
        ),
        # Where one revision's branch left the base, which is what the two
        # ends of a rebase's own rewrite record are read over.
        "_fork_point": MagicMock(side_effect=_ForkPoints(context)),
    }


_MOCK_BUILDERS = (
    _execution_mocks,
    _worktree_mocks,
    _cleanup_mocks,
    _publication_mocks,
    _validation_mocks,
    _conflict_mocks,
    _measurement_mocks,
)


def _build_workflow_mocks(
    context: _WorkflowRunContext,
) -> dict[str, object]:
    workflow_mocks: dict[str, object] = {}
    for build_group in _MOCK_BUILDERS:
        workflow_mocks.update(build_group(context))
    return workflow_mocks
