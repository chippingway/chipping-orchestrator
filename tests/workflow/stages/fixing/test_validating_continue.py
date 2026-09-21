# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing validating continue behavior."""

from __future__ import annotations

import unittest

from tests.workflow.stages.fixing import fixing_test_support as support
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
    replayed_task,
)

ADVANCED_PR_COMMENT_WATERMARK = support.ADVANCED_PR_COMMENT_WATERMARK
ADVANCED_REVIEW_COMMENT_WATERMARK = support.ADVANCED_REVIEW_COMMENT_WATERMARK
ADVANCED_REVIEW_SUMMARY_WATERMARK = support.ADVANCED_REVIEW_SUMMARY_WATERMARK
ALICE = support.ALICE
AWAITING_HUMAN = support.AWAITING_HUMAN
BATCH_INLINE_ID = support.BATCH_INLINE_ID
BATCH_ISSUE_ID = support.BATCH_ISSUE_ID
BATCH_ISSUE_IDS = support.BATCH_ISSUE_IDS
BATCH_PR_CONVERSATION_ID = support.BATCH_PR_CONVERSATION_ID
BATCH_SUMMARY_ID = support.BATCH_SUMMARY_ID
BATCH_SUMMARY_IDS = support.BATCH_SUMMARY_IDS
BOB = support.BOB
BRANCH = support.BRANCH
CAROL = support.CAROL
CHANGES_REQUESTED = support.CHANGES_REQUESTED
CHECK_SUCCESS = support.CHECK_SUCCESS
COMMAND_COMMENT_ID = support.COMMAND_COMMENT_ID
CONTINUE_COMMAND = support.CONTINUE_COMMAND
DAVE = support.DAVE
DEV_AGENT = support.DEV_AGENT
DEV_SESSION_ID = support.DEV_SESSION_ID
FIXING = support.FIXING
FRESH_SESSION = support.FRESH_SESSION
FakeComment = support.FakeComment
FakeGitHubClient = support.FakeGitHubClient
FakePR = support.FakePR
FakePRRef = support.FakePRRef
FakePRReview = support.FakePRReview
FakeUser = support.FakeUser
ISSUE = support.ISSUE
IN_REVIEW_LABEL = support.IN_REVIEW_LABEL
NO_PRESERVED_MESSAGE = support.NO_PRESERVED_MESSAGE
ORCHESTRATOR = support.ORCHESTRATOR
PARK_AGENT_SILENT = support.PARK_AGENT_SILENT
PARK_AGENT_TIMEOUT = support.PARK_AGENT_TIMEOUT
PARK_REASON = support.PARK_REASON
PENDING_FIX_AT = support.PENDING_FIX_AT
PENDING_FIX_ISSUE_IDS = support.PENDING_FIX_ISSUE_IDS
PENDING_FIX_ISSUE_MAX_ID = support.PENDING_FIX_ISSUE_MAX_ID
PENDING_FIX_REVIEWER_COMMENT_ID = support.PENDING_FIX_REVIEWER_COMMENT_ID
PENDING_FIX_REVIEW_IDS = support.PENDING_FIX_REVIEW_IDS
PENDING_FIX_REVIEW_MAX_ID = support.PENDING_FIX_REVIEW_MAX_ID
PENDING_FIX_REVIEW_SUMMARY_IDS = support.PENDING_FIX_REVIEW_SUMMARY_IDS
PENDING_FIX_REVIEW_SUMMARY_MAX_ID = support.PENDING_FIX_REVIEW_SUMMARY_MAX_ID
POISONED_SESSION = support.POISONED_SESSION
PRESERVED_BATCH_BODIES = support.PRESERVED_BATCH_BODIES
PR_HEAD_SHA = support.PR_HEAD_SHA
PR_LAST_COMMENT_ID = support.PR_LAST_COMMENT_ID
PR_LAST_REVIEW_COMMENT_ID = support.PR_LAST_REVIEW_COMMENT_ID
PR_LAST_REVIEW_SUMMARY_ID = support.PR_LAST_REVIEW_SUMMARY_ID
PR_NUMBER = support.PR_NUMBER
PUSHED_FIX_MESSAGE = support.PUSHED_FIX_MESSAGE
RESUME_SESSION_ID = support.RESUME_SESSION_ID
REVIEW_ROUND = support.REVIEW_ROUND
RUN_AGENT = support.RUN_AGENT
SHA_AFTER = support.SHA_AFTER
SHA_BEFORE = support.SHA_BEFORE
SHA_SAME = support.SHA_SAME
VALIDATING = support.VALIDATING
_ContinueSeed = support._ContinueSeed
_PatchedWorkflowMixin = support._PatchedWorkflowMixin
_agent = support._agent
dev_task_section = support.dev_task_section
make_issue = support.make_issue
posted_comment_contains = support.posted_comment_contains


class _ContinueCommandFixtureMixin(_PatchedWorkflowMixin):
    """`/orchestrator continue` retries a `fixing` park caused by a
    session-limit / session-failure reason (`agent_silent` / `agent_timeout`).
    On the in_review route it replays the PRESERVED review-feedback batch on a
    FRESH dev session rather than resuming on the command text -- the
    geserdugarov/lance-open-source#23 shape where a generic continue lost the
    latest review feedback. On the validating route (no replayable batch) and
    for parks that still need real human guidance, it is refused rather than
    resumed on the command text. A comment mixing guidance with the command
    line is left as ordinary feedback so its guidance is never dropped.
    """

    def _seed_parked_with_batch(
        self,
        seed: _ContinueSeed,
    ):
        # Batch feedback spans all three surfaces and sits BELOW the advanced
        # watermarks -- the shape after a poisoned/timed-out resume already
        # advanced past it. `_reconstruct_pending_fix_batch` re-fetches it
        # from the preserved `pending_fix_*_ids`. The `/orchestrator continue`
        # comment sits ABOVE the issue watermark so the per-tick rescan
        # surfaces it as fresh feedback. `pending_fix_at=None` +
        # `with_batch_ids=False` models a validating-route park (no batch).
        issue = make_issue(ISSUE, label=FIXING)
        issue.comments.append(
            FakeComment(
                id=BATCH_ISSUE_ID,
                body="fix the null check",
                user=FakeUser(CAROL),
            ),
        )
        command = FakeComment(
            id=seed.command_id,
            body=seed.command_body,
            user=FakeUser(DAVE),
        )
        if not seed.command_on_pr_conversation:
            issue.comments.append(command)
        for comment in seed.extra_issue_comments:
            issue.comments.append(comment)
        pr_conv = [
            FakeComment(
                id=BATCH_PR_CONVERSATION_ID,
                body="handle the edge case",
                user=FakeUser(ALICE),
            ),
        ]
        if seed.command_on_pr_conversation:
            pr_conv.append(command)
        self._pr = FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=PR_HEAD_SHA),
            mergeable=True,
            check_state=CHECK_SUCCESS,
            issue_comments=pr_conv,
            review_comments=[
                FakeComment(
                    id=BATCH_INLINE_ID,
                    body="rename the temp var",
                    user=FakeUser(BOB),
                ),
            ],
            reviews=[
                FakePRReview(
                    id=BATCH_SUMMARY_ID,
                    body="please address the review",
                    state=CHANGES_REQUESTED,
                ),
            ],
        )
        gh = FakeGitHubClient()
        gh.add_issue(issue)
        gh.add_pr(self._pr)
        self._state = {
            "pr_number": PR_NUMBER,
            "branch": BRANCH,
            "dev_agent": DEV_AGENT,
            DEV_SESSION_ID: POISONED_SESSION,
            REVIEW_ROUND: 1,
            AWAITING_HUMAN: True,
            PARK_REASON: seed.park_reason,
            "silent_park_count": seed.silent_park_count,
            # Watermarks advanced PAST the batch.
            PR_LAST_COMMENT_ID: ADVANCED_PR_COMMENT_WATERMARK,
            PR_LAST_REVIEW_COMMENT_ID: ADVANCED_REVIEW_COMMENT_WATERMARK,
            PR_LAST_REVIEW_SUMMARY_ID: ADVANCED_REVIEW_SUMMARY_WATERMARK,
        }
        if seed.pending_fix_at is not None:
            self._state[PENDING_FIX_AT] = seed.pending_fix_at
        if seed.with_batch_ids:
            self._state.update(
                {
                    PENDING_FIX_ISSUE_IDS: list(BATCH_ISSUE_IDS),
                    PENDING_FIX_ISSUE_MAX_ID: BATCH_PR_CONVERSATION_ID,
                    PENDING_FIX_REVIEW_IDS: [BATCH_INLINE_ID],
                    PENDING_FIX_REVIEW_MAX_ID: BATCH_INLINE_ID,
                    PENDING_FIX_REVIEW_SUMMARY_IDS: list(BATCH_SUMMARY_IDS),
                    PENDING_FIX_REVIEW_SUMMARY_MAX_ID: BATCH_SUMMARY_ID,
                }
            )
        gh.seed_state(ISSUE, **self._state)
        return gh, issue, self._pr


class _ValidatingContinueFixtureMixin(_ContinueCommandFixtureMixin):
    def _seed_validating_route_anchored_park(
        self,
        *,
        park_reason,
        reviewer_id: int = BATCH_PR_CONVERSATION_ID,
        command_id: int = COMMAND_COMMENT_ID,
    ):
        # #742 shape: a validating-route session-failure park (no
        # `pending_fix_at`, no `pending_fix_*_ids`) whose LONE replay anchor is
        # the reviewer-feedback PR comment recorded in
        # `pending_fix_reviewer_comment_id`. The reviewer comment is
        # orchestrator-authored, carries the hidden marker, and sits BELOW the
        # advanced watermark (so the per-tick rescan drops it) -- only the
        # anchor id re-surfaces it for the replay. A bare `/orchestrator
        # continue` sits ABOVE the watermark so the rescan sees it.
        issue = make_issue(ISSUE, label=FIXING)
        issue.comments.append(
            FakeComment(
                id=command_id,
                body=CONTINUE_COMMAND,
                user=FakeUser(DAVE),
            ),
        )
        reviewer = FakeComment(
            id=reviewer_id,
            body=(
                ":eyes: codex review (round 3/5) requested changes:\n\n"
                "please fix the last-frame-wins docstring\n\n"
                "<!--orchestrator-comment-->"
            ),
            user=FakeUser(ORCHESTRATOR),
        )
        pr = FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=PR_HEAD_SHA),
            mergeable=True,
            check_state=CHECK_SUCCESS,
            issue_comments=[reviewer],
        )
        gh = FakeGitHubClient()
        gh.add_issue(issue)
        gh.add_pr(pr)
        gh.seed_state(
            ISSUE,
            **{
                "pr_number": PR_NUMBER,
                "branch": BRANCH,
                "dev_agent": DEV_AGENT,
                DEV_SESSION_ID: POISONED_SESSION,
                REVIEW_ROUND: 2,
                AWAITING_HUMAN: True,
                PARK_REASON: park_reason,
                "silent_park_count": 2,
                PR_LAST_COMMENT_ID: ADVANCED_PR_COMMENT_WATERMARK,
                PR_LAST_REVIEW_COMMENT_ID: ADVANCED_REVIEW_COMMENT_WATERMARK,
                PR_LAST_REVIEW_SUMMARY_ID: ADVANCED_REVIEW_SUMMARY_WATERMARK,
                PENDING_FIX_REVIEWER_COMMENT_ID: reviewer_id,
                # No `pending_fix_at`, no `pending_fix_*_ids` -> validating route.
            },
        )
        return gh, issue, pr


def _reviewer_feedback(github):
    """The reviewer's CHANGES_REQUESTED comment, as the anchor re-fetches it."""
    return next(
        posted for posted in github.get_pr(PR_NUMBER).issue_comments
        if posted.id == BATCH_PR_CONVERSATION_ID
    )


def _assert_validating_retry_prompt(test_case) -> None:
    test_case.assertIsNone(
        test_case._call.kwargs.get(RESUME_SESSION_ID),
    )
    test_case.assertIn(
        "please fix the last-frame-wins docstring",
        test_case._call.args[1],
    )
    # The reviewer anchor is what the dev is asked to act on; the bare command
    # that asked for the retry is not, or the task would read as "implement
    # /orchestrator continue".
    test_case.assertNotIn(
        CONTINUE_COMMAND, dev_task_section(test_case._call.args[1]),
    )


def _assert_validating_retry_outcome(test_case, github) -> None:
    _assert_validating_retry_prompt(test_case)
    test_case.assertFalse(
        posted_comment_contains(github, NO_PRESERVED_MESSAGE),
    )
    test_case._pinned_data = github.pinned_data(ISSUE)
    test_case.assertEqual(
        test_case._pinned_data.get(DEV_SESSION_ID),
        FRESH_SESSION,
    )
    test_case.assertIn((ISSUE, VALIDATING), github.label_history)
    test_case.assertFalse(
        test_case._pinned_data.get(AWAITING_HUMAN),
    )
    test_case.assertIsNone(
        test_case._pinned_data.get(PARK_REASON),
    )
    test_case.assertEqual(
        test_case._pinned_data.get(REVIEW_ROUND),
        3,
    )
    test_case.assertIsNone(
        test_case._pinned_data.get(
            PENDING_FIX_REVIEWER_COMMENT_ID,
        ),
    )
    # Kept out of the task, still consumed: the watermark advances past the
    # command comment so it does not re-fire next tick.
    test_case.assertGreaterEqual(
        test_case._pinned_data.get(PR_LAST_COMMENT_ID),
        COMMAND_COMMENT_ID,
    )


class ValidatingContinueCommandTest(
    unittest.TestCase,
    _ValidatingContinueFixtureMixin,
):
    def test_validating_anchor_replays_feedback(self) -> None:
        # #742: a validating-route park after a session limit, with the reviewer
        # feedback anchored in `pending_fix_reviewer_comment_id`. A bare
        # `/orchestrator continue` must REPLAY that reviewer feedback on a fresh
        # session -- not refuse with "no preserved PR-feedback batch".
        for reason in (PARK_AGENT_SILENT, PARK_AGENT_TIMEOUT):
            with self.subTest(reason=reason):
                gh, issue, _pr = self._seed_validating_route_anchored_park(
                    park_reason=reason,
                )

                self._mocks = self._run_fixing(
                    gh,
                    issue,
                    run_agent=_agent(
                        session_id=FRESH_SESSION,
                        last_message=PUSHED_FIX_MESSAGE,
                    ),
                    head_shas=(SHA_BEFORE, SHA_AFTER),
                )

                # Dev invoked once; the poisoned session is dropped so the
                # retry is a FRESH spawn (no resume id) grounded on the branch.
                self._mocks[RUN_AGENT].assert_called_once()
                self._call = self._mocks[RUN_AGENT].call_args
                _assert_validating_retry_outcome(self, gh)

    def test_an_ack_does_not_answer_the_review(self) -> None:
        # The automated reviewer asked for a concrete change, so the developer
        # saying there is nothing to do is not an answer to it. The in_review
        # route's `ACK:` fast path is not offered here: the round parks for a
        # human with its replay anchor intact rather than returning the pull
        # request to review as ready.
        github, issue, _pr = self._seed_validating_route_anchored_park(
            park_reason=PARK_AGENT_TIMEOUT,
        )

        mocks = self._run_fixing(
            github,
            issue,
            run_agent=_agent(
                session_id=FRESH_SESSION,
                last_message="ACK: the branch already does this",
            ),
            head_shas=(SHA_SAME, SHA_SAME),
        )

        # The replay hands the developer the reviewer's own CHANGES_REQUESTED
        # feedback, entire and alone -- the real automated request, re-fetched
        # by the anchor the validating route recorded for it, and never the
        # bare command that asked for the retry.
        self.assertEqual(
            replayed_task(only_prompt(mocks)),
            pr_feedback_prompt([_reviewer_feedback(github)]),
        )
        pinned_data = github.pinned_data(ISSUE)
        self.assertNotIn((ISSUE, IN_REVIEW_LABEL), github.label_history)
        self.assertTrue(pinned_data.get(AWAITING_HUMAN))
        self.assertEqual(
            pinned_data.get(PENDING_FIX_REVIEWER_COMMENT_ID),
            BATCH_PR_CONVERSATION_ID,
        )

    def test_command_with_guidance_is_not_swallowed(self) -> None:
        # A PR-conversation comment mixing real guidance with a
        # `/orchestrator continue` line IS the command (exact-line match), so
        # on an eligible in_review park it REPLAYS the preserved batch on a
        # fresh session -- and carries the accompanying guidance verbatim
        # (reaching the dev directly, not just via the fresh-spawn preamble
        # that omits PR-conversation comments), so nothing is dropped.
        gh, issue, _pr = self._seed_parked_with_batch(
            _ContinueSeed(
                park_reason=PARK_AGENT_SILENT,
                command_body=("please handle the PR conv case\n/orchestrator continue"),
                command_on_pr_conversation=True,
            ),
        )

        self._mocks = self._run_fixing(
            gh,
            issue,
            run_agent=_agent(
                session_id=FRESH_SESSION,
                last_message=PUSHED_FIX_MESSAGE,
            ),
            head_shas=(SHA_BEFORE, SHA_AFTER),
        )

        self._mocks[RUN_AGENT].assert_called_once()
        self._agent_call = self._mocks[RUN_AGENT].call_args
        self._prompt = self._agent_call.args[1]
        # The accompanying guidance is NOT dropped ...
        self.assertIn("please handle the PR conv case", self._prompt)
        # ... AND the preserved batch is replayed (the issue requirement the
        # bare-continue path would have missed).
        for batch_body in PRESERVED_BATCH_BODIES:
            self.assertIn(batch_body, self._prompt)
        # Replayed on a fresh session (poisoned one dropped), no refusal note.
        self.assertIsNone(
            self._agent_call.kwargs.get(RESUME_SESSION_ID),
        )
        self.assertFalse(
            any(
                NO_PRESERVED_MESSAGE in comment_body or "needs your" in comment_body
                for _, comment_body in gh.posted_comments
            )
        )
