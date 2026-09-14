# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Repo specs, slugs, and pinned states shared by the path-owner tests."""

from __future__ import annotations

from pathlib import Path

from orchestrator.config import models as _config_models
from orchestrator.git.worktrees import naming as _naming
from orchestrator.github.pinned_state import PinnedState

BASE_BRANCH = "main"
MIGRATION_REPO_SLUG = "chippingway/orchestrator"
MIGRATION_TARGET_ROOT = Path("/tmp/x")
ALICE_REPO_SLUG = "alice/repo"
BOB_REPO_SLUG = "bob/repo"
LOCK_SUFFIX_SLUG = "owner/foo.lock"
DOUBLE_DOT_SLUG = "owner/foo..bar"
BRANCH_KEY = "branch"
LEGACY_BRANCH = "orchestrator/issue-7"
NAMESPACED_BRANCH = "orchestrator/chippingway__orchestrator/issue-7"
STAGE_LAYOUT_ISSUE_NUMBER = 11
SHARED_BRANCH_ISSUE_NUMBER = 15
PR_NUMBER = 42


def _spec(repo_slug: str) -> _config_models.RepoSpec:
    return _config_models.RepoSpec(
        slug=repo_slug,
        target_root=Path(f"/tmp/{_naming._sanitize_slug(repo_slug)}-target"),
        base_branch=BASE_BRANCH,
    )


def _branch(repo_slug: str, issue_number: int = 1) -> str:
    return _naming._branch_name(_spec(repo_slug), issue_number)


def _migration_spec() -> _config_models.RepoSpec:
    return _config_models.RepoSpec(
        slug=MIGRATION_REPO_SLUG,
        target_root=MIGRATION_TARGET_ROOT,
        base_branch=BASE_BRANCH,
    )


def _state(state_data=None) -> PinnedState:
    return PinnedState(comment_id=None, data=dict(state_data or {}))
