# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing resume behavior."""

from __future__ import annotations

import contextlib
import unittest

from tests.workflow.stages.fixing import fixing_test_support as support

IssueScenario = support.IssueScenario

ALICE = support.ALICE
AWAITING_HUMAN = support.AWAITING_HUMAN
LATE_APPROVED_SHA = "late_approved_sha"
LATE_APPROVED_LEASE = "late_approved_lease"
PR_HEAD_SHA = support.PR_HEAD_SHA
PARK_MEASUREMENT_FAILED = "late_measurement_failed"
MEASURED_CANDIDATE_SHA = support.fixtures.MEASURED_CANDIDATE_SHA
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_SESSION = support.DEV_SESSION
DOCUMENTING = support.DOCUMENTING
FakeComment = support.FakeComment
FakeUser = support.FakeUser
HISTORICAL_COMMENT_ID = support.HISTORICAL_COMMENT_ID
HUMAN_REPLY_ID = support.HUMAN_REPLY_ID
ISSUE = support.ISSUE
LAST_ACTION_COMMENT_ID = support.LAST_ACTION_COMMENT_ID
PARKED_COMMENT_WATERMARK = support.PARKED_COMMENT_WATERMARK
PARK_AGENT_TIMEOUT = support.PARK_AGENT_TIMEOUT
PARK_PUSH_FAILED = support.PARK_PUSH_FAILED
PARK_REASON = support.PARK_REASON
PENDING_FIX_AT = support.PENDING_FIX_AT
PENDING_FIX_ISSUE_MAX_ID = support.PENDING_FIX_ISSUE_MAX_ID
PRE_DEV_FIX_SHA = support.PRE_DEV_FIX_SHA
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PUSHED_MESSAGE = support.PUSHED_MESSAGE
PUSH_BRANCH = support.PUSH_BRANCH
PUSH_RETRIED_DETAIL = support.PUSH_RETRIED_DETAIL
REVIEW_ROUND = support.REVIEW_ROUND
RUN_AGENT = support.RUN_AGENT
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
TEMP_ROOT = support.TEMP_ROOT
TIMEOUT_EMPTY_DETAIL = support.TIMEOUT_EMPTY_DETAIL
TIMEOUT_PUSHED_DETAIL = support.TIMEOUT_PUSHED_DETAIL
TRANSIENT_PARK_WATERMARK = support.TRANSIENT_PARK_WATERMARK
UNCHANGED_SHA = support.UNCHANGED_SHA
VALIDATING = support.VALIDATING
WORKTREE_PATH = support.WORKTREE_PATH
WRITE_FAILED = "pinned write rejected"
WRITE_PINNED_STATE = "write_pinned_state"
_FixingFixtureMixin = support._FixingFixtureMixin
_RecoveryFollowupAssertions = support._RecoveryFollowupAssertions
_agent = support._agent
config = support.config
datetime = support.datetime
patch = support.patch
timedelta = support.timedelta
timezone = support.timezone
_worktree_paths = support.worktree_paths


class FixingAwaitingHumanResumeTest(unittest.TestCase, _FixingFixtureMixin):
    def test_no_new_feedback_is_noop(self) -> None:
        # After a prior failed tick parked the issue and bumped the
        # watermark past the original triggering comment, a poll with no
        # fresh human reply must be a no-op -- no agent spawn, no comment
        # post, no label change.
        pr = self._open_pr()
        gh, issue = self._seed(
            pr=pr,
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: PARK_AGENT_TIMEOUT,
                PR_LAST_COMMENT_ID: PARKED_COMMENT_WATERMARK,
            },
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                gh,
                issue,
                run_agent=_agent(),
            )

        mocks[RUN_AGENT].assert_not_called()
        self.assertEqual(gh.posted_comments, [])
        self.assertEqual(gh.label_history, [])

    def test_fresh_reply_resumes_dev(self) -> None:
        # The human typed a reply after the park. The fresh comment is
        # past the bumped watermark and past the debounce window, so the
        # handler clears the park flags and resumes the dev with the
        # new context.
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        reply = FakeComment(
            id=HUMAN_REPLY_ID,
            body="actually try X instead",
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=pr,
                issue_comments=[reply],
                extra_state={
                    AWAITING_HUMAN: True,
                    PARK_REASON: PARK_AGENT_TIMEOUT,
                    PR_LAST_COMMENT_ID: PARKED_COMMENT_WATERMARK,
                },
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            mocks = self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        mocks[RUN_AGENT].assert_called_once()
        self._pinned_data = scenario.github.pinned_data(ISSUE)
        # Park flags cleared (either by _resume_dev_with_text or after
        # the successful push). After a successful push we end up in
        # validating directly so the reviewer re-evaluates the new
        # head next tick.
        self.assertFalse(self._pinned_data.get(AWAITING_HUMAN))
        self.assertIsNone(self._pinned_data.get(PARK_REASON))
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)
        self.assertNotIn((ISSUE, DOCUMENTING), scenario.github.label_history)

    def test_validating_fix_bumps_instead_of_resets(self) -> None:
        # A parked CHANGES_REQUESTED dev fix (label flipped to `fixing`
        # by `_handle_validating`) is finished off via a human reply.
        # The pushed fix must BUMP `review_round`, not reset it: we are
        # still inside the same review cycle (the previous reviewer
        # round was CHANGES_REQUESTED, not APPROVED) and resetting would
        # silently restart MAX_REVIEW_ROUNDS accounting.
        # `pending_fix_at` is the discriminator: in_review->fixing sets
        # it (and resets the round on push); validating->fixing does NOT
        # set it (and bumps the round on push).
        long_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        reply = FakeComment(
            id=HUMAN_REPLY_ID,
            body="here's a clarification: use option B",
            user=FakeUser(ALICE),
            created_at=long_ago,
        )
        pr = self._open_pr()
        scenario = IssueScenario(
            *self._seed(
                pr=pr,
                issue_comments=[reply],
                extra_state={
                    AWAITING_HUMAN: True,
                    PARK_REASON: PARK_AGENT_TIMEOUT,
                    PR_LAST_COMMENT_ID: PARKED_COMMENT_WATERMARK,
                    # validating->fixing route did NOT set pending_fix_at;
                    # only the in_review route sets it. Override the seed's
                    # default to model the validating-route shape.
                    PENDING_FIX_AT: None,
                    PENDING_FIX_ISSUE_MAX_ID: None,
                    REVIEW_ROUND: 2,
                },
            )
        )

        with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS):
            self._run_fixing(
                scenario.github,
                scenario.issue,
                run_agent=_agent(
                    session_id=DEV_SESSION,
                    last_message=PUSHED_MESSAGE,
                ),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        pinned_data = scenario.github.pinned_data(ISSUE)
        # `review_round` bumped from 2 to 3 -- the review cycle continues
        # under MAX_REVIEW_ROUNDS rather than starting over at 0.
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 3)
        # Flipped back to validating so the reviewer re-evaluates next tick.
        self.assertIn((ISSUE, VALIDATING), scenario.github.label_history)


class _WriteFailingAfter:
    """A pinned write that lets the first `landed` writes through, then dies.

    The durable clear a landed push takes is a write of its own, and it lands
    BEFORE the follow-up this test is about. So the crash is modelled where it
    can actually happen: past the push and past the comment, on the write that
    would have cleared the park.
    """

    def __init__(self, landed: int, wrapped) -> None:
        self._landed = landed
        self._wrapped = wrapped
        self._writes = 0

    def __call__(self, *called, **options):
        self._writes += 1
        if self._writes > self._landed:
            raise RuntimeError(WRITE_FAILED)
        return self._wrapped(*called, **options)


@contextlib.contextmanager
def _debounced_in(worktree):
    """The quiet window and the checkout one parked-recovery tick runs in."""
    with patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS), patch.object(
        _worktree_paths, WORKTREE_PATH, return_value=worktree,
    ):
        yield


class FixingTransientParkRecoveryTest(
    unittest.TestCase,
    _FixingFixtureMixin,
    _RecoveryFollowupAssertions,
):
    def test_push_failure_park_recovers_on_success(
        self,
    ) -> None:
        # A `_handle_validating` CHANGES_REQUESTED dev fix can park
        # under `fixing` with `park_reason=PARK_PUSH_FAILED` after a
        # racing non-fast-forward push. Without the recovery branch
        # the issue would sit in `fixing` forever because
        # `_resume_developer_on_human_reply` only fires on a new human
        # comment AND the deferred --force-with-lease push that
        # eventually lands does not produce one. The recovery branch
        # silently retries the push and, on success, clears the park
        # flags, bumps `review_round`, and flips back to `validating`
        # so the reviewer re-evaluates the now-landed head.
        pr = self._open_pr()
        gh, issue = self._seed(
            pr=pr,
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: PARK_PUSH_FAILED,
                PR_LAST_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                # The push-failure park posted a HITL mention and stamped
                # this watermark at it; that stamp is what tells the
                # recovery a follow-up is owed.
                LAST_ACTION_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                # Validating route did not set pending_fix_at.
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                REVIEW_ROUND: 1,
                # What a `push_failed` park really carries: the size gate
                # approved this commit and the push it licensed is what
                # failed. The retry recognizes it rather than measuring it
                # again, so the only pinned write on this tick is the one the
                # follow-up rides out on.
                LATE_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
                LATE_APPROVED_LEASE: PR_HEAD_SHA,
            },
        )

        # `_worktree_path` is not mocked by the standard mixin (only
        # `_ensure_worktree` is). The recovery helper checks
        # `wt.exists()` before retrying the push, so route it to an
        # existing path. `/tmp` exists; the actual filesystem state
        # does not matter because `_push_branch` is mocked.
        with (
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
            patch.object(_worktree_paths, WORKTREE_PATH, return_value=TEMP_ROOT),
        ):
            mocks = self._run_fixing(
                gh,
                issue,
                run_agent=_agent(),
                push_branch=True,
            )

        # Recovery ran -- not a human-comment driven resume.
        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_called_once()
        # The mention that parked the issue is retired on the same tick.
        self._assert_recovery_followup(gh, PUSH_RETRIED_DETAIL)
        pinned_data = gh.pinned_data(ISSUE)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertIsNone(pinned_data.get(PARK_REASON))
        # Round bumped because a fix landed (the recovery helper bumps
        # on its `pushed` outcome).
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 2)
        # Flipped back to validating so the reviewer reruns next tick.
        self.assertIn((ISSUE, VALIDATING), gh.label_history)

    def test_failed_write_announces_only_once(
        self,
    ) -> None:
        # GitHub accepts the follow-up before the pinned write that clears the
        # park, so a write that dies leaves the comment posted and the park
        # standing. The next tick recovers again: it must recognize its own
        # follow-up on the thread rather than post a second one, and must not
        # rescan it as the fresh PR feedback that would resume the dev.
        gh, issue = self._seed(
            pr=self._open_pr(),
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: PARK_PUSH_FAILED,
                # Both watermarks sit BELOW the ids the fake hands out, so the
                # follow-up lands inside the next tick's rescan window and
                # above the park mention the recovery looks past for it.
                PR_LAST_COMMENT_ID: HISTORICAL_COMMENT_ID,
                LAST_ACTION_COMMENT_ID: HISTORICAL_COMMENT_ID,
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                REVIEW_ROUND: 1,
                LATE_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
                LATE_APPROVED_LEASE: PR_HEAD_SHA,
            },
        )

        with patch.object(_worktree_paths, WORKTREE_PATH, return_value=TEMP_ROOT):
            with patch.object(
                gh, WRITE_PINNED_STATE,
                _WriteFailingAfter(1, gh.write_pinned_state),
            ), self.assertRaises(RuntimeError):
                self._run_fixing(
                    gh, issue, run_agent=_agent(), push_branch=True,
                )
            # The comment really did land before the write blew up; without
            # this the retry below would be a first announcement.
            self.assertEqual(len(gh.posted_comments), 1)
            mocks = self._run_fixing(
                gh, issue, run_agent=_agent(), push_branch=True,
            )

        # The dev was NOT resumed on the orchestrator's own comment.
        mocks[RUN_AGENT].assert_not_called()
        self._assert_recovery_followup(gh, PUSH_RETRIED_DETAIL)
        pinned_data = gh.pinned_data(ISSUE)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertIn((ISSUE, VALIDATING), gh.label_history)

    def test_push_failure_park_stays_on_failure(
        self,
    ) -> None:
        # The remote is still rejecting the push. The recovery branch
        # must leave the park in place (no flag clear, no relabel) and
        # NOT re-post the park comment -- the next tick retries.
        pr = self._open_pr()
        gh, issue = self._seed(
            pr=pr,
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: PARK_PUSH_FAILED,
                PR_LAST_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                REVIEW_ROUND: 1,
            },
        )

        with _debounced_in(TEMP_ROOT):
            mocks = self._run_fixing(
                gh,
                issue,
                run_agent=_agent(),
                push_branch=False,
            )

        mocks[RUN_AGENT].assert_not_called()
        pinned_data = gh.pinned_data(ISSUE)
        # Park flags unchanged.
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(PARK_REASON), PARK_PUSH_FAILED)
        # Still on `fixing` (no relabel emitted this tick).
        self.assertNotIn((ISSUE, VALIDATING), gh.label_history)
        # Did NOT re-post the park comment (would be repetitive churn).
        self.assertEqual(gh.posted_comments, [])

    def test_a_refused_retry_persists_its_park(self) -> None:
        # The size gate refused the reading this retry was about, so the
        # recovery is neither healed nor stuck: the drift reroute to
        # `resolving_conflict` is not this tick's to take, and the park the
        # gate left has to reach the pinned comment -- otherwise the durable
        # state still says `push_failed` at the old watermark and the same
        # retry fires next tick.
        pr = self._open_pr()
        gh, issue = self._seed(
            pr=pr,
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: PARK_PUSH_FAILED,
                PR_LAST_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                LAST_ACTION_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                REVIEW_ROUND: 1,
                LATE_APPROVED_SHA: MEASURED_CANDIDATE_SHA,
                LATE_APPROVED_LEASE: PR_HEAD_SHA,
            },
        )

        with _debounced_in(TEMP_ROOT):
            mocks = self._run_fixing(
                gh, issue, run_agent=_agent(),
                push_branch=True, tree_readable=False,
            )

        mocks[PUSH_BRANCH].assert_not_called()
        self.assertEqual(gh.label_history, [])
        pinned_data = gh.pinned_data(ISSUE)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(
            pinned_data.get(PARK_REASON), PARK_MEASUREMENT_FAILED,
        )

    def test_timeout_park_clears_without_commit(self) -> None:
        # An `agent_timeout` park with `pre_dev_fix_sha == head_sha` means
        # the timeout produced no new commit. The recovery branch clears
        # the park flags WITHOUT bumping the round (nothing landed) and
        # flips back to `validating` so the reviewer reruns. The dev
        # session is not respawned in fixing -- the next validating tick
        # re-runs the reviewer which decides whether the same
        # CHANGES_REQUESTED fix is still needed.
        pr = self._open_pr()
        gh, issue = self._seed(
            pr=pr,
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: PARK_AGENT_TIMEOUT,
                PR_LAST_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                LAST_ACTION_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                REVIEW_ROUND: 1,
                # before-SHA equals current HEAD -- timeout did not
                # commit. The mixin's `head_shas` controls `_head_sha`.
                PRE_DEV_FIX_SHA: UNCHANGED_SHA,
            },
        )

        with (
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
            patch.object(_worktree_paths, WORKTREE_PATH, return_value=TEMP_ROOT),
        ):
            mocks = self._run_fixing(
                gh,
                issue,
                run_agent=_agent(),
                head_shas=(UNCHANGED_SHA,),
            )

        mocks[RUN_AGENT].assert_not_called()
        self._assert_recovery_followup(gh, TIMEOUT_EMPTY_DETAIL)
        pinned_data = gh.pinned_data(ISSUE)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertIsNone(pinned_data.get(PARK_REASON))
        # No round bump -- the timeout produced no fix.
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 1)
        self.assertIn((ISSUE, VALIDATING), gh.label_history)
        # `pre_dev_fix_sha` watermark cleared by the recovery helper so
        # a future park does not re-use a stale value.
        self.assertIsNone(pinned_data.get(PRE_DEV_FIX_SHA))

    def test_timeout_park_pushes_dev_commit(
        self,
    ) -> None:
        # The dev committed before the timeout killed it; recovery
        # pushes the new SHA and bumps `review_round`. Mirrors the
        # validating-side `pushed` branch.
        pr = self._open_pr()
        gh, issue = self._seed(
            pr=pr,
            extra_state={
                AWAITING_HUMAN: True,
                PARK_REASON: PARK_AGENT_TIMEOUT,
                PR_LAST_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                LAST_ACTION_COMMENT_ID: TRANSIENT_PARK_WATERMARK,
                PENDING_FIX_AT: None,
                PENDING_FIX_ISSUE_MAX_ID: None,
                REVIEW_ROUND: 1,
                PRE_DEV_FIX_SHA: UNCHANGED_SHA,
            },
        )

        with (
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
            patch.object(_worktree_paths, WORKTREE_PATH, return_value=TEMP_ROOT),
        ):
            mocks = self._run_fixing(
                gh,
                issue,
                run_agent=_agent(),
                # HEAD moved past pre-agent SHA -- the dev had committed. It
                # is the commit the gate proves the checkout to, because the
                # recovery's own reading and that proof are one read of one
                # worktree.
                head_shas=(SHA_AFTER,),
                # Where that commit leaves the branch: one above the head the
                # pull request is standing on, which is the reading the
                # recovery places it by and the head its push is leased to.
                branch_ahead_behind=(1, 0),
                push_branch=True,
                dirty_files=(),
            )

        mocks[PUSH_BRANCH].assert_called_once()
        self._assert_recovery_followup(gh, TIMEOUT_PUSHED_DETAIL)
        pinned_data = gh.pinned_data(ISSUE)
        self.assertFalse(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(pinned_data.get(REVIEW_ROUND), 2)
        self.assertIn((ISSUE, VALIDATING), gh.label_history)
