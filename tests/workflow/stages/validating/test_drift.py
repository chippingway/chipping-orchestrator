# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from orchestrator import config
from orchestrator.git.measurement.models import FrozenCommit
from orchestrator.git.worktrees import paths as _worktree_paths
from orchestrator.workflow.engine import content_hash as _content_hash
from tests.support.fakes import (
    DEFAULT_PR_HEAD_SHA,
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakeUser,
    make_issue,
)
from tests.support.publication import LandingPush
from tests.workflow import fixtures as _fixtures
from tests.workflow.fixtures import (
    LABEL_DECOMPOSING,
    MEASURED_CANDIDATE_SHA,
    REVIEW_APPROVED_MESSAGE,
    _agent,
    _open_pr_for,
    _PatchedWorkflowMixin,
)

LATE_APPROVED_SHA = "late_approved_sha"
# The head the pull request stood on when the approval was written: an
# approval with no lease is one nothing can pin a push against, which the
# gate refuses rather than falling back to whatever it can read now.
PR_HEAD_SHA = "deadbeef" * 5
COUNT_ADDED_LINES = "_count_added_lines"
RECOVERED_PREFIX = _fixtures.RECOVERED_PREFIX
PARK_MEASUREMENT_FAILED = "late_measurement_failed"
# The head a timed-out run left the checkout on, past `pre_dev_fix_sha`. It IS
# the commit the size gate proves that checkout to, because the two are one
# read of one worktree: the recovery names the commit it is publishing as that
# run's, and the gate refuses a checkout standing anywhere else.
TIMEOUT_HEAD = MEASURED_CANDIDATE_SHA
# What the checkout stands on once something has moved it out from under the
# head this recovery read.
MOVED_HEAD = "m0vedc0m" * 5
MAX_ADDED_LINES = "MAX_ADDED_LINES"
DECOMPOSE = "DECOMPOSE"
CEILING = 5
PAST_THE_CEILING = 6
VALIDATING_ISSUE = 170
VALIDATING_PR = 99
VALIDATING_BRANCH = "orchestrator/chippingway__orchestrator/issue-170"
BODY_DRIFT_ISSUE = 70
BODY_DRIFT_PR = 700
REVIEWER_RETRY_COMMENT_ID = 4000
PARK_MENTION_ID = 500
WRITE_PINNED_STATE = "write_pinned_state"
WRITE_FAILED = "pinned write rejected"
# The baseline a `_parked_issue` thread already hashes to. Seeding it is what
# keeps the drift check from writing one itself, ahead of the recovery write a
# test is simulating the failure of.
UNCHANGED_CONTENT_HASH = _content_hash._compute_user_content_hash(
    make_issue(VALIDATING_ISSUE), set(),
)
REVIEWER_DRIFT_PR = 10000
ACTION_WATERMARK = 10_000
HUMAN_REPLY_ID = 10_500
DEV_SESSION = "dev-sess"
HUMAN_LOGIN = "alice"
# The head a run starts on, which is the head its pull request is standing
# on: the branch is in sync with its publication when a round opens.
PRE_FIX_SHA = DEFAULT_PR_HEAD_SHA
# The pinned watermark a dev timeout park leaves the head it was taken at on.
PRE_DEV_FIX_SHA = "pre_dev_fix_sha"
REBASE_REQUEST = "please rebase first"
WORKTREE_ROOT = "/tmp"
WORKTREE_PATH = "_worktree_path"
RUN_AGENT = "run_agent"
PUSH_BRANCH = "_push_branch"
AWAITING_HUMAN = "awaiting_human"
PARK_REASON = "park_reason"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
REVIEW_ROUND = "review_round"

AGENT_TIMEOUT = _fixtures.AGENT_TIMEOUT_PARK
PUSH_FAILED = _fixtures.PUSH_FAILED_PARK
PUSH_RETRIED_DETAIL = _fixtures.PUSH_RETRIED_DETAIL
REVIEWER_FAILED = _fixtures.REVIEWER_FAILED_PARK
REVIEWER_RESPAWN_DETAIL = _fixtures.REVIEWER_RESPAWN_DETAIL
REVIEWER_TIMEOUT = _fixtures.REVIEWER_TIMEOUT_PARK
TIMEOUT_EMPTY_DETAIL = _fixtures.TIMEOUT_EMPTY_DETAIL
TIMEOUT_PUSHED_DETAIL = _fixtures.TIMEOUT_PUSHED_DETAIL


class _TransientParkFixtureMixin(
    _PatchedWorkflowMixin,
    _fixtures._RecoveryFollowupAssertions,
):
    def _pinned(self, github) -> dict:
        """What this issue's pinned comment says once the tick has finished."""
        return github.pinned_data(VALIDATING_ISSUE)

    def _pushes(self, mocks):
        """The seam a recovery's size question is decided at."""
        return mocks[PUSH_BRANCH]

    def _parked_issue(self, *, park_reason: str, **extra_state):
        gh = FakeGitHubClient()
        # `last_action_comment_id` is well above any existing comment id, so
        # `comments_after` returns []. This mirrors the post-park watermark
        # set by `_park_awaiting_human` (it bumps to the latest comment id).
        issue = make_issue(VALIDATING_ISSUE, label="workflow:validating")
        gh.add_issue(issue)
        seed = {
            "pr_number": VALIDATING_PR,
            "branch": VALIDATING_BRANCH,
            "dev_agent": "claude",
            "dev_session_id": DEV_SESSION,
            "review_round": 1,
            "awaiting_human": True,
            "park_reason": park_reason,
            "last_action_comment_id": ACTION_WATERMARK,
        }
        seed.update(extra_state)
        gh.seed_state(VALIDATING_ISSUE, **seed)
        _open_pr_for(
            gh, issue_number=VALIDATING_ISSUE, pr_number=VALIDATING_PR,
        )
        return gh, issue

    def _run_parked_validating(self, github, issue, **kwargs):
        with patch.object(
            _worktree_paths,
            WORKTREE_PATH,
            return_value=Path(WORKTREE_ROOT),
        ):
            return self._run_validating(github, issue, **kwargs)

    def _assert_stays_validating(self, github) -> None:
        self.assertEqual(github.label_history, [])
        self.assertNotIn(
            (VALIDATING_ISSUE, "workflow:documenting"),
            github.label_history,
        )
        self.assertNotIn(
            (VALIDATING_ISSUE, "in_review"),
            github.label_history,
        )


class ValidatingTransientParkRecoveryTest(
    unittest.TestCase,
    _TransientParkFixtureMixin,
):
    """Recover safe push failures while retaining ambiguous parks."""

    def test_push_failure_recovers_on_success(self) -> None:
        gh, issue = self._parked_issue(park_reason=PUSH_FAILED)

        # Force the worktree-existence check to pass; "/tmp" always exists
        # on Linux. The recovery only retries the push when the worktree
        # is still on disk (otherwise the dev's local commits are gone and
        # only a human relabel can unstick the issue).
        mocks = self._run_parked_validating(
            gh,
            issue,
            run_agent=_agent(),
            push_branch=True,
        )

        # Recovery must NOT spawn the agent -- it is a silent retry that
        # speaks only once it has worked, and only on the issue thread the
        # park's mention is sitting on.
        mocks[RUN_AGENT].assert_not_called()
        self._assert_recovery_followup(gh, PUSH_RETRIED_DETAIL)
        self.assertEqual(gh.posted_pr_comments, [])
        # Push retried and succeeded: park flags cleared, review_round
        # incremented so the next reviewer run starts a fresh round.
        mocks[PUSH_BRANCH].assert_called_once()
        state = self._pinned(gh)
        self.assertFalse(state.get(AWAITING_HUMAN))
        self.assertIsNone(state.get(PARK_REASON))
        self.assertEqual(state.get(REVIEW_ROUND), 2)
        # The push that landed paid the debt the approval recorded; left
        # standing it would freeze this branch out of the base refresh with
        # the recovery that owed the drop already finished.
        self.assertIsNone(state.get(LATE_APPROVED_SHA))
        # Stays on `validating` (no documenting hop) so the reviewer
        # re-evaluates the recovered head on the next tick.
        self._assert_stays_validating(gh)

    def test_failed_write_announces_only_once(self) -> None:
        # GitHub accepts the follow-up before the pinned write that clears
        # the park, so a write that dies leaves the comment posted and the
        # park standing. The next tick recovers again and must neither read
        # its own follow-up as the human reply the park is waiting for nor
        # post a second one.
        gh, issue = self._parked_issue(
            park_reason=PUSH_FAILED,
            # Below the ids the fake hands out, so the follow-up lands ABOVE
            # the park's mention -- where the next tick looks for it.
            last_action_comment_id=PARK_MENTION_ID,
            user_content_hash=UNCHANGED_CONTENT_HASH,
            # What a `push_failed` park really carries: the size gate approved
            # this commit and the push it licensed is what failed. The retry
            # recognizes it rather than measuring it again, so the only pinned
            # write on this tick is the one the follow-up rides out on.
            late_approved_sha=MEASURED_CANDIDATE_SHA,
            late_approved_lease=PR_HEAD_SHA,
        )

        with patch.object(
            gh, WRITE_PINNED_STATE,
            _fixtures._WriteFailingAfter(1, gh.write_pinned_state),
        ), self.assertRaises(RuntimeError):
            self._run_parked_validating(
                gh, issue, run_agent=_agent(),
                # The push lands, so the pull request stands on what it
                # published: the retry below reads a publication that is
                # over rather than one to make again.
                push_branch=LandingPush(gh, VALIDATING_PR),
            )
        # The comment really did land before the write blew up; without this
        # the retry below would be exercising a first announcement.
        self.assertEqual(len(gh.posted_comments), 1)

        mocks = self._run_parked_validating(
            gh, issue, run_agent=_agent(),
            push_branch=LandingPush(gh, VALIDATING_PR),
        )

        # The dev was NOT resumed on the orchestrator's own comment.
        mocks[RUN_AGENT].assert_not_called()
        self._assert_recovery_followup(gh, PUSH_RETRIED_DETAIL)
        state = self._pinned(gh)
        self.assertFalse(state.get(AWAITING_HUMAN))
        self.assertIsNone(state.get(PARK_REASON))
        # The round rode the write the receipt did, so the discarded one took
        # nothing with it -- and the retry reads a settled publication and
        # counts nothing more. One fix landed; one round advanced.
        self.assertEqual(state.get(REVIEW_ROUND), 2)

    def test_a_refused_retry_persists_what_it_parked(self) -> None:
        # The gate's refusal posts a notice and moves the watermark in
        # memory, and no caller of a held recovery writes state: they clear
        # nothing and announce nothing, which is right. Without the write the
        # durable comment would still say `push_failed` at the old watermark,
        # so the same retry fires next tick and the human is asked again.
        refused = self._parked_issue(
            park_reason=PUSH_FAILED,
            last_action_comment_id=PARK_MENTION_ID,
            user_content_hash=UNCHANGED_CONTENT_HASH,
            late_approved_sha=MEASURED_CANDIDATE_SHA,
            late_approved_lease=PR_HEAD_SHA,
        )
        gh = refused[0]

        mocks = self._run_parked_validating(
            *refused, run_agent=_agent(), push_branch=True,
            tree_readable=False,
        )

        mocks[PUSH_BRANCH].assert_not_called()
        state = self._pinned(gh)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PARK_MEASUREMENT_FAILED)
        self.assertGreater(
            state.get(LAST_ACTION_COMMENT_ID), PARK_MENTION_ID,
        )
        self.assertFalse(
            any(RECOVERED_PREFIX in body for _, body in gh.posted_comments),
        )

    def test_repeat_push_failure_stays_parked(self) -> None:
        # Recovery must not re-post the park message when the push still
        # fails -- otherwise every poll would spam the issue.
        gh, issue = self._parked_issue(park_reason=PUSH_FAILED)

        mocks = self._run_parked_validating(
            gh,
            issue,
            run_agent=_agent(),
            push_branch=False,
        )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_called_once()
        # No new park comment posted on this tick.
        self.assertEqual(gh.posted_comments, [])
        # Park flags preserved for the next recovery attempt.
        state = self._pinned(gh)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PUSH_FAILED)
        # review_round NOT bumped while still stuck.
        self.assertEqual(state.get(REVIEW_ROUND), 1)

    def test_missing_worktree_stays_parked(self) -> None:
        # If the worktree was reaped between the original park and the
        # recovery tick, the dev's local commits are gone and there is
        # nothing to push. Stay parked so a human can intervene.
        gh, issue = self._parked_issue(park_reason=PUSH_FAILED)

        # Path that will not exist on the test host.
        gone = Path("/tmp/orchestrator-test-recovery-no-such-worktree-xyz")
        with patch.object(_worktree_paths, WORKTREE_PATH, return_value=gone):
            mocks = self._run_validating(
                gh,
                issue,
                run_agent=_agent(),
                push_branch=True,
            )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        state = self._pinned(gh)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(PARK_REASON), PUSH_FAILED)

    def test_nontransient_no_comments_stays_parked(self) -> None:
        # A park whose reason is not in the validating transient set (e.g.
        # a question or dirty-tree park) must NOT auto-recover. The
        # _resume_developer_on_human_reply path (no new comments) returns
        # without doing anything; recovery is the only other path and it
        # bails on park_reason.
        gh, issue = self._parked_issue(park_reason=None)

        mocks = self._run_parked_validating(
            gh,
            issue,
            run_agent=_agent(),
            push_branch=True,
        )

        mocks[RUN_AGENT].assert_not_called()
        mocks[PUSH_BRANCH].assert_not_called()
        state = self._pinned(gh)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(REVIEW_ROUND), 1)


class ValidatingReviewerParkRecoveryTest(
    unittest.TestCase,
    _TransientParkFixtureMixin,
):
    """Recover reviewer-side transient parks or rerun on a human reply."""

    def test_reviewer_timeout_park_self_recovers(self) -> None:
        # A previous tick parked because the reviewer agent timed out.
        # The next tick must clear the flags so the reviewer re-runs --
        # nothing in `_resume_developer_on_human_reply` would unstick this
        # otherwise (no comment ever lands from a timeout).
        reviewer_gh, issue = self._parked_issue(park_reason=REVIEWER_TIMEOUT)

        reviewer_mocks = self._run_parked_validating(
            reviewer_gh,
            issue,
            run_agent=_agent(),
            push_branch=True,
        )

        # The agent is NOT re-spawned here (next tick does that, on the
        # cleared awaiting_human flag) and no push is attempted (no fix
        # landed); the only visible trace is the follow-up retiring the
        # timeout mention.
        reviewer_mocks[RUN_AGENT].assert_not_called()
        reviewer_mocks[PUSH_BRANCH].assert_not_called()
        self._assert_recovery_followup(reviewer_gh, REVIEWER_RESPAWN_DETAIL)
        reviewer_state = reviewer_gh.pinned_data(VALIDATING_ISSUE)
        self.assertFalse(reviewer_state.get(AWAITING_HUMAN))
        self.assertIsNone(reviewer_state.get(PARK_REASON))
        # review_round MUST NOT advance: a timeout produced no fix, so
        # bumping would burn through MAX_REVIEW_ROUNDS without progress.
        self.assertEqual(reviewer_state.get(REVIEW_ROUND), 1)

    def test_reviewer_failed_park_self_recovers(self) -> None:
        # The reviewer crashed with empty stdout + non-zero exit on the
        # previous tick. Recovery must clear the flags so the next tick
        # re-spawns the reviewer with a fresh budget -- without this,
        # the issue waits for a human comment that the codex / network
        # blip cannot produce.
        reviewer_gh, issue = self._parked_issue(park_reason=REVIEWER_FAILED)

        reviewer_mocks = self._run_parked_validating(
            reviewer_gh,
            issue,
            run_agent=_agent(),
            push_branch=True,
        )

        reviewer_mocks[RUN_AGENT].assert_not_called()
        reviewer_mocks[PUSH_BRANCH].assert_not_called()
        self._assert_recovery_followup(reviewer_gh, REVIEWER_RESPAWN_DETAIL)
        reviewer_state = reviewer_gh.pinned_data(VALIDATING_ISSUE)
        self.assertFalse(reviewer_state.get(AWAITING_HUMAN))
        self.assertIsNone(reviewer_state.get(PARK_REASON))
        # No fix landed; a reviewer crash produces no commit, so the
        # round must stay flat (mirrors the reviewer_timeout branch).
        self.assertEqual(reviewer_state.get(REVIEW_ROUND), 1)

    def test_error_comment_reruns_reviewer(self) -> None:
        # A human "Retry" / "Continue" nudge after a reviewer-side park
        # must wake the REVIEWER, not the dev. Pre-fix this branch fed
        # the comment to `_resume_developer_on_human_reply`, which woke
        # the dev session; the dev correctly answered "nothing to do,
        # the reviewer should re-run" and the issue wedged.
        reviewer_gh, issue = self._parked_issue(park_reason=REVIEWER_FAILED)
        issue.comments.append(
            FakeComment(
                id=HUMAN_REPLY_ID,
                body="retry please",
                user=FakeUser(HUMAN_LOGIN),
            )
        )

        reviewer_mocks = self._run_parked_validating(
            reviewer_gh,
            issue,
            run_agent=_agent(
                session_id="rev-sess",
                last_message=REVIEW_APPROVED_MESSAGE,
            ),
            head_shas=[PRE_FIX_SHA],
        )

        # Exactly one agent ran: the reviewer (not the dev). The agent
        # call must use the reviewer config, not the dev session resume.
        self.assertEqual(reviewer_mocks[RUN_AGENT].call_count, 1)
        call = reviewer_mocks[RUN_AGENT].call_args
        self.assertEqual(call.args[0], config.REVIEW_AGENT)
        self.assertNotIn("resume_session_id", call.kwargs)
        # Park flags cleared and the human's comment is consumed so it
        # cannot replay on the next tick.
        reviewer_state = reviewer_gh.pinned_data(VALIDATING_ISSUE)
        self.assertFalse(reviewer_state.get(AWAITING_HUMAN))
        self.assertIsNone(reviewer_state.get(PARK_REASON))
        self.assertEqual(reviewer_state.get("last_action_comment_id"), HUMAN_REPLY_ID)

    def test_timeout_comment_reruns_reviewer(self) -> None:
        # Same routing rule for the reviewer_timeout park reason: a
        # human nudge must reach the reviewer, not the dev session.
        reviewer_gh, issue = self._parked_issue(park_reason=REVIEWER_TIMEOUT)
        issue.comments.append(
            FakeComment(
                id=HUMAN_REPLY_ID,
                body="retry please",
                user=FakeUser(HUMAN_LOGIN),
            )
        )

        reviewer_mocks = self._run_parked_validating(
            reviewer_gh,
            issue,
            run_agent=_agent(
                session_id="rev-sess",
                last_message=REVIEW_APPROVED_MESSAGE,
            ),
            head_shas=[PRE_FIX_SHA],
        )

        self.assertEqual(reviewer_mocks[RUN_AGENT].call_count, 1)
        call = reviewer_mocks[RUN_AGENT].call_args
        self.assertEqual(call.args[0], config.REVIEW_AGENT)
        self.assertNotIn("resume_session_id", call.kwargs)
        reviewer_state = reviewer_gh.pinned_data(VALIDATING_ISSUE)
        self.assertFalse(reviewer_state.get(AWAITING_HUMAN))
        self.assertIsNone(reviewer_state.get(PARK_REASON))


class ValidatingDevParkRecoveryTest(
    unittest.TestCase,
    _TransientParkFixtureMixin,
):
    """Recover dev timeouts from the worktree and push developer_state."""

    def test_dev_timeout_comment_routes_to_dev(self) -> None:
        # Regression: dev-side park reasons (agent_timeout) must keep
        # routing to the dev session on a human comment. Only
        # reviewer-side reasons get the new fall-through.
        developer_gh, issue = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )
        issue.comments.append(
            FakeComment(
                id=HUMAN_REPLY_ID,
                body=REBASE_REQUEST,
                user=FakeUser(HUMAN_LOGIN),
            )
        )

        developer_mocks = self._run_parked_validating(
            developer_gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="rebased",
            ),
            push_branch=True,
            head_shas=[PRE_FIX_SHA, MEASURED_CANDIDATE_SHA],
        )

        # The dev was resumed with the human's feedback (NOT the reviewer).
        developer_mocks[RUN_AGENT].assert_called_once()
        call = developer_mocks[RUN_AGENT].call_args
        self.assertEqual(call.kwargs.get("resume_session_id"), DEV_SESSION)
        followup = call.args[1]
        self.assertIn(REBASE_REQUEST, followup)

    def test_clean_timeout_recovers_without_a_push(self) -> None:
        # Common timeout shape: the dev burned the budget without
        # producing a new commit. Recovery clears flags and does not
        # bump the round (no fix landed); next tick re-runs the reviewer.
        # `head_shas[0] == pre_dev_fix_sha` models "agent did nothing"
        # (worktree HEAD unchanged from the pre-agent watermark).
        developer_gh, issue = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )

        developer_mocks = self._run_parked_validating(
            developer_gh,
            issue,
            run_agent=_agent(),
            dirty_files=(),
            push_branch=True,
            head_shas=(PRE_FIX_SHA,),
        )

        developer_mocks[RUN_AGENT].assert_not_called()
        developer_mocks[PUSH_BRANCH].assert_not_called()
        self._assert_recovery_followup(developer_gh, TIMEOUT_EMPTY_DETAIL)
        developer_state = self._pinned(developer_gh)
        self.assertFalse(developer_state.get(AWAITING_HUMAN))
        self.assertIsNone(developer_state.get(PARK_REASON))
        self.assertEqual(developer_state.get(REVIEW_ROUND), 1)
        # Watermark cleared so a future timeout cycle starts fresh.
        self.assertIsNone(developer_state.get(PRE_DEV_FIX_SHA))

    def test_timeout_with_only_pr_commits_recovers(self) -> None:
        # Regression: a normal PR worktree is always ahead of
        # `origin/<base>` after the first fix lands. `_has_new_commits()`
        # would say "yes" even when this run produced nothing, so naive
        # recovery would call `_push_branch()` (force-with-lease over
        # the live remote head with a stale local HEAD) and bump the
        # round on every tick. The pre/now SHA comparison must guard
        # against that.
        developer_gh, issue = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )

        developer_mocks = self._run_parked_validating(
            developer_gh,
            issue,
            run_agent=_agent(),
            # Mock `_has_new_commits` to True to model an established
            # PR worktree (commits ahead of origin/main); the
            # recovery must not consult this signal.
            has_new_commits=True,
            dirty_files=(),
            push_branch=True,
            head_shas=(PRE_FIX_SHA,),  # HEAD == pre_dev_fix_sha
        )

        developer_mocks[RUN_AGENT].assert_not_called()
        developer_mocks[PUSH_BRANCH].assert_not_called()
        self._assert_recovery_followup(developer_gh, TIMEOUT_EMPTY_DETAIL)
        developer_state = self._pinned(developer_gh)
        self.assertFalse(developer_state.get(AWAITING_HUMAN))
        self.assertIsNone(developer_state.get(PARK_REASON))
        # MUST NOT bump: nothing landed.
        self.assertEqual(developer_state.get(REVIEW_ROUND), 1)

    def test_timeout_pushes_commits_and_bumps(self) -> None:
        # The dev committed the fix locally but the timeout killed it
        # before the push. Recovery must finish that push -- otherwise
        # the next tick's reviewer would inspect a SHA that is not on
        # the PR. `head_shas[0] != pre_dev_fix_sha` models "agent
        # produced a new commit before timing out."
        developer_gh, issue = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )

        developer_mocks = self._run_parked_validating(
            developer_gh,
            issue,
            run_agent=_agent(),
            dirty_files=(),
            push_branch=True,
            head_shas=(TIMEOUT_HEAD,),  # HEAD moved past pre-agent SHA
        )

        developer_mocks[RUN_AGENT].assert_not_called()
        developer_mocks[PUSH_BRANCH].assert_called_once()
        self._assert_recovery_followup(developer_gh, TIMEOUT_PUSHED_DETAIL)
        developer_state = self._pinned(developer_gh)
        self.assertFalse(developer_state.get(AWAITING_HUMAN))
        self.assertIsNone(developer_state.get(PARK_REASON))
        # Bumped: a real fix landed.
        self.assertEqual(developer_state.get(REVIEW_ROUND), 2)
        self.assertIsNone(developer_state.get(PRE_DEV_FIX_SHA))
        # Stays on `validating` (no documenting hop) so the reviewer
        # re-evaluates the recovered head on the next tick.
        self.assertNotIn((VALIDATING_ISSUE, "workflow:documenting"), developer_gh.label_history)

    def test_timeout_work_is_measured_first(self) -> None:
        # The one road to a published pull request that never reached the
        # gate: the park was taken because the run timed out, so nothing
        # measured the commit it turned out to have made. The recovery
        # measures it here and names the push against what came back.
        measured = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )
        gh = measured[0]

        mocks = self._run_parked_validating(
            *measured,
            run_agent=_agent(),
            dirty_files=(),
            push_branch=True,
            head_shas=(TIMEOUT_HEAD,),
        )

        mocks[COUNT_ADDED_LINES].assert_called_once()
        pushed = self._pushes(mocks).call_args
        self.assertEqual(pushed.kwargs["revision"], MEASURED_CANDIDATE_SHA)
        self.assertIsNone(self._pinned(gh).get(LATE_APPROVED_SHA))

    def test_the_switch_publishes_oversized_work(self) -> None:
        # The same commit on an install that turned the gate off. No developer
        # ran on this tick -- the one that did was killed -- but nothing on the
        # record ever asked for this commit to be read, so it is the new work
        # `DECOMPOSE=off` publishes untouched rather than a reading the gate
        # already took.
        switched_off = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )
        gh = switched_off[0]

        with patch.object(config, DECOMPOSE, False), patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._run_parked_validating(
                *switched_off,
                run_agent=_agent(),
                dirty_files=(),
                push_branch=True,
                head_shas=(TIMEOUT_HEAD,),
                added_lines=PAST_THE_CEILING,
            )

        mocks[COUNT_ADDED_LINES].assert_not_called()
        self._pushes(mocks).assert_called_once()
        self.assertNotIn(
            (VALIDATING_ISSUE, LABEL_DECOMPOSING), gh.label_history,
        )

    def test_oversized_timeout_work_is_held(self) -> None:
        # Nothing is pushed and the issue goes to the adjudication instead of
        # back to the reviewer -- and no follow-up is posted, because no
        # recovery happened for the operator to be told about.
        oversized = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )
        gh = oversized[0]

        with patch.object(config, MAX_ADDED_LINES, CEILING):
            mocks = self._run_parked_validating(
                *oversized,
                run_agent=_agent(),
                dirty_files=(),
                push_branch=True,
                head_shas=(TIMEOUT_HEAD,),
                added_lines=PAST_THE_CEILING,
            )

        self._pushes(mocks).assert_not_called()
        self.assertEqual(
            gh.label_history, [(VALIDATING_ISSUE, LABEL_DECOMPOSING)],
        )
        self.assertFalse(
            any(RECOVERED_PREFIX in body for _, body in gh.posted_comments),
        )
        # The recovery counts a round for a fix that reaches the reviewer, and
        # a held one reaches it just the same: the commit is on the branch and
        # a `single` verdict publishes it from there. Left uncounted, nothing
        # goes back for it -- the settlement pushes the accepted commit itself
        # and the resumed recovery finds nothing to publish -- so
        # `MAX_REVIEW_ROUNDS` stops meaning what it says on this issue.
        self.assertEqual(self._pinned(gh).get(REVIEW_ROUND), 2)

class ValidatingDevParkSafetyTest(
    unittest.TestCase,
    _TransientParkFixtureMixin,
):
    """Keep unsafe or unanchored dev timeout recoveries parked."""

    def test_timeout_push_error_stays_parked(
        self,
    ) -> None:
        developer_gh, issue = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )

        developer_mocks = self._run_parked_validating(
            developer_gh,
            issue,
            run_agent=_agent(),
            dirty_files=(),
            push_branch=False,
            head_shas=(TIMEOUT_HEAD,),
        )

        developer_mocks[PUSH_BRANCH].assert_called_once()
        self.assertEqual(developer_gh.posted_comments, [])
        developer_state = self._pinned(developer_gh)
        self.assertTrue(developer_state.get(AWAITING_HUMAN))
        self.assertEqual(developer_state.get(PARK_REASON), AGENT_TIMEOUT)
        # NOT bumped while still stuck; watermark preserved for next try.
        self.assertEqual(developer_state.get(REVIEW_ROUND), 1)
        self.assertEqual(developer_state.get(PRE_DEV_FIX_SHA), PRE_FIX_SHA)

    def test_a_head_moved_between_the_reads_stops(self) -> None:
        # This recovery reads the head to decide the killed run committed at
        # all, and the gate proves the checkout again before it measures.
        # Unbound, a commit landing between the two would be measured, pushed,
        # and receipted as the work that run left behind. Nothing is measured
        # and nothing goes out; the watermark stands, so the retry asks for the
        # same commit once the checkout is back where it was left.
        moved = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )

        moved_mocks = self._run_parked_validating(
            *moved,
            run_agent=_agent(),
            dirty_files=(),
            push_branch=True,
            head_shas=(TIMEOUT_HEAD,),
            candidate_commit=FrozenCommit(sha=MOVED_HEAD),
        )

        moved_mocks[COUNT_ADDED_LINES].assert_not_called()
        moved_mocks[PUSH_BRANCH].assert_not_called()
        moved_state = self._pinned(moved[0])
        self.assertTrue(moved_state.get(AWAITING_HUMAN))
        self.assertEqual(moved_state.get(PARK_REASON), PARK_MEASUREMENT_FAILED)
        self.assertEqual(moved_state.get(PRE_DEV_FIX_SHA), PRE_FIX_SHA)

    def test_dirty_timeout_stays_parked(self) -> None:
        # The dev edited files without committing before timing out.
        # Recovery refuses to silently push (would publish an incomplete
        # branch) or to clear flags (the next reviewer would inspect
        # uncommitted state). Stays parked until a human or comment-
        # driven resume sorts the dirty edits out.
        safety_gh, issue = self._parked_issue(
            park_reason=AGENT_TIMEOUT,
            pre_dev_fix_sha=PRE_FIX_SHA,
        )

        safety_mocks = self._run_parked_validating(
            safety_gh,
            issue,
            run_agent=_agent(),
            dirty_files=["leftover.py"],
            push_branch=True,
        )

        safety_mocks[RUN_AGENT].assert_not_called()
        safety_mocks[PUSH_BRANCH].assert_not_called()
        # No new comment posted on this tick -- the original park
        # message still describes the situation.
        self.assertEqual(safety_gh.posted_comments, [])
        safety_state = safety_gh.pinned_data(VALIDATING_ISSUE)
        self.assertTrue(safety_state.get(AWAITING_HUMAN))
        self.assertEqual(safety_state.get(PARK_REASON), AGENT_TIMEOUT)
        self.assertEqual(safety_state.get(REVIEW_ROUND), 1)

    def test_timeout_without_watermark_stays_parked(self) -> None:
        # Defensive: if the timeout park ran in foreign code that did
        # not persist `pre_dev_fix_sha`, recovery cannot tell whether a
        # commit was produced. Refuse to act -- a force-push of a stale
        # local HEAD would silently rewrite remote.
        safety_gh, issue = self._parked_issue(park_reason=AGENT_TIMEOUT)

        safety_mocks = self._run_parked_validating(
            safety_gh,
            issue,
            run_agent=_agent(),
            dirty_files=(),
            push_branch=True,
            head_shas=("anything",),
        )

        safety_mocks[RUN_AGENT].assert_not_called()
        safety_mocks[PUSH_BRANCH].assert_not_called()
        safety_state = safety_gh.pinned_data(VALIDATING_ISSUE)
        self.assertTrue(safety_state.get(AWAITING_HUMAN))
        self.assertEqual(safety_state.get(PARK_REASON), AGENT_TIMEOUT)

    def test_transient_comment_takes_resume_path(self) -> None:
        # A transient park is preempted by a fresh human comment: the
        # comment-driven resume path wins, the dev is spawned with the
        # human's feedback, and the recovery branch does not silently
        # retry the push. This ensures the human's reply is not dropped.
        safety_gh, issue = self._parked_issue(park_reason=PUSH_FAILED)
        issue.comments.append(
            FakeComment(
                id=HUMAN_REPLY_ID,
                body=REBASE_REQUEST,
                user=FakeUser(HUMAN_LOGIN),
            )
        )

        safety_mocks = self._run_parked_validating(
            safety_gh,
            issue,
            run_agent=_agent(
                session_id=DEV_SESSION,
                last_message="rebased",
            ),
            push_branch=True,
            head_shas=[PRE_FIX_SHA, MEASURED_CANDIDATE_SHA],
        )

        # Dev was resumed with the human's feedback (recovery did NOT run).
        safety_mocks[RUN_AGENT].assert_called_once()
        followup = safety_mocks[RUN_AGENT].call_args.args[1]
        self.assertIn(REBASE_REQUEST, followup)
        safety_state = safety_gh.pinned_data(VALIDATING_ISSUE)
        self.assertFalse(safety_state.get(AWAITING_HUMAN))


class HandleValidatingResumeOnHashChangeTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
):
    def test_body_drift_resumes_and_stays_validating(self) -> None:
        # While validating (PR is open), a human edit must not discard the
        # dev's already-pushed work. Notify and resume; on a successful
        # pushed fix, stay on `validating` so the reviewer re-evaluates
        # the new diff next tick. The docs pass only runs as the
        # final-docs handoff after a fresh approval.
        body_drift_gh = FakeGitHubClient()
        issue = make_issue(BODY_DRIFT_ISSUE, label="workflow:validating", body="updated criteria")
        body_drift_gh.add_issue(issue)
        pr = FakePR(number=BODY_DRIFT_PR, head_branch="orchestrator/chippingway__orchestrator/issue-70")
        body_drift_gh.add_pr(pr)
        body_drift_gh.seed_state(
            BODY_DRIFT_ISSUE,
            user_content_hash="stale-hash",
            dev_agent="claude",
            dev_session_id=DEV_SESSION,
            pr_number=pr.number,
            review_round=0,
            branch="orchestrator/chippingway__orchestrator/issue-70",
        )

        self._run_validating(
            body_drift_gh,
            issue,
            run_agent=_agent(session_id=DEV_SESSION, last_message="fixed"),
            has_new_commits=True,
            dirty_files=(),
            push_branch=True,
            head_shas=[PRE_FIX_SHA, MEASURED_CANDIDATE_SHA],
        )

        # Stays on `validating`: no documenting hop, and the reviewer
        # has NOT been spawned this tick (the only run_agent call was
        # the dev resume).
        self.assertNotIn((BODY_DRIFT_ISSUE, "workflow:documenting"), body_drift_gh.label_history)
        self.assertNotIn((BODY_DRIFT_ISSUE, "in_review"), body_drift_gh.label_history)
        # Notice posted on the issue thread.
        self.assertTrue(
            any(
                "issue body changed" in body
                for _, body in body_drift_gh.posted_comments
            )
        )
        # review_round incremented so the validating cap stays accurate.
        body_drift_state = body_drift_gh.pinned_data(BODY_DRIFT_ISSUE)
        self.assertEqual(body_drift_state.get(REVIEW_ROUND), 1)


class ValidatingDriftDefersToReviewerRecoveryTest(
    unittest.TestCase,
    _PatchedWorkflowMixin,
):
    """Reviewer point 1: when validating is parked with a reviewer-side
    park reason (`reviewer_timeout` / `reviewer_failed`), a human "retry"
    comment must re-spawn the REVIEWER, not the dev session. The drift
    check fires first because the human's comment also flips the hash;
    the drift handler must defer to the awaiting-human branch in this
    case so the reviewer re-runs naturally."""

    def test_timeout_drift_respawns_reviewer(
        self,
    ) -> None:
        # The human reply changes the user-content hash while the issue
        # remains parked for reviewer recovery.
        reviewer_drift_gh, issue = self._parked_reviewer_drift()

        reviewer_drift_mocks = self._run_validating(
            reviewer_drift_gh,
            issue,
            run_agent=_agent(
                session_id="rev-sess",
                last_message="Looks fine.\n\nVERDICT: APPROVED",
            ),
            has_new_commits=False,
            head_shas=["head"],
        )

        # The reviewer (REVIEW_AGENT) ran, NOT the dev session. The
        # agent invocation should have been against the review agent
        # binary, with a review-style prompt.
        call_args = reviewer_drift_mocks[RUN_AGENT].call_args
        self.assertEqual(call_args[0][0], config.REVIEW_AGENT)
        self.assertIn("automated code reviewer", call_args[0][1])
        # No drift-style ":pencil2: issue body changed; resuming dev
        # session" notice was posted -- the drift was deferred.
        self._assert_no_drift_notice(reviewer_drift_gh)
        # The reviewer recovery consumed the human comment and cleared
        # the park flags.
        reviewer_drift_state = reviewer_drift_gh.pinned_data(1000)
        self.assertFalse(reviewer_drift_state.get(AWAITING_HUMAN))
        self.assertIsNone(reviewer_drift_state.get(PARK_REASON))
        # The new hash baseline was persisted so the next tick doesn't
        # loop on the same drift.
        self.assertEqual(
            reviewer_drift_state.get("user_content_hash"),
            _content_hash._compute_user_content_hash(issue, set()),
        )

    def _parked_reviewer_drift(self):
        reviewer_drift_gh = FakeGitHubClient()
        issue = make_issue(
            1000,
            label="workflow:validating",
            body="initial body",
        )
        issue.comments.append(
            FakeComment(
                id=REVIEWER_RETRY_COMMENT_ID,
                body="retry the reviewer please",
                user=FakeUser(HUMAN_LOGIN),
            ),
        )
        reviewer_drift_gh.add_issue(issue)
        reviewer_drift_gh.add_pr(
            FakePR(
                number=REVIEWER_DRIFT_PR,
                head_branch="orchestrator/chippingway__orchestrator/issue-1000",
            ),
        )
        seed_hash = _content_hash._compute_user_content_hash(
            make_issue(1000, body="initial body"),
            set(),
        )
        reviewer_drift_gh.seed_state(
            1000,
            pr_number=REVIEWER_DRIFT_PR,
            dev_agent="claude",
            dev_session_id=DEV_SESSION,
            review_round=1,
            branch="orchestrator/chippingway__orchestrator/issue-1000",
            awaiting_human=True,
            park_reason=REVIEWER_TIMEOUT,
            last_action_comment_id=100,
            user_content_hash=seed_hash,
        )
        return reviewer_drift_gh, issue

    def _assert_no_drift_notice(self, github) -> None:
        self.assertFalse(
            any(
                ":pencil2:" in body
                and "resuming dev session" in body
                for _, body in github.posted_comments
            ),
        )
