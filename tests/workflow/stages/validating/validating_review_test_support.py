# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and protocol values for validating review-loop tests."""

from __future__ import annotations

import pathlib
from unittest import mock

from orchestrator import config as _config
from orchestrator.workflow.engine import content_hash as _content_hash
from tests.support import fakes
from tests.workflow import fixtures

Path = pathlib.Path
patch = mock.patch
MagicMock = mock.MagicMock
config = _config

FakeComment = fakes.FakeComment
FakeGitHubClient = fakes.FakeGitHubClient
FakeUser = fakes.FakeUser
make_issue = fakes.make_issue

EVENT_AGENT_SPAWN = fixtures.EVENT_AGENT_SPAWN
LABEL_DOCUMENTING = fixtures.LABEL_DOCUMENTING
LABEL_FIXING = fixtures.LABEL_FIXING
LABEL_IN_REVIEW = fixtures.LABEL_IN_REVIEW
AGENT_RUN_CHARGE_WRITES = fixtures.AGENT_RUN_CHARGE_WRITES
LABEL_VALIDATING = fixtures.LABEL_VALIDATING
STAGE_FIXING = fixtures.STAGE_FIXING
STAGE_VALIDATING = fixtures.STAGE_VALIDATING
PROVIDER_OVERLOAD_MENTION = fixtures.PROVIDER_OVERLOAD_MENTION
PROVIDER_OVERLOAD_MESSAGE = fixtures.PROVIDER_OVERLOAD_MESSAGE
PROVIDER_UNAVAILABLE_PHRASE = fixtures.PROVIDER_UNAVAILABLE_PHRASE
REVIEW_APPROVED_MESSAGE = fixtures.REVIEW_APPROVED_MESSAGE
REVIEW_CHANGES_REQUESTED_MESSAGE = fixtures.REVIEW_CHANGES_REQUESTED_MESSAGE
ROLE_DEVELOPER = fixtures.ROLE_DEVELOPER
ROLE_REVIEWER = fixtures.ROLE_REVIEWER
_PatchedWorkflowMixin = fixtures._PatchedWorkflowMixin
_TEST_SPEC = fixtures._TEST_SPEC
_agent = fixtures._agent
_issue_branch = fixtures._issue_branch
_open_pr_for = fixtures._open_pr_for

FRESH_REVIEW_ISSUE = 5
FRESH_REVIEW_PR = 11
FIX_LOOP_ISSUE = 6
FIX_LOOP_PR = 12
HUMAN_RESUME_ISSUE = 7
RESUME_PR = 13
REVIEW_CAP_ISSUE = 80
REVIEW_CAP_PR = 15
CAP_REASON_PR = 17
CAP_RECOVERY_ISSUE = 83
SECONDARY_PR = 18
TRUST_CAP_ISSUE = 90
TRUST_RETRY_ISSUE = 91
HUMAN_COMMENT_ID = 1100
FOLLOWUP_COMMENT_ID = 1200
CAP_COMMAND_ID = 2000
ACTION_COMMENT_ID = 950
DEV_SESSION = "dev-sess"

# The head a fix run starts on and the head it leaves the checkout at. The
# second IS the commit the size gate proves that checkout to, because in
# production the two are one read of one worktree: the route names the commit
# it means to publish and the gate refuses a checkout standing anywhere else,
# so a fixture spelling them apart would model the race rather than the tick.
#
# The first is the head the pull request is standing on for the same reason:
# the branch is in sync with its publication when a fix round opens, since the
# reviewer just read that head. It is what the round names to the gate, so a
# pull request somebody moved while the agent was out refuses the push.
BEFORE_FIX_SHA = fakes.DEFAULT_PR_HEAD_SHA
AFTER_FIX_SHA = fixtures.MEASURED_CANDIDATE_SHA
FIX_HEAD_SHAS = (BEFORE_FIX_SHA, AFTER_FIX_SHA)

BACKEND_CLAUDE = "claude"
BACKEND_CODEX = "codex"
HUMAN_LOGIN = "alice"
REVIEW_CAP = "review_cap"
RUN_AGENT = "run_agent"
PR_NUMBER = "pr_number"
REVIEW_ROUND = "review_round"
AWAITING_HUMAN = "awaiting_human"


class FreshReviewFixtureMixin(_PatchedWorkflowMixin):
    def _seeded(self, **state):
        github = FakeGitHubClient()
        issue = make_issue(FRESH_REVIEW_ISSUE, label=LABEL_VALIDATING)
        github.add_issue(issue)
        defaults = {
            PR_NUMBER: FRESH_REVIEW_PR,
            "branch": _issue_branch(FRESH_REVIEW_ISSUE),
            "codex_session_id": DEV_SESSION,
            REVIEW_ROUND: 0,
        }
        defaults.update(state)
        github.seed_state(FRESH_REVIEW_ISSUE, **defaults)
        _open_pr_for(
            github,
            issue_number=FRESH_REVIEW_ISSUE,
            pr_number=defaults[PR_NUMBER],
        )
        return github, issue

    def _assert_dev_fix_call(self, mocks) -> None:
        self.assertEqual(mocks[RUN_AGENT].call_count, 2)
        second_kwargs = mocks[RUN_AGENT].call_args_list[1].kwargs
        self.assertEqual(second_kwargs.get("resume_session_id"), DEV_SESSION)

    def _assert_fix_labels(self, github) -> None:
        self.assertIn((FRESH_REVIEW_ISSUE, LABEL_FIXING), github.label_history)
        self.assertEqual(
            github.label_history[-1],
            (FRESH_REVIEW_ISSUE, LABEL_VALIDATING),
        )
        fixing_index = github.label_history.index((FRESH_REVIEW_ISSUE, LABEL_FIXING))
        validating_index = github.label_history.index((FRESH_REVIEW_ISSUE, LABEL_VALIDATING))
        self.assertLess(fixing_index, validating_index)
        self.assertNotIn((FRESH_REVIEW_ISSUE, LABEL_DOCUMENTING), github.label_history)
        self.assertNotIn((FRESH_REVIEW_ISSUE, LABEL_IN_REVIEW), github.label_history)


class FixLoopFixtureMixin(_PatchedWorkflowMixin):
    def _seeded(self, *, stale_label_cache=False, **state):
        github = FakeGitHubClient(stale_label_cache=stale_label_cache)
        issue = make_issue(FIX_LOOP_ISSUE, label=LABEL_VALIDATING)
        github.add_issue(issue)
        defaults = {
            PR_NUMBER: FIX_LOOP_PR,
            "branch": _issue_branch(FIX_LOOP_ISSUE),
            "codex_session_id": DEV_SESSION,
            REVIEW_ROUND: 0,
        }
        defaults.update(state)
        github.seed_state(FIX_LOOP_ISSUE, **defaults)
        _open_pr_for(
            github,
            issue_number=FIX_LOOP_ISSUE,
            pr_number=defaults[PR_NUMBER],
        )
        return github, issue

    def _changes_requested_review(self):
        return _agent(
            session_id="rev-sess",
            last_message=REVIEW_CHANGES_REQUESTED_MESSAGE,
        )


class ContinueCommandFixtureMixin(_PatchedWorkflowMixin):
    def _seed(self, number, *, park_reason, command="/orchestrator continue"):
        github = FakeGitHubClient()
        issue = make_issue(number, label=LABEL_VALIDATING, body="the requirements")
        issue.comments.append(
            FakeComment(
                id=HUMAN_COMMENT_ID,
                body=command,
                user=FakeUser("dave"),
            ),
        )
        github.add_issue(issue)
        github.seed_state(
            number,
            awaiting_human=True,
            park_reason=park_reason,
            last_action_comment_id=ACTION_COMMENT_ID,
            dev_agent=BACKEND_CLAUDE,
            dev_session_id=DEV_SESSION,
            silent_park_count=1,
            review_round=1,
            pr_number=RESUME_PR,
            branch=_issue_branch(number),
            user_content_hash=_content_hash._compute_user_content_hash(issue, set()),
        )
        _open_pr_for(github, issue_number=number, pr_number=RESUME_PR)
        return github, issue

    def _assert_retry_result(self, github, mocks) -> None:
        self.assertEqual(mocks[RUN_AGENT].call_count, 1)
        followup = mocks[RUN_AGENT].call_args.args[1]
        self.assertIn("session/usage limit", followup)
        self.assertNotIn("/orchestrator continue", followup)
        self.assertEqual(
            mocks[RUN_AGENT].call_args.kwargs.get("resume_session_id"),
            DEV_SESSION,
        )
        self.assertFalse(
            any("issue body changed" in body for _, body in github.posted_comments)
        )
        state = github.pinned_data(HUMAN_RESUME_ISSUE)
        self.assertFalse(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get(REVIEW_ROUND), 2)
        self.assertEqual(state.get("last_action_comment_id"), HUMAN_COMMENT_ID)


class ReviewCapFixtureMixin(_PatchedWorkflowMixin):
    def _seeded(self, *, comment_body: str | None = None, **state):
        github = FakeGitHubClient()
        issue = make_issue(REVIEW_CAP_ISSUE, label=LABEL_VALIDATING)
        if comment_body is not None:
            issue.comments.append(
                FakeComment(
                    id=HUMAN_COMMENT_ID,
                    body=comment_body,
                    user=FakeUser(HUMAN_LOGIN),
                ),
            )
        github.add_issue(issue)
        defaults = {
            AWAITING_HUMAN: True,
            "park_reason": REVIEW_CAP,
            "last_action_comment_id": ACTION_COMMENT_ID,
            REVIEW_ROUND: config.MAX_REVIEW_ROUNDS,
            "dev_session_id": DEV_SESSION,
            "dev_agent": BACKEND_CODEX,
            PR_NUMBER: REVIEW_CAP_PR,
            "branch": _issue_branch(REVIEW_CAP_ISSUE),
        }
        defaults.update(state)
        github.seed_state(REVIEW_CAP_ISSUE, **defaults)
        _open_pr_for(
            github,
            issue_number=REVIEW_CAP_ISSUE,
            pr_number=defaults[PR_NUMBER],
        )
        return github, issue

    def _assert_reviewer_spawn(self, github) -> None:
        reviewer_spawns = [
            event
            for event in github.recorded_events
            if event["event"] == EVENT_AGENT_SPAWN and event.get("agent_role") == ROLE_REVIEWER
        ]
        self.assertEqual(len(reviewer_spawns), 1)
        self.assertEqual(
            reviewer_spawns[0][REVIEW_ROUND],
            config.MAX_REVIEW_ROUNDS - 1,
        )


class InterruptedFixFixtureMixin:
    def _seeded(self, **state):
        github = FakeGitHubClient()
        issue = make_issue(HUMAN_RESUME_ISSUE, label=LABEL_VALIDATING)
        github.add_issue(issue)
        github.seed_state(HUMAN_RESUME_ISSUE, **state)
        return github, github.read_pinned_state(issue), issue


class ResumeTrustFixtureMixin(_PatchedWorkflowMixin):
    def _seed_cap_park(self, github, *, author, body):
        issue = make_issue(TRUST_CAP_ISSUE, label=LABEL_VALIDATING)
        issue.comments.append(
            FakeComment(
                id=HUMAN_COMMENT_ID,
                body=body,
                user=FakeUser(author),
            ),
        )
        github.add_issue(issue)
        github.seed_state(
            TRUST_CAP_ISSUE,
            awaiting_human=True,
            park_reason=REVIEW_CAP,
            last_action_comment_id=ACTION_COMMENT_ID,
            review_round=config.MAX_REVIEW_ROUNDS,
            dev_session_id=DEV_SESSION,
            dev_agent=BACKEND_CODEX,
            pr_number=CAP_REASON_PR,
            branch=_issue_branch(TRUST_CAP_ISSUE),
        )
        _open_pr_for(
            github, issue_number=TRUST_CAP_ISSUE, pr_number=CAP_REASON_PR,
        )
        return issue

    def _seed_reviewer_timeout_park(self, github, *, author):
        issue = make_issue(TRUST_RETRY_ISSUE, label=LABEL_VALIDATING)
        issue.comments.append(
            FakeComment(
                id=FOLLOWUP_COMMENT_ID,
                body="please retry",
                user=FakeUser(author),
            ),
        )
        github.add_issue(issue)
        github.seed_state(
            TRUST_RETRY_ISSUE,
            awaiting_human=True,
            park_reason="reviewer_timeout",
            last_action_comment_id=ACTION_COMMENT_ID,
            review_round=1,
            dev_session_id=DEV_SESSION,
            dev_agent=BACKEND_CODEX,
            pr_number=SECONDARY_PR,
            branch=_issue_branch(TRUST_RETRY_ISSUE),
        )
        _open_pr_for(
            github, issue_number=TRUST_RETRY_ISSUE, pr_number=SECONDARY_PR,
        )
        return issue


class CapRecoveryAssertionsMixin:
    def _cap_park_hash(self, github) -> str:
        state = github.pinned_data(CAP_RECOVERY_ISSUE)
        self.assertTrue(state.get(AWAITING_HUMAN))
        self.assertEqual(state.get("park_reason"), REVIEW_CAP)
        self.assertIsInstance(state.get("user_content_hash"), str)
        return state["user_content_hash"]

    def _assert_cap_reset_state(self, github, baseline_hash: str) -> None:
        state = github.pinned_data(CAP_RECOVERY_ISSUE)
        self.assertFalse(state.get(AWAITING_HUMAN))
        self.assertIsNone(state.get("park_reason"))
        self.assertEqual(
            state.get(REVIEW_ROUND),
            config.MAX_REVIEW_ROUNDS - 1,
        )
        self.assertEqual(state.get("last_action_comment_id"), CAP_COMMAND_ID)
        self.assertNotEqual(state.get("user_content_hash"), baseline_hash)
        self.assertFalse(
            any("issue body changed; resuming dev session" in body for _, body in github.posted_comments)
        )
        self.assertTrue(
            any("review-cap reset" in body for _, body in github.posted_comments)
        )

    def _assert_cap_reset_event(self, github) -> None:
        reviewer_spawns = [
            event
            for event in github.recorded_events
            if event["event"] == EVENT_AGENT_SPAWN and event.get("agent_role") == ROLE_REVIEWER
        ]
        self.assertEqual(len(reviewer_spawns), 1)
        self.assertEqual(
            reviewer_spawns[0][REVIEW_ROUND],
            config.MAX_REVIEW_ROUNDS - 1,
        )
