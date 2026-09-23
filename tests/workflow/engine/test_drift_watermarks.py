# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Workflow drift comment-watermark tests."""
from __future__ import annotations

import unittest

from orchestrator.workflow.engine import (
    content_hash as _content_hash,
    drift as _engine_drift,
    drift_delivery as _drift_delivery,
    prompt_context as _prompt_context,
)
from orchestrator.workflow.stages.conflicts import handler as _conflicts
from orchestrator.workflow.stages.implementing import handler as _implementing
from orchestrator.workflow.stages.in_review import handler as _in_review
from orchestrator.workflow.stages.validating import handler as _validating
from tests.workflow.engine import drift_test_support as support


class DriftMarksCommentsConsumedTest(
    unittest.TestCase, support._PatchedWorkflowMixin,
):
    """What a drift road leaves on `last_action_comment_id`, road by road.

    All four feed the dev session the issue thread, so none of them may
    leave a comment the developer read unrecorded: the next
    validating->in_review handoff's `_seed_watermark_past_self` would stop
    at that comment and replay it as fresh PR feedback, buying a duplicate
    dev resume.

    How far each goes is the same question on all four, and the answer is
    what each prompt carried: every one records the frozen snapshot it was
    built from, which is why the cases below ask only that the mark reached
    the comment that was delivered. What the excerpt bound dropped, and what
    landed after the freeze, are deliberately left unread (the
    `DriftResumeDeliveryTest` cases below)."""

    def test_validating_bumps_past_human_comment(
        self,
    ) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._VALIDATING_WATERMARK_ISSUE_NUMBER,
            label=support.LABEL_VALIDATING,
            body=support.NEW_BODY,
        )
        # Pre-existing human comment with a high id -- representing the
        # comment that arrived at the same time as the body edit.
        human = support.FakeComment(
            id=support._VALIDATING_WATERMARK_COMMENT_ID,
            body="add this acceptance criterion",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        issue.comments.append(human)
        gh.add_issue(issue)
        pr = support.FakePR(
            number=support._VALIDATING_WATERMARK_PR_NUMBER,
            head_branch="orchestrator/chippingway__orchestrator/issue-900",
        )
        gh.add_pr(pr)
        gh.seed_state(
            support._VALIDATING_WATERMARK_ISSUE_NUMBER,
            pr_number=pr.number,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=support.STALE_HASH,
            review_round=1,
            branch="orchestrator/chippingway__orchestrator/issue-900",
            last_action_comment_id=100,
        )

        self._run(
            lambda: _validating._handle_validating(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(
                session_id=support.DEV_SESSION, last_message="fixed"
            ),
            has_new_commits=True,
            dirty_files=(),
            push_branch=True,
            head_shas=["before", support.SHA_AFTER],
        )

        state = gh.pinned_data(support._VALIDATING_WATERMARK_ISSUE_NUMBER)
        # last_action_comment_id advanced past the human comment so the
        # eventual handoff to in_review does not classify it as fresh
        # feedback.
        self.assertGreaterEqual(
            int(state.get(support.KEY_LAST_ACTION_COMMENT_ID)),
            support._VALIDATING_WATERMARK_COMMENT_ID,
        )

    def test_in_review_human_comment_routes_to_fixing(
        self,
    ) -> None:
        # Regression for the reviewer's bug: a fresh issue-thread human
        # comment used to trip `user_content_hash` (which covers comments
        # too) and the drift path would resume the dev + bounce to
        # `validating` instead of the contracted route to `fixing`. With
        # the in_review handler scanning fresh feedback BEFORE the drift
        # check, the issue-thread comment now routes to `fixing` and the
        # hash is recomputed so the drift path does not double-fire on the
        # same comment changes next tick.
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._IN_REVIEW_WATERMARK_ISSUE_NUMBER,
            label=support.LABEL_IN_REVIEW,
            body=support.NEW_BODY,
        )
        issue.comments.append(
            support.FakeComment(
                id=support._IN_REVIEW_WATERMARK_COMMENT_ID,
                body="please also handle X",
                user=support.FakeUser(support.TRUSTED_AUTHOR),
            ),
        )
        gh.add_issue(issue)
        pr = support.FakePR(
            number=support._IN_REVIEW_WATERMARK_PR_NUMBER,
            head_branch="orchestrator/chippingway__orchestrator/issue-910",
        )
        gh.add_pr(pr)
        gh.seed_state(
            support._IN_REVIEW_WATERMARK_ISSUE_NUMBER,
            pr_number=pr.number,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=support.STALE_HASH,
            pr_last_comment_id=0,
            pr_last_review_comment_id=0,
            pr_last_review_summary_id=0,
            branch="orchestrator/chippingway__orchestrator/issue-910",
            last_action_comment_id=100,
        )

        mocks = self._run(
            lambda: _in_review._handle_in_review(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(),
        )

        # No dev spawn, no bounce to `validating`: the fixing route owns
        # this signal.
        mocks["run_agent"].assert_not_called()
        self.assertEqual(
            (
                (
                    support._IN_REVIEW_WATERMARK_ISSUE_NUMBER,
                    "workflow:fixing",
                ) in gh.label_history,
                (
                    support._IN_REVIEW_WATERMARK_ISSUE_NUMBER,
                    support.LABEL_VALIDATING,
                ) in gh.label_history,
            ),
            (True, False),
        )
        state = gh.pinned_data(support._IN_REVIEW_WATERMARK_ISSUE_NUMBER)
        # The triggering comment is bookmarked for the fixing handler.
        self.assertEqual(
            state.get("pending_fix_issue_max_id"),
            support._IN_REVIEW_WATERMARK_COMMENT_ID,
        )
        # Hash is updated so the drift check does not re-fire on the
        # same comment change after the fixing handler (or an operator
        # relabel) bounces the issue back to `in_review`.
        self.assertNotEqual(state.get(support.KEY_USER_CONTENT_HASH), support.STALE_HASH)
        # Watermark is deliberately left at the route-time value so the
        # fixing handler can read the triggering comment to build its
        # dev-resume prompt (the bookmark above tells it where to start).
        # The fixing handler advances this watermark itself once the
        # consumed feedback has been fed to the dev.
        self.assertEqual(state.get("pr_last_comment_id"), 0)

    def test_implementing_bumps_past_comment(
        self,
    ) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._IMPLEMENTING_WATERMARK_ISSUE_NUMBER,
            label=support.LABEL_IMPLEMENTING,
            body=support.NEW_BODY,
        )
        human = support.FakeComment(
            id=support._IMPLEMENTING_WATERMARK_COMMENT_ID,
            body="here are more requirements",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        issue.comments.append(human)
        gh.add_issue(issue)
        gh.seed_state(
            support._IMPLEMENTING_WATERMARK_ISSUE_NUMBER,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=support.STALE_HASH,
            awaiting_human=True,
            last_action_comment_id=100,
            branch="orchestrator/chippingway__orchestrator/issue-920",
        )

        self._run(
            lambda: _implementing._handle_implementing(gh, support._TEST_SPEC, issue),
            run_agent=support._agent(
                session_id=support.DEV_SESSION, last_message="implemented"
            ),
            has_new_commits=True,
            dirty_files=(),
            push_branch=True,
            head_shas=["before-resume", "after-resume"],
        )

        state = gh.pinned_data(support._IMPLEMENTING_WATERMARK_ISSUE_NUMBER)
        # The dev's commit goes through `_on_commits` which flips to
        # validating; the validating->in_review handoff later reads
        # last_action_comment_id, so we must have bumped past 7000.
        self.assertGreaterEqual(
            int(state.get(support.KEY_LAST_ACTION_COMMENT_ID)),
            support._IMPLEMENTING_WATERMARK_COMMENT_ID,
        )

    def test_conflict_drift_bumps_last_action(self) -> None:
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._CONFLICT_WATERMARK_ISSUE_NUMBER,
            label=support.LABEL_RESOLVING_CONFLICT,
            body=support.NEW_BODY,
        )
        human = support.FakeComment(
            id=support._CONFLICT_WATERMARK_COMMENT_ID,
            body="more context",
            user=support.FakeUser(support.TRUSTED_AUTHOR),
        )
        issue.comments.append(human)
        gh.add_issue(issue)
        pr = support.FakePR(
            number=support._CONFLICT_WATERMARK_PR_NUMBER,
            head_branch="orchestrator/chippingway__orchestrator/issue-930",
        )
        gh.add_pr(pr)
        gh.seed_state(
            support._CONFLICT_WATERMARK_ISSUE_NUMBER,
            pr_number=pr.number,
            dev_agent=support.BACKEND_CLAUDE,
            dev_session_id=support.DEV_SESSION,
            user_content_hash=support.STALE_HASH,
            conflict_round=0,
            branch="orchestrator/chippingway__orchestrator/issue-930",
            last_action_comment_id=100,
        )

        self._run(
            lambda: _conflicts._handle_resolving_conflict(
                gh, support._TEST_SPEC, issue,
            ),
            run_agent=support._agent(
                session_id=support.DEV_SESSION, last_message="resolved"
            ),
            has_new_commits=True,
            dirty_files=(),
            push_branch=True,
            head_shas=["before", support.SHA_AFTER, support.SHA_AFTER],
        )

        state = gh.pinned_data(support._CONFLICT_WATERMARK_ISSUE_NUMBER)
        # After the pushed resolution flips to validating, the
        # subsequent handoff back to in_review must not replay the human
        # comment that arrived during conflict resolution.
        self.assertGreaterEqual(
            int(state.get(support.KEY_LAST_ACTION_COMMENT_ID)),
            support._CONFLICT_WATERMARK_COMMENT_ID,
        )


class DriftResumeDeliveryTest(unittest.TestCase):
    """What one frozen drift prompt lets an issue record as answered.

    The prompt and the record come off one read, so these ask what that read
    leaves behind. An excerpt bound that stopped short consumes nothing below
    the context it dropped -- the comment stays unread for the road that
    delivers it -- while the requirements revision still covers the read as a
    whole, so a single edit does not re-open the same resume every poll. A
    reply written after the freeze is in neither the prompt nor the mark.
    """

    def test_the_prompt_and_the_record_are_one_read(self) -> None:
        gh, issue, state = self._thread((support._QUOTED_COMMENT_ID, support.QUOTED_EDIT))

        answered = _drift_delivery._drift_resume_prompt(gh, issue, state)

        self.assertIn(support.NEW_BODY, answered.text)
        self.assertIn(
            f"@{support.TRUSTED_AUTHOR}: {support.QUOTED_EDIT}", answered.text,
        )
        self.assertEqual(
            [entry.id for entry in answered.delivery.delivered_inputs()],
            [support._QUOTED_COMMENT_ID],
        )
        self.assertEqual(
            dict(answered.delivery.settle(state))[
                support.KEY_LAST_ACTION_COMMENT_ID
            ],
            support._QUOTED_COMMENT_ID,
        )

    def test_an_omitted_comment_is_not_consumed(self) -> None:
        # The bound is what decides the prompt, so it decides the mark too: the
        # comment the excerpt dropped holds the watermark below itself and is
        # still there for the scan that delivers it. The revision covers the
        # whole read regardless -- it is the baseline a later edit is compared
        # against, and stopped short of the drop it would re-run this resume,
        # on a prompt bounded exactly the same way, every poll.
        gh, issue, state = self._thread(
            (support._OMITTED_COMMENT_ID, support.OMITTED_CONTEXT),
            (support._QUOTED_COMMENT_ID, support.QUOTED_EDIT),
        )

        delivery = _prompt_context._delivered_thread(
            gh, issue, state, support._JUST_THE_TAIL,
        )
        settled = dict(delivery.settle(state))

        self.assertNotIn(support.OMITTED_CONTEXT, delivery.rendered_text)
        self.assertIn(support.QUOTED_EDIT, delivery.rendered_text)
        self.assertNotIn(support.KEY_LAST_ACTION_COMMENT_ID, settled)
        self.assertEqual(
            state.get(support.KEY_LAST_ACTION_COMMENT_ID), support._DELIVERY_FLOOR,
        )
        self.assertEqual(
            state.get(support.KEY_USER_CONTENT_HASH),
            _content_hash._compute_user_content_hash(issue, set()),
        )

    def test_a_later_reply_is_still_an_edit(self) -> None:
        # The minutes an agent is out for. Nothing re-reads the thread to
        # settle it, so the reply is unquoted, uncrossed, and still drift on
        # the poll that follows.
        gh, issue, state = self._thread((support._QUOTED_COMMENT_ID, support.QUOTED_EDIT))
        answered = _drift_delivery._drift_resume_prompt(gh, issue, state)
        issue.comments.append(
            support.FakeComment(
                id=support._LATER_COMMENT_ID,
                body=support.LANDED_MID_RUN,
                user=support.FakeUser(support.TRUSTED_AUTHOR),
            ),
        )

        answered.delivery.settle(state)

        self.assertNotIn(support.LANDED_MID_RUN, answered.text)
        self.assertEqual(
            state.get(support.KEY_LAST_ACTION_COMMENT_ID),
            support._QUOTED_COMMENT_ID,
        )
        self.assertIsNotNone(
            _engine_drift._detect_user_content_change(gh, issue, state),
        )

    def _thread(self, *replies: tuple[int, str]):
        """A `workflow:implementing` issue whose park had read up to the floor."""
        gh = support.FakeGitHubClient()
        issue = support.make_issue(
            support._DELIVERY_ISSUE_NUMBER,
            label=support.LABEL_IMPLEMENTING,
            body=support.NEW_BODY,
            comments=[
                support.FakeComment(
                    id=identified,
                    body=said,
                    user=support.FakeUser(support.TRUSTED_AUTHOR),
                )
                for identified, said in replies
            ],
        )
        gh.add_issue(issue)
        gh.seed_state(
            issue,
            user_content_hash=support.STALE_HASH,
            last_action_comment_id=support._DELIVERY_FLOOR,
        )
        return gh, issue, gh.read_pinned_state(issue)
