# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing drift behavior."""

from __future__ import annotations

import unittest

from orchestrator.workflow.stages.fixing import handler as _fixing
from tests.workflow.stages.fixing import (
    fixing_drift_test_support as drift_support,
    fixing_routing_test_support as support,
    fixing_test_support as fixing_support,
)

BEHIND_BASE_ISSUE = support.BEHIND_BASE_ISSUE
DIRTY_WORKTREE_ISSUE = support.DIRTY_WORKTREE_ISSUE
DRIFT_PR_HEAD = support.DRIFT_PR_HEAD
FakeGitHubClient = support.FakeGitHubClient
IN_SYNC_ISSUE = support.IN_SYNC_ISSUE
KEY_AWAITING_HUMAN = support.KEY_AWAITING_HUMAN
LABEL_RESOLVING_CONFLICT = support.LABEL_RESOLVING_CONFLICT
PENDING_FIX_AT = support.PENDING_FIX_AT
QUESTION_PARK_ISSUE = support.QUESTION_PARK_ISSUE
REVIEW_TRANSIENT_ISSUE = support.REVIEW_TRANSIENT_ISSUE
SILENT_PARK_ISSUE = support.SILENT_PARK_ISSUE
UNPUSHED_REBASE_ISSUE = support.UNPUSHED_REBASE_ISSUE
MagicMock = support.MagicMock
Path = support.Path
seam_patch = support.seam_patch
_FixingWorktreeDriftFixtureMixin = (
    drift_support._FixingWorktreeDriftFixtureMixin
)
_TEST_SPEC = support._TEST_SPEC

AWAITING_HUMAN = fixing_support.AWAITING_HUMAN
DEBOUNCE_CONFIG = fixing_support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = fixing_support.DEBOUNCE_SECONDS
KEY_PARK_REASON = fixing_support.PARK_REASON
# The bookmark key, which `PENDING_FIX_AT` above is one recorded VALUE of.
KEY_PENDING_FIX_AT = fixing_support.PENDING_FIX_AT
PARK_AGENT_TIMEOUT = fixing_support.PARK_AGENT_TIMEOUT
PARKED_ISSUE = fixing_support.ISSUE
PENDING_FIX_ISSUE_MAX_ID = fixing_support.PENDING_FIX_ISSUE_MAX_ID
PRE_DEV_FIX_SHA = fixing_support.PRE_DEV_FIX_SHA
PR_LAST_COMMENT_ID = fixing_support.PR_LAST_COMMENT_ID
PUSH_BRANCH = fixing_support.PUSH_BRANCH
RUN_AGENT = fixing_support.RUN_AGENT
STRANDED_HEAD = fixing_support.SHA_SAME
TRANSIENT_PARK_WATERMARK = fixing_support.TRANSIENT_PARK_WATERMARK
WORKTREE_PATH = fixing_support.WORKTREE_PATH
_FixingFixtureMixin = fixing_support._FixingFixtureMixin
_agent = fixing_support._agent
config = fixing_support.config
patch = fixing_support.patch
worktree_paths = fixing_support.worktree_paths

# The base probe the reroute routes on, and the counter it seeds when it does.
GIT_COMMAND = "_git"
ON_BASE = 0
CONFLICT_ROUND = "conflict_round"

# A fetch that did not return, which is one of the readings that leaves a
# branch unplaced against its pull request.
REFUSED_FETCH = MagicMock(returncode=1, stderr="boom")


class FixingWorktreeDriftRoutingTest(
    _FixingWorktreeDriftFixtureMixin,
    unittest.TestCase,
):
    def test_stuck_push_failed_behind_base_routes(self) -> None:
        # Variant 1: stuck `push_failed` + worktree behind base ->
        # resolving_conflict rebases.
        gh = FakeGitHubClient()
        self._seed_parked_fixing(gh, BEHIND_BASE_ISSUE)
        with self._drift_patches(2):
            _fixing._handle_fixing(gh, _TEST_SPEC, gh.get_issue(BEHIND_BASE_ISSUE))
        self._assert_routed(gh, BEHIND_BASE_ISSUE)
        self.recover.assert_called_once()

    def test_stuck_push_failed_unpushed_rebase_routes(self) -> None:
        # Variant 2: stuck `push_failed` + worktree ON base but local HEAD
        # differs from the stale remote PR head -> resolving_conflict
        # recognises the already-rebased worktree and republishes it.
        gh = FakeGitHubClient()
        self._seed_parked_fixing(gh, UNPUSHED_REBASE_ISSUE)
        with self._drift_patches(0, local_head="079210cabc"):
            _fixing._handle_fixing(gh, _TEST_SPEC, gh.get_issue(UNPUSHED_REBASE_ISSUE))
        self._assert_routed(gh, UNPUSHED_REBASE_ISSUE)

    def test_stuck_push_failed_in_sync_stays_parked(self) -> None:
        # On base AND local HEAD == PR head: drift is not the underlying
        # blocker. The recovery already declared "stuck" -> bail silently
        # so the human can investigate, do not re-post any comment.
        gh = FakeGitHubClient()
        self._seed_parked_fixing(gh, IN_SYNC_ISSUE)
        with self._drift_patches(0, local_head=DRIFT_PR_HEAD):
            _fixing._handle_fixing(gh, _TEST_SPEC, gh.get_issue(IN_SYNC_ISSUE))

        self.assertNotIn((IN_SYNC_ISSUE, LABEL_RESOLVING_CONFLICT), gh.label_history)
        self.assertTrue(gh.pinned_data(IN_SYNC_ISSUE).get(KEY_AWAITING_HUMAN))
        self.post.assert_not_called()

    def test_stuck_push_failed_dirty_stays_parked(self) -> None:
        # A dirty worktree is a park an operator may be inspecting;
        # `resolving_conflict` would reset it to the remote, so leave it.
        gh = FakeGitHubClient()
        self._seed_parked_fixing(gh, DIRTY_WORKTREE_ISSUE)
        with self._drift_patches(5, dirty=("src/x.py",)):
            _fixing._handle_fixing(gh, _TEST_SPEC, gh.get_issue(DIRTY_WORKTREE_ISSUE))

        self.assertNotIn((DIRTY_WORKTREE_ISSUE, LABEL_RESOLVING_CONFLICT), gh.label_history)
        self.assertTrue(gh.pinned_data(DIRTY_WORKTREE_ISSUE).get(KEY_AWAITING_HUMAN))
        self.post.assert_not_called()

    def test_question_park_with_drift_stays_parked(self) -> None:
        # A `park_reason=None` `_on_question` shape could be a real agent
        # question or a "nothing to fix" remark; route neither by inspection.
        gh = FakeGitHubClient()
        self._seed_parked_fixing(gh, QUESTION_PARK_ISSUE, park_reason=None)
        with self._drift_patches(7):
            _fixing._handle_fixing(gh, _TEST_SPEC, gh.get_issue(QUESTION_PARK_ISSUE))

        self.assertNotIn((QUESTION_PARK_ISSUE, LABEL_RESOLVING_CONFLICT), gh.label_history)
        self.assertTrue(gh.pinned_data(QUESTION_PARK_ISSUE).get(KEY_AWAITING_HUMAN))
        self.post.assert_not_called()
        self.recover.assert_not_called()

    def test_review_transient_drift_stays_parked(self) -> None:
        # In_review-route transient parks (`pending_fix_at` set) are
        # deliberately NOT auto-recovered: the round and watermark
        # semantics differ from the validating route.
        gh = FakeGitHubClient()
        self._seed_parked_fixing(
            gh,
            REVIEW_TRANSIENT_ISSUE,
            pending_fix_at=PENDING_FIX_AT,
        )
        with self._drift_patches(4):
            _fixing._handle_fixing(gh, _TEST_SPEC, gh.get_issue(REVIEW_TRANSIENT_ISSUE))

        self.assertNotIn((REVIEW_TRANSIENT_ISSUE, LABEL_RESOLVING_CONFLICT), gh.label_history)
        self.assertTrue(gh.pinned_data(REVIEW_TRANSIENT_ISSUE).get(KEY_AWAITING_HUMAN))
        self.post.assert_not_called()
        self.recover.assert_not_called()

    def test_silent_park_with_drift_stays_parked(self) -> None:
        # `agent_silent` is not in `_VALIDATING_TRANSIENT_PARK_REASONS`
        # (the silent-crash counter is the recovery channel, not drift)
        # so even with `pending_fix_at` unset the issue must stay parked.
        gh = FakeGitHubClient()
        self._seed_parked_fixing(gh, SILENT_PARK_ISSUE, park_reason="agent_silent")
        with self._drift_patches(3):
            _fixing._handle_fixing(gh, _TEST_SPEC, gh.get_issue(SILENT_PARK_ISSUE))

        self.assertNotIn((SILENT_PARK_ISSUE, LABEL_RESOLVING_CONFLICT), gh.label_history)
        self.assertTrue(gh.pinned_data(SILENT_PARK_ISSUE).get(KEY_AWAITING_HUMAN))
        self.post.assert_not_called()
        self.recover.assert_not_called()


class UnplacedBranchDriftRefusalTest(
    _FixingWorktreeDriftFixtureMixin,
    unittest.TestCase,
    _FixingFixtureMixin,
):
    """What the drift reroute may never be handed: a branch nobody placed.

    The reroute is for a park whose transient condition keeps failing while the
    base moved under its worktree, and `resolving_conflict` behind it publishes
    what it reconciles. A park the branch READING withheld the clear from is the
    opposite claim -- the checkout may be carrying a commit no report describes
    -- so the recovery answers the two in different words and only the first
    reaches this road.
    """

    def test_an_unplaced_timeout_park_is_not_rerouted(self) -> None:
        # The timeout left the head where it found it, and the head it found is
        # a commit an earlier interrupted resume stranded: the pull request
        # stands somewhere else, so the base probe answers "on base" and the
        # local head differs from the PR head -- drift, as far as the reroute
        # can tell. The fetch behind the branch reading refused, so nothing
        # placed that checkout; rerouted anyway, the park comes down and
        # `resolving_conflict` publishes a head with no report debt staged for
        # it.
        gh, issue = self._seed(
            pr=self._open_pr(),
            extra_state={
                AWAITING_HUMAN: True,
                KEY_PARK_REASON: PARK_AGENT_TIMEOUT,
                PR_LAST_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                # The validating route, which is the one the silent recovery
                # answers a transient park on.
                KEY_PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                PRE_DEV_FIX_SHA: STRANDED_HEAD,
            },
        )

        with (
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
            patch.object(
                worktree_paths, WORKTREE_PATH, return_value=Path(self._wt_dir),
            ),
            seam_patch(GIT_COMMAND, self._git_behind(ON_BASE)),
        ):
            mocks = self._run_fixing(
                gh,
                issue,
                run_agent=_agent(),
                head_shas=(STRANDED_HEAD,),
                authed_fetch_result=REFUSED_FETCH,
            )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        pinned_data = gh.pinned_data(PARKED_ISSUE)
        # The park stands as the timeout filed it, with the anchor the tick
        # that can finally read the branch needs still recorded.
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(KEY_PARK_REASON), PARK_AGENT_TIMEOUT)
        self.assertEqual(pinned_data.get(PRE_DEV_FIX_SHA), STRANDED_HEAD)
        # No reroute: no label moved, no conflict counter seeded, and neither
        # the issue nor the pull request was told a thing.
        self.assertEqual(gh.label_history, [])
        self.assertIsNone(pinned_data.get(CONFLICT_ROUND))
        self.assertEqual(gh.posted_pr_comments, [])
        self.assertEqual(gh.posted_comments, [])
