# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Tests for fixing validating continue behavior."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tests.workflow.agent_failure_values import (
    FIVE_HOUR_LIMIT_MESSAGE,
    FIVE_HOUR_LIMIT_QUESTION,
    WEEKLY_LIMIT_MESSAGE,
)
from tests.workflow.fixtures import EVENT_PARK_AWAITING_HUMAN, REVIEW_CHANGES_REQUESTED_MESSAGE
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
DEV_SESSION = support.DEV_SESSION
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
PARK_AGENT_EXECUTION_FAILED = support.PARK_AGENT_EXECUTION_FAILED
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
SESSION_LIMIT_PHRASE = support.SESSION_LIMIT_PHRASE
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

_DIRTY_FILE_NAME = "orchestrator/uncommitted_work.py"
_DIRTY_CONTENT = "# reviewer fix the quota stopped half way\n"
# A developer command pinned with arguments the configured one lacks, so a
# retry that ran on the configuration instead would be told apart.
_PINNED_DEV_SPEC = "claude --model claude-opus-4-7"
_PINNED_DEV_ARGS = ("--model", "claude-opus-4-7")
_DEV_AGENT_KEY = "dev_agent"
_SILENT_PARK_COUNT = "silent_park_count"
_AGENT_RUNS_USED = "agent_runs_used"
# The reviewer's run and the developer's the quota stopped.
_RUNS_BEFORE_RETRY = 2


class _ContinueCommandFixtureMixin(_PatchedWorkflowMixin):
    """`/orchestrator continue` retries a `fixing` park caused by a
    session-limit / session-failure reason (`agent_silent` / `agent_timeout` /
    `agent_execution_failed`).
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
        test_case._call.kwargs["options"].resume_session_id,
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
        for reason in (PARK_AGENT_SILENT, PARK_AGENT_TIMEOUT, PARK_AGENT_EXECUTION_FAILED):
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
            self._agent_call.kwargs["options"].resume_session_id,
        )
        self.assertFalse(
            any(
                NO_PRESERVED_MESSAGE in comment_body or "needs your" in comment_body
                for _, comment_body in gh.posted_comments
            )
        )


class ValidatingQuotaParkContinueTest(unittest.TestCase, _PatchedWorkflowMixin):
    """The developer handed a reviewer's change request stops on its
    account's quota (the weekly one of #1796, the five-hour one of #2426),
    leaving the fix half written in the checkout. That notice is the CLI's,
    not a question, so the round parks retryably with everything the retry
    needs kept, and a tick nobody answered launches nothing. The bare
    `/orchestrator continue` the park asks for, once the quota resets, replays
    the reviewer's request on a fresh session of the pinned command over that
    same checkout instead of being refused as an unanswered question. A real
    question that merely quotes the notice stays one the bare command cannot
    answer.
    """

    def test_quota_park_continue_replays(self) -> None:
        for notice in (WEEKLY_LIMIT_MESSAGE, FIVE_HOUR_LIMIT_MESSAGE):
            with self.subTest(notice=notice):
                # --- Tick 1: the reviewer asks for a change; the quota stops the dev.
                self._stop_the_developer(notice)
                reviewer = self._assert_retryable_quota_park(notice)

                # --- Tick 2: nobody has answered, so nothing is retried or said.
                parked = self._github.pinned_data(ISSUE)
                said = len(self._github.posted_comments)
                self._fixing_tick(command=False)[RUN_AGENT].assert_not_called()
                self.assertEqual(self._github.pinned_data(ISSUE), parked)
                self.assertEqual(len(self._github.posted_comments), said)

                # --- Tick 3: the bare command after the reset retries the round.
                self._assert_retry_taken(self._fixing_tick(command=True), reviewer)

    def test_question_quote_refuses_continue(self) -> None:
        self._stop_the_developer(FIVE_HOUR_LIMIT_QUESTION)
        self.assertEqual(self._park_events(), [("fixing", "agent_question")])
        self.assertIn("needs your input", self._github.posted_comments[-1][1])
        anchor = self._github.pinned_data(ISSUE).get(PENDING_FIX_REVIEWER_COMMENT_ID)
        self.assertIsNotNone(anchor)

        self._fixing_tick(command=True)[RUN_AGENT].assert_not_called()
        self.assertTrue(posted_comment_contains(self._github, "needs your actual guidance"))
        pinned_data = self._github.pinned_data(ISSUE)
        self.assertEqual(
            (
                pinned_data.get(AWAITING_HUMAN),
                pinned_data.get(PARK_REASON),
                pinned_data.get(_SILENT_PARK_COUNT),
                pinned_data.get(PENDING_FIX_REVIEWER_COMMENT_ID),
            ),
            (True, None, 0, anchor),
        )
        self.assertNotIn((ISSUE, VALIDATING), self._github.label_history)

    def _stop_the_developer(self, last_message: str) -> None:
        """Tick 1 on a `validating` issue: the reviewer requests changes, and
        the developer's run on them ends in `last_message` with no commit,
        its fix left half written in the checkout."""
        self._github = FakeGitHubClient()
        self._issue = make_issue(ISSUE, label=VALIDATING)
        self._github.add_issue(self._issue)
        self._github.add_pr(
            FakePR(
                number=PR_NUMBER,
                head_branch=BRANCH,
                head=FakePRRef(sha=PR_HEAD_SHA),
                mergeable=True,
                check_state=CHECK_SUCCESS,
            ),
        )
        self._github.seed_state(
            ISSUE,
            pr_number=PR_NUMBER,
            branch=BRANCH,
            dev_agent=_PINNED_DEV_SPEC,
            dev_session_id=DEV_SESSION,
            review_round=0,
        )
        self._worktree = Path(tempfile.mkdtemp(prefix="fixing-quota-wt-"))
        self.addCleanup(shutil.rmtree, self._worktree, ignore_errors=True)
        dirty_file = self._worktree / _DIRTY_FILE_NAME
        dirty_file.parent.mkdir(parents=True)
        dirty_file.write_text(_DIRTY_CONTENT)
        self._run_validating(
            self._github,
            self._issue,
            run_agent=[
                _agent(session_id="rev-sess", last_message=REVIEW_CHANGES_REQUESTED_MESSAGE),
                _agent(session_id=DEV_SESSION, last_message=last_message),
            ],
            head_shas=[SHA_BEFORE, SHA_BEFORE],
            dirty_files=[_DIRTY_FILE_NAME],
            issue_checkout=self._worktree,
            issue_worktree=self._worktree,
        )

    def _fixing_tick(self, *, command: bool):
        """One fixing tick over the parked round, after a trusted bare
        `/orchestrator continue` where `command` says one was posted."""
        if command:
            self._issue.comments.append(
                FakeComment(
                    id=max(comment.id for comment in self._issue.comments) + 1,
                    body=CONTINUE_COMMAND,
                    user=FakeUser(DAVE),
                ),
            )
        return self._run_fixing(
            self._github,
            self._issue,
            run_agent=_agent(session_id=FRESH_SESSION, last_message=PUSHED_FIX_MESSAGE),
            head_shas=(SHA_BEFORE, SHA_AFTER),
            issue_checkout=self._worktree,
            issue_worktree=self._worktree,
        )

    def _park_events(self) -> list[tuple]:
        return [
            (record.get("stage"), record.get("reason"))
            for record in self._github.recorded_events
            if record.get("event") == EVENT_PARK_AWAITING_HUMAN
        ]

    def _assert_retryable_quota_park(self, notice: str):
        """The park tick 1 leaves, and the reviewer comment it is anchored on."""
        self.assertEqual(self._park_events(), [("fixing", "agent_session_limit")])
        self.assertEqual(self._github.label_history, [(ISSUE, FIXING)])
        pinned_data = self._github.pinned_data(ISSUE)
        # `agent_silent` is the retryable reason the continue command keys
        # off, and the streak it advances is what rotates a session that
        # keeps stopping; the anchor, PR and branch are what the replay is
        # rebuilt from, and the pinned command what it runs on. Both runs
        # the round spent stay charged.
        self.assertEqual(
            (
                pinned_data.get(AWAITING_HUMAN),
                pinned_data.get(PARK_REASON),
                pinned_data.get(_SILENT_PARK_COUNT),
                pinned_data.get("pr_number"),
                pinned_data.get("branch"),
                pinned_data.get(_DEV_AGENT_KEY),
                pinned_data.get(_AGENT_RUNS_USED),
            ),
            (True, PARK_AGENT_SILENT, 1, PR_NUMBER, BRANCH, _PINNED_DEV_SPEC, _RUNS_BEFORE_RETRY),
        )
        notice_comment = self._github.posted_comments[-1][1]
        for expected in (SESSION_LIMIT_PHRASE, CONTINUE_COMMAND, f"> {notice}"):
            self.assertIn(expected, notice_comment)
        self.assertNotIn("needs your input", notice_comment)
        return next(
            posted for posted in self._github.get_pr(PR_NUMBER).issue_comments
            if posted.id == pinned_data.get(PENDING_FIX_REVIEWER_COMMENT_ID)
        )

    def _assert_retry_taken(self, mocks, reviewer) -> None:
        """Exactly the reviewer's request, on a fresh spawn of the developer's
        pinned command in the checkout still holding the unfinished fix,
        charged as one more run, and the fix back in review."""
        self.assertEqual(
            replayed_task(only_prompt(mocks)), pr_feedback_prompt([reviewer]),
        )
        agent_call = mocks[RUN_AGENT].call_args
        options = agent_call.kwargs["options"]
        self.assertEqual(
            (agent_call.args[0], options.extra_args, agent_call.args[2], options.resume_session_id),
            (DEV_AGENT, _PINNED_DEV_ARGS, self._worktree, None),
        )
        self.assertEqual((self._worktree / _DIRTY_FILE_NAME).read_text(), _DIRTY_CONTENT)
        self.assertFalse(posted_comment_contains(self._github, "needs your actual guidance"))
        pinned_data = self._github.pinned_data(ISSUE)
        self.assertEqual(
            (
                pinned_data.get(AWAITING_HUMAN),
                pinned_data.get(PARK_REASON),
                pinned_data.get(DEV_SESSION_ID),
                pinned_data.get(PENDING_FIX_REVIEWER_COMMENT_ID),
                pinned_data.get(_DEV_AGENT_KEY),
                pinned_data.get(_AGENT_RUNS_USED),
            ),
            (False, None, FRESH_SESSION, None, _PINNED_DEV_SPEC, _RUNS_BEFORE_RETRY + 1),
        )
        self.assertIn((ISSUE, VALIDATING), self._github.label_history)
