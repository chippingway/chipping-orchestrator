# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Workflow drift routing and acknowledgement tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from orchestrator.config import settings as config
from orchestrator.workflow.engine import comments, drift, pickup as _pickup
from orchestrator.workflow.stages.decomposition import blocked as _blocked
from orchestrator.workflow.stages.in_review import handler as _in_review
from orchestrator.workflow.stages.validating import handler as _validating
from tests.workflow.engine import drift_test_support as support


class HandlePickupInitializesUserContentHashTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    def test_pickup_with_decompose_off_seeds_hash(self) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(1)
        gh.add_issue(issue)

        with patch.object(config, "DECOMPOSE", False):
            self._run(
                lambda: _pickup._handle_pickup(gh, support._TEST_SPEC, issue),
                run_agent=support._agent(last_message="q"),
                has_new_commits=False,
            )

        state = gh.pinned_data(1)
        self.assertIn(support.KEY_USER_CONTENT_HASH, state)
        # Hash filters the pickup comment by id (it has been recorded in
        # `orchestrator_comment_ids`), so it should match a re-computation
        # over the same set.
        orch_ids = set(state.get("orchestrator_comment_ids") or [])
        self.assertEqual(
            state[support.KEY_USER_CONTENT_HASH],
            drift._compute_user_content_hash(issue, orch_ids),
        )

    def test_pickup_with_decompose_on_seeds_hash(self) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(2)
        gh.add_issue(issue)

        with patch.object(config, "DECOMPOSE", True):
            self._run(
                lambda: _pickup._handle_pickup(gh, support._TEST_SPEC, issue),
                run_agent=support._agent(
                    session_id="dec-sess",
                    last_message=(
                        "fits one\n\n```orchestrator-manifest\n"
                        '{"decision": "single", "rationale": "small"}\n'
                        "```"
                    ),
                ),
            )

        state = gh.pinned_data(2)
        self.assertIn(support.KEY_USER_CONTENT_HASH, state)


class UserContentChangePromptIncludesCommentsTest(unittest.TestCase):
    """A drift triggered by a NEW human comment (not a body edit) must
    surface that comment to the dev. Quoting only title/body would leave
    the dev unaware of the acceptance criterion the human just posted."""

    def test_recent_comments_quoted_in_resume_prompt(self) -> None:
        issue = support.make_issue(1, title="t", body="b")
        issue.comments.append(support.FakeComment(
            id=support._PROMPT_COMMENT_ID,
            body="new acceptance criterion: handle empty input",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        ))
        comments_text = comments._recent_comments_text(issue)
        prompt = drift._build_user_content_change_prompt(
            issue, comments_text,
        )
        self.assertIn("new acceptance criterion", prompt)
        self.assertIn("Conversation so far", prompt)
        self.assertIn("Updated issue body", prompt)


class FirstTimeHashSeedingIsDurableTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    """Reviewer point 3: `_detect_user_content_change` must persist the
    first-time baseline via `gh.write_pinned_state` immediately, so a
    later edit after a parked/idle tick is not silently absorbed as the
    new baseline."""

    def test_validating_no_reply_persists_baseline(
        self,
    ) -> None:
        # Legacy state (no `user_content_hash`) parked on awaiting_human
        # with no new comments. `_handle_validating`'s awaiting-human
        # path returns without writing state on a real no-reply tick;
        # the durability fix in `_detect_user_content_change` must still
        # have written the baseline by then.
        gh = support.FakeGitHubClient()
        issue = support.make_issue(100, label=support.LABEL_VALIDATING, body="initial body")
        gh.add_issue(issue)
        pr = support.FakePR(number=1000, head_branch="orchestrator/chippingway__orchestrator/issue-100")
        gh.add_pr(pr)
        gh.seed_state(
            100,
            pr_number=pr.number,
            awaiting_human=True,
            last_action_comment_id=support._INITIAL_LAST_ACTION_COMMENT_ID,
            review_round=1,
        )

        # Tick: no new comments and no hash baseline. Park branch
        # returns early without writing state.
        self._run(
            lambda: _validating._handle_validating(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(),
        )

        # Baseline durably persisted by the first-call branch in
        # `_detect_user_content_change`.
        state = gh.pinned_data(100)
        self.assertIsNotNone(state.get(support.KEY_USER_CONTENT_HASH))

    def test_blocked_child_no_op_persists_baseline(self) -> None:
        # A `blocked` child waiting on a sibling is a per-tick no-op.
        # Without the durability fix, a later edit during the wait would
        # silently become the new baseline because the no-op branch
        # returns without `write_pinned_state`.
        gh = support.FakeGitHubClient()
        child = support.make_issue(
            support._BLOCKED_CHILD_ISSUE_NUMBER,
            label=support.LABEL_BLOCKED,
            body="child body",
        )
        gh.add_issue(child)
        gh.seed_state(
            support._BLOCKED_CHILD_ISSUE_NUMBER,
            parent_number=support._BLOCKED_PARENT_ISSUE_NUMBER,
        )

        self._run(
            lambda: _blocked._handle_blocked(gh, support._TEST_SPEC, child),
            run_agent=support._agent(),
        )

        state = gh.pinned_data(support._BLOCKED_CHILD_ISSUE_NUMBER)
        self.assertIsNotNone(state.get(support.KEY_USER_CONTENT_HASH))


class BareAddAgentRunsIsNotDriftTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    """The command that buys an issue more agent runs is a control, not an edit.

    The dispatcher answers it and hands the SAME tick to the stage below, so a
    hash that counted the command would meet the handler as a body edit
    nobody made: `validating` would resume the developer on "the human edited
    the issue" instead of running the reviewer round the issue was stopped
    mid-way through.
    """

    def test_validating_runs_the_reviewer_not_the_dev(self) -> None:
        gh, issue = self._parked_and_bought()

        mocks = self._run(
            lambda: _validating._handle_validating(
                gh, support._TEST_SPEC, issue,
            ),
            run_agent=support._agent(
                last_message=support.REVIEW_APPROVED_MESSAGE,
            ),
        )

        prompt = mocks[support.RUN_AGENT].call_args.args[1]
        self.assertNotIn("The human edited the issue", prompt)
        # An approved round routes on for the docs pass, which is the whole
        # proof that the reviewer -- and not the drift resume -- ran.
        self.assertIn(
            (support._ADD_AGENT_RUNS_ISSUE_NUMBER, support.LABEL_DOCUMENTING),
            gh.label_history,
        )

    def test_guidance_beside_the_command_still_drifts(self) -> None:
        # Words beside the command are requirements, and the drift road is how
        # they reach the agent that has to act on them.
        gh, issue = self._parked_and_bought(
            guidance="also handle the empty input case",
        )

        mocks = self._run(
            lambda: _validating._handle_validating(
                gh, support._TEST_SPEC, issue,
            ),
            run_agent=support._agent(
                session_id=support.DEV_SESSION,
                last_message="ACK: covered already",
            ),
            has_new_commits=False,
            dirty_files=(),
            head_shas=[support.SAME_SHA, support.SAME_SHA],
        )

        prompt = mocks[support.RUN_AGENT].call_args.args[1]
        self.assertIn("The human edited the issue", prompt)

    def _parked_and_bought(self, *, guidance: str = ""):
        """A validating issue whose thread carries the operator's command.

        The baseline is the hash of the thread WITHOUT it, which is what the
        stage recorded before the park: the command is written while the issue
        is stopped, and the tick that reads it is the one the handler runs on.
        """
        issue_number = support._ADD_AGENT_RUNS_ISSUE_NUMBER
        issue = support.make_issue(
            issue_number, label=support.LABEL_VALIDATING,
        )
        baseline = drift._compute_user_content_hash(issue, set())
        issue.comments.append(support.FakeComment(
            id=support._ADD_AGENT_RUNS_COMMENT_ID,
            body="\n\n".join(
                part for part in (support.ADD_AGENT_RUNS_COMMAND, guidance)
                if part
            ),
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        ))
        branch = f"orchestrator/chippingway__orchestrator/issue-{issue_number}"
        gh = support.FakeGitHubClient()
        gh.add_issue(issue)
        gh.add_pr(support.FakePR(
            number=support._ADD_AGENT_RUNS_PR_NUMBER, head_branch=branch,
        ))
        gh.seed_state(
            issue_number,
            pr_number=support._ADD_AGENT_RUNS_PR_NUMBER,
            branch=branch,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=baseline,
            agent_run_allowance=support._ADD_AGENT_RUNS_ALLOWANCE,
            agent_runs_used=support._ADD_AGENT_RUNS_SPENT,
            review_round=1,
        )
        return gh, issue


class NoCommitAckDoesNotParkTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    """Reviewer point 4: a harmless clarification edit can elicit a
    no-commit reply from the dev ('existing work satisfies'). The
    validating / in_review / resolving_conflict drift paths must treat
    that as an ack rather than parking awaiting_human."""

    def test_validating_ack_does_not_park(self) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._VALIDATING_ACK_ISSUE_NUMBER,
            label=support.LABEL_VALIDATING,
            body=support.CLARIFIED_BODY,
        )
        gh.add_issue(issue)
        pr = support.FakePR(
            number=support._VALIDATING_ACK_PR_NUMBER,
            head_branch="orchestrator/chippingway__orchestrator/issue-600",
        )
        gh.add_pr(pr)
        gh.seed_state(
            support._VALIDATING_ACK_ISSUE_NUMBER,
            pr_number=pr.number,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=support.STALE_HASH,
            review_round=1,
            branch="orchestrator/chippingway__orchestrator/issue-600",
        )

        self._run(
            lambda: _validating._handle_validating(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(
                session_id=support.DEV_SESSION,
                last_message=(
                    "Reviewed the clarified body.\n\n"
                    "ACK: existing commits already cover the clarified body"
                ),
            ),
            has_new_commits=False,
            dirty_files=(),
            head_shas=[support.SAME_SHA, support.SAME_SHA],
        )

        state = gh.pinned_data(support._VALIDATING_ACK_ISSUE_NUMBER)
        # Crucial: must NOT park as a question.
        self.assertFalse(state.get(support.KEY_AWAITING_HUMAN))
        # Dev's ACK justification was posted on the issue as an FYI.
        self.assertTrue(any(
            support.EXISTING_WORK_MESSAGE in body
            for _, body in gh.posted_comments
        ))

    def test_in_review_ack_routes_to_validating(
        self,
    ) -> None:
        # A no-commit "ack" reply from the dev on an in_review drift
        # MUST bounce DIRECTLY back to `validating` (same destination
        # as the pushed-fix exit; docs do not run on the drift exit,
        # the single docs pass runs after reviewer approval before
        # `in_review` via the final-docs handoff). `review_round`
        # resets so the validating cap counts fresh rounds.
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._IN_REVIEW_ACK_ISSUE_NUMBER,
            label=support.LABEL_IN_REVIEW,
            body=support.CLARIFIED_BODY,
        )
        gh.add_issue(issue)
        pr = support.FakePR(
            number=support._IN_REVIEW_ACK_PR_NUMBER,
            head_branch="orchestrator/chippingway__orchestrator/issue-700",
        )
        gh.add_pr(pr)
        gh.seed_state(
            support._IN_REVIEW_ACK_ISSUE_NUMBER,
            pr_number=pr.number,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=support.STALE_HASH,
            pr_last_comment_id=0,
            pr_last_review_comment_id=0,
            pr_last_review_summary_id=0,
            branch="orchestrator/chippingway__orchestrator/issue-700",
        )

        self._run(
            lambda: _in_review._handle_in_review(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(
                session_id=support.DEV_SESSION,
                last_message="ACK: no additional code change needed",
            ),
            has_new_commits=False,
            dirty_files=(),
            head_shas=[support.UNCHANGED_SHA, support.UNCHANGED_SHA],
        )

        state = gh.pinned_data(support._IN_REVIEW_ACK_ISSUE_NUMBER)
        # Must NOT park (the dev acknowledged, not asked a question).
        self.assertFalse(state.get(support.KEY_AWAITING_HUMAN))
        # MUST bounce directly to validating (no documenting hop) so
        # the reviewer re-evaluates against the updated body.
        self.assertIn(
            (support._IN_REVIEW_ACK_ISSUE_NUMBER, support.LABEL_VALIDATING),
            gh.label_history,
        )
        # And NOT through documenting -- no commit landed.
        self.assertNotIn(
            (support._IN_REVIEW_ACK_ISSUE_NUMBER, "workflow:documenting"),
            gh.label_history,
        )
        # review_round reset so the validating cap counts fresh rounds.
        self.assertEqual(state.get("review_round"), 0)
        # Dev's reply still posted on the issue as an FYI.
        self.assertTrue(any(
            support.EXISTING_WORK_MESSAGE in body
            for _, body in gh.posted_comments
        ))
