# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and protocol values for fixing routing tests."""

from __future__ import annotations

import pathlib
import subprocess
from unittest import mock

from orchestrator.config import models as _config_models
from tests.git.base_sync.gate_reads_support import _gate_reads
from tests.support import fakes
from tests.workflow import fixtures, git_owners

Path = pathlib.Path
MagicMock = mock.MagicMock
patch = mock.patch
seam_patch = git_owners.seam_patch
FakeGitHubClient = fakes.FakeGitHubClient
FakePR = fakes.FakePR
FakePRRef = fakes.FakePRRef
make_issue = fakes.make_issue
_PatchedWorkflowMixin = fixtures._PatchedWorkflowMixin
_TEST_SPEC = fixtures._TEST_SPEC
_agent = fixtures._agent
_issue_branch = fixtures._issue_branch
BACKEND_CLAUDE = "claude"
KEY_AWAITING_HUMAN = "awaiting_human"
LABEL_DONE = "done"
LABEL_FIXING = "workflow:fixing"
LABEL_IMPLEMENTING = "workflow:implementing"
LABEL_IN_REVIEW = "in_review"
LABEL_REJECTED = "rejected"
LABEL_RESOLVING_CONFLICT = "workflow:resolving_conflict"
LABEL_VALIDATING = "workflow:validating"
STAGE_FIXING = "fixing"
STATE_CLOSED = "closed"
STATE_OPEN = "open"
DEV_SESSION = "dev-sess"
# A whole git object id: the size gate freezes the head its pull request
# stands on before a refresh may push, and reads a commit field at its exact
# length.
PR_HEAD_SHA = "cafe1234" * 5
PENDING_FIX_AT = "2026-05-23T00:00:00+00:00"
INITIAL_COMMENT_WATERMARK = 1999
ISSUE_FEEDBACK_ID = 2000
REVIEW_FEEDBACK_ID = 3000
SUMMARY_FEEDBACK_ID = 4000
DISPATCH_ISSUE = 701
MISSING_PR_ISSUE = 702
IDEMPOTENT_PARK_ISSUE = 703
CLOSED_WITHOUT_PR_ISSUE = 704
MERGED_ISSUE = 705
MERGED_PR = 801
UNMERGED_ISSUE = 706
UNMERGED_PR = 802
OPEN_POLLABLE_ISSUE = 710
CLOSED_POLLABLE_ISSUE = 711
AUTO_MERGE_ISSUE = 720
AUTO_MERGE_PR = 901
CONFLICT_FIXTURE_ISSUE = 7
CONFLICT_FIXTURE_PR = 42
DRIFT_PR_NUMBER_OFFSET = 900
DRIFT_FEEDBACK_WATERMARK = 5000
DRIFT_PR_HEAD = "prhead00cafe1234"
BEHIND_BASE_ISSUE = 30
UNPUSHED_REBASE_ISSUE = 34
IN_SYNC_ISSUE = 31
DIRTY_WORKTREE_ISSUE = 33
QUESTION_PARK_ISSUE = 35
REVIEW_TRANSIENT_ISSUE = 36
SILENT_PARK_ISSUE = 37


class _FixingConflictFixtureMixin:
    """A behind-base `fixing` worktree goes through the pre-tick base
    rebase. Both exits (clean rebase -> `validating`, conflicted rebase
    -> `resolving_conflict`) must PRESERVE the `pending_fix_*`
    bookmarks recorded by the in_review handoff and the in_review
    watermarks, so the eventual return from `validating` -> `in_review`
    re-discovers the unread feedback and routes it back to `fixing`.
    """

    def setUp(self) -> None:
        self.spec = _config_models.RepoSpec(
            slug="acme/widget",
            target_root=Path("/tmp/refresh-target-fixing"),
            base_branch="main",
        )
        self.wt = Path("/tmp/refresh-wt-fixing")
        self.gh = FakeGitHubClient()
        # The rebase this refresh would push is measured before it goes out,
        # and this fixture has no checkout on disk for the reading to be taken
        # in. These tests are about what the relabel preserves, so the gate
        # gets its ordinary answers.
        _gate_reads(self)

    def _git_result(self, *, returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=["git"],
            returncode=returncode,
            stdout=stdout,
            stderr="",
        )

    def _seed_fixing_with_pending_feedback(self) -> None:
        self.gh.add_issue(make_issue(CONFLICT_FIXTURE_ISSUE, label=LABEL_FIXING))
        pr = FakePR(
            number=CONFLICT_FIXTURE_PR,
            head_branch="orchestrator/acme__widget/issue-7",
            head=FakePRRef(sha=PR_HEAD_SHA),
            state=STATE_OPEN,
        )
        self.gh.add_pr(pr)
        self.gh.seed_state(
            CONFLICT_FIXTURE_ISSUE,
            pr_number=CONFLICT_FIXTURE_PR,
            branch="orchestrator/acme__widget/issue-7",
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            pr_last_comment_id=INITIAL_COMMENT_WATERMARK,
            pr_last_review_comment_id=0,
            pr_last_review_summary_id=0,
            pending_fix_at=PENDING_FIX_AT,
            pending_fix_issue_max_id=ISSUE_FEEDBACK_ID,
            pending_fix_review_max_id=REVIEW_FEEDBACK_ID,
            pending_fix_review_summary_max_id=SUMMARY_FEEDBACK_ID,
        )

    def _assert_pending_feedback_intact(self) -> None:
        # Pending-fix bookmarks survived the relabel so the eventual
        # in_review re-entry can correlate the triggering ids. The
        # in_review watermark is unchanged so the rescan after
        # `validating` -> `in_review` surfaces the original triggering
        # comment as fresh feedback again.
        pinned_data = self.gh.pinned_data(CONFLICT_FIXTURE_ISSUE)
        self.assertEqual(pinned_data.get("pending_fix_at"), PENDING_FIX_AT)
        self.assertEqual(pinned_data.get("pending_fix_issue_max_id"), ISSUE_FEEDBACK_ID)
        self.assertEqual(pinned_data.get("pending_fix_review_max_id"), REVIEW_FEEDBACK_ID)
        self.assertEqual(pinned_data.get("pending_fix_review_summary_max_id"), SUMMARY_FEEDBACK_ID)
        self.assertEqual(pinned_data.get("pr_last_comment_id"), INITIAL_COMMENT_WATERMARK)
        self.assertEqual(pinned_data.get("pr_last_review_comment_id"), 0)
        self.assertEqual(pinned_data.get("pr_last_review_summary_id"), 0)
