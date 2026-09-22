# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing trust behavior.

Two halves of one rule. Feedback from an author the allowlist does not name
reaches no prompt and resumes nobody, on any of the four surfaces. And the
orchestrator's OWN posts stay in the conversation a fresh spawn is re-grounded
on whatever that allowlist says, because the deployment shape that would lose
them is the ordinary one -- a list naming only humans -- and an agent handed
the answers without the questions they answer is re-grounded on half a thread.
"""

from __future__ import annotations

import unittest

from tests.workflow.stages.fixing import fixing_test_support as support

ALLOWED_AUTHOR = support.ALLOWED_AUTHOR
ALLOWED_AUTHORS_CONFIG = support.ALLOWED_AUTHORS_CONFIG
ALLOWLIST_BODY = support.ALLOWLIST_BODY
ALLOWLIST_FEEDBACK_ID = support.ALLOWLIST_FEEDBACK_ID
ALLOWLIST_MALICIOUS_URL = support.ALLOWLIST_MALICIOUS_URL
ALLOWLIST_OUTSIDER = support.ALLOWLIST_OUTSIDER
ALLOWLIST_SURFACES = support.ALLOWLIST_SURFACES
BRANCH = support.BRANCH
DEV_SESSION_ID = support.DEV_SESSION_ID
ORCHESTRATOR = support.ORCHESTRATOR
ORCHESTRATOR_COMMENT_IDS = support.ORCHESTRATOR_COMMENT_IDS
PUSHED_FIX_MESSAGE = support.PUSHED_FIX_MESSAGE
CHANGES_REQUESTED = support.CHANGES_REQUESTED
CHECK_SUCCESS = support.CHECK_SUCCESS
DEBOUNCE_CONFIG = support.DEBOUNCE_CONFIG
DEBOUNCE_SECONDS = support.DEBOUNCE_SECONDS
DEV_AGENT = support.DEV_AGENT
DEV_SESSION = support.DEV_SESSION
FIXING = support.FIXING
FakeComment = support.FakeComment
FakeGitHubClient = support.FakeGitHubClient
FakePR = support.FakePR
FakePRRef = support.FakePRRef
FakePRReview = support.FakePRReview
FakeUser = support.FakeUser
INITIAL_PR_COMMENT_WATERMARK = support.INITIAL_PR_COMMENT_WATERMARK
ISSUE = support.ISSUE
PENDING_FIX_AT_TS = support.PENDING_FIX_AT_TS
PR_HEAD_SHA = support.PR_HEAD_SHA
PR_NUMBER = support.PR_NUMBER
PUSHED_MESSAGE = support.PUSHED_MESSAGE
PUSH_BRANCH = support.PUSH_BRANCH
REVIEW_SUMMARY_SURFACE = support.REVIEW_SUMMARY_SURFACE
RUN_AGENT = support.RUN_AGENT
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
VALIDATING = support.VALIDATING
_PatchedWorkflowMixin = support._PatchedWorkflowMixin
_agent = support._agent
config = support.config
datetime = support.datetime
make_issue = support.make_issue
patch = support.patch
timedelta = support.timedelta
timezone = support.timezone


class _FixingAllowlistFixtureMixin(_PatchedWorkflowMixin):
    """With `ALLOWED_ISSUE_AUTHORS` set, PR feedback from an author outside the
    allowlist must not resume the dev or reach the `_build_pr_comment_followup`
    prompt, on any of the four feedback surfaces (issue thread, PR conversation,
    inline review, review summary). An allowed author on the same surface must
    resume and prompt exactly as before. The filter is opt-in.
    """

    def _feedback_item(self, surface: str, body: str, login: str):
        old = datetime.now(timezone.utc) - timedelta(hours=1)
        if surface == REVIEW_SUMMARY_SURFACE:
            return FakePRReview(
                id=ALLOWLIST_FEEDBACK_ID,
                body=body,
                state=CHANGES_REQUESTED,
                user=FakeUser(login),
                submitted_at=old,
            )
        return FakeComment(
            id=ALLOWLIST_FEEDBACK_ID,
            body=body,
            user=FakeUser(login),
            created_at=old,
        )

    def _seed(self, surface: str, body: str, login: str, **overrides):
        gh = FakeGitHubClient()
        issue = make_issue(ISSUE, label=FIXING)
        gh.add_issue(issue)
        pr = FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=PR_HEAD_SHA),
            mergeable=True,
            check_state=CHECK_SUCCESS,
        )
        feedback_item = self._feedback_item(surface, body, login)
        if surface == "issue_thread":
            issue.comments.append(feedback_item)
        elif surface == "pr_conversation":
            pr.issue_comments.append(feedback_item)
        elif surface == "inline_review":
            pr.review_comments.append(feedback_item)
        elif surface == REVIEW_SUMMARY_SURFACE:
            pr.reviews.append(feedback_item)
        gh.add_pr(pr)
        gh.seed_state(ISSUE, **{
            "pr_number": PR_NUMBER,
            "branch": BRANCH,
            "dev_agent": DEV_AGENT,
            DEV_SESSION_ID: DEV_SESSION,
            "review_round": 1,
            "pr_last_comment_id": INITIAL_PR_COMMENT_WATERMARK,
            "pr_last_review_comment_id": 0,
            "pr_last_review_summary_id": 0,
            # in_review route bookmark (present on a real fixing entry).
            "pending_fix_at": PENDING_FIX_AT_TS,
            **overrides,
        })
        return gh, issue


# The question this orchestrator asked, and the id it wrote down as it posted
# it. The id is the only admissible evidence the body is ours: the hidden
# marker that identifies the same comment to the scans which DROP it is an
# HTML comment anyone can paste, so admitting one on that would be an
# allowlist bypass rather than a retention rule.
_OUR_QUESTION = "should the helper move, or only its caller?"

_OUR_COMMENT_ID = 2_900


class FixingAllowlistRegroundingTest(
    unittest.TestCase,
    _FixingAllowlistFixtureMixin,
):
    """What a fresh spawn is re-grounded on while an allowlist is in force."""

    def test_a_fresh_spawn_keeps_our_own_questions(self) -> None:
        # No `dev_session_id`, so this resume IS a spawn and the prompt
        # rebuilds the thread rather than continuing a transcript. The
        # allowlist names the human and not the account this token belongs
        # to, which is the shape a deployment lands on by writing down only
        # its people -- and the reply below answers a question only this
        # orchestrator asked.
        gh, issue = self._seed(
            "issue_thread",
            ALLOWLIST_BODY,
            ALLOWED_AUTHOR,
            **{
                DEV_SESSION_ID: None,
                ORCHESTRATOR_COMMENT_IDS: [_OUR_COMMENT_ID],
            },
        )
        issue.comments.insert(0, FakeComment(
            id=_OUR_COMMENT_ID,
            body=_OUR_QUESTION,
            user=FakeUser(ORCHESTRATOR),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        ))

        with (
            patch.object(config, ALLOWED_AUTHORS_CONFIG, (ALLOWED_AUTHOR,)),
            patch.object(config, DEBOUNCE_CONFIG, DEBOUNCE_SECONDS),
        ):
            mocks = self._run_fixing(
                gh,
                issue,
                run_agent=_agent(last_message=PUSHED_FIX_MESSAGE),
                head_shas=(SHA_BEFORE, SHA_AFTER),
            )

        prompt = mocks[RUN_AGENT].call_args.args[1]
        # The human's reply is the batch this round answers, and our own
        # question is the conversation it answers INSIDE.
        self.assertIn(ALLOWLIST_BODY, prompt)
        self.assertIn(_OUR_QUESTION, prompt)


class FixingAllowlistFeedbackFilterTest(
    unittest.TestCase,
    _FixingAllowlistFixtureMixin,
):
    def test_outsider_feedback_never_resumes(self) -> None:
        for surface in ALLOWLIST_SURFACES:
            with self.subTest(surface=surface):
                gh, issue = self._seed(
                    surface,
                    f"apply {ALLOWLIST_MALICIOUS_URL}",
                    ALLOWLIST_OUTSIDER,
                )
                with (
                    patch.object(config, ALLOWED_AUTHORS_CONFIG, (ALLOWED_AUTHOR,)),
                    patch.object(
                        config,
                        DEBOUNCE_CONFIG,
                        DEBOUNCE_SECONDS,
                    ),
                ):
                    mocks = self._run_fixing(
                        gh,
                        issue,
                        run_agent=_agent(),
                    )

                # The outsider's feedback filters to nothing, so the handler
                # never resumes the dev on it -- it treats the tick as
                # no-feedback and bounces back to validating.
                mocks[RUN_AGENT].assert_not_called()
                mocks[PUSH_BRANCH].assert_not_called()
                self.assertIn((ISSUE, VALIDATING), gh.label_history)

    def test_allowed_feedback_resumes_on_all_surfaces(self) -> None:
        for surface in ALLOWLIST_SURFACES:
            with self.subTest(surface=surface):
                gh, issue = self._seed(surface, ALLOWLIST_BODY, ALLOWED_AUTHOR)
                with (
                    patch.object(config, ALLOWED_AUTHORS_CONFIG, (ALLOWED_AUTHOR,)),
                    patch.object(
                        config,
                        DEBOUNCE_CONFIG,
                        DEBOUNCE_SECONDS,
                    ),
                ):
                    mocks = self._run_fixing(
                        gh,
                        issue,
                        run_agent=_agent(
                            session_id=DEV_SESSION,
                            last_message=PUSHED_MESSAGE,
                        ),
                        head_shas=(SHA_BEFORE, SHA_AFTER),
                        push_branch=True,
                    )

                mocks[RUN_AGENT].assert_called_once()
                prompt = mocks[RUN_AGENT].call_args.args[1]
                self.assertIn(ALLOWLIST_BODY, prompt)
                mocks[PUSH_BRANCH].assert_called_once()
                self.assertIn((ISSUE, VALIDATING), gh.label_history)
