# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""One issue reply, delivered once, and a pull request nobody read it from.

`last_action_comment_id` is settled by the implementing and validating
awaiting-human resumes, and those watch the issue thread alone. So the
PR-feedback scans owe that field two different answers, and one watermark over
the shared IssueComment id space cannot give both: an issue-thread reply at or
below it has been in a developer prompt and may not route the issue back to
`fixing`, while a PR-conversation comment numbered below it was never in any
prompt and has to surface.

The first case crosses the stage that writes the field and the two that read
it, because neither end shows the defect alone -- validating settles a reply it
delivered, and only the scan a manual relabel hands the issue to decides
whether the same reply comes back as feedback. The rest pin the surfaces that
must stay deliverable across the cursor shapes a relabelled or legacy issue
arrives with.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from functools import partial
from unittest.mock import patch

from orchestrator import config
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    FakePRReview,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    DEFAULT_PR_HEAD_SHA,
    LABEL_FIXING,
    LABEL_IN_REVIEW,
    LABEL_VALIDATING,
    MEASURED_CANDIDATE_SHA,
    _agent,
    _PatchedWorkflowMixin,
)

ISSUE = 1843
PR_NUMBER = 4310
BRANCH = f"orchestrator/chippingway__orchestrator/issue-{ISSUE}"
# The head the pull request stands on when a round opens, and the one a dev
# resume leaves the checkout at.
HEAD_SHA = DEFAULT_PR_HEAD_SHA
FIXED_SHA = MEASURED_CANDIDATE_SHA

DEV_AGENT = "claude"
DEV_SESSION = "dev-sess"
HUMAN = "alice"
ORCHESTRATOR = "orchestrator"

# The park that opened the wait, the PR comment nobody has read yet, and the
# reply the developer answered -- numbered in the one IssueComment id space
# GitHub gives the issue thread and the PR conversation, so the unread PR
# comment sits BELOW the answered reply.
PARK_NOTICE_ID = 700
PR_CONVERSATION_ID = 710
ISSUE_REPLY_ID = 720
LATER_ISSUE_ID = 730
INLINE_REVIEW_ID = 40
REVIEW_SUMMARY_ID = 9

PARK_NOTICE_BODY = ":raising_hand: waiting on a human."
DELIVERED_REPLY = "please use sqlite for the cache"
PR_CONVERSATION_BODY = "the migration script needs a rollback path"
LATER_ISSUE_BODY = "and rename the helper to `cache_path`"
INLINE_REVIEW_BODY = "line 12: this branch is unreachable"
REVIEW_SUMMARY_BODY = "please tighten the error message"

RUN_AGENT = "run_agent"
DEBOUNCE_SETTING = "IN_REVIEW_DEBOUNCE_SECONDS"
DEBOUNCE_SECONDS = 600
PENDING_FIX_ISSUE_MAX_ID = "pending_fix_issue_max_id"
PENDING_FIX_REVIEW_MAX_ID = "pending_fix_review_max_id"
PENDING_FIX_REVIEW_SUMMARY_MAX_ID = "pending_fix_review_summary_max_id"
PR_LAST_COMMENT_ID = "pr_last_comment_id"
LAST_ACTION_COMMENT_ID = "last_action_comment_id"
CHANGES_REQUESTED = "CHANGES_REQUESTED"
# The legacy handoff value, and the manual relabel that never wrote one. Both
# leave the issue thread bounded by the delivery cursor alone.
LEGACY_WATERMARK_SHAPES = (None, 0)


def _settled() -> datetime:
    """A timestamp old enough that no quiet window is still waiting on it."""
    return datetime.now(UTC) - timedelta(hours=1)


def _comment(comment_id: int, body: str, *, author: str = HUMAN) -> FakeComment:
    """One settled comment, on whichever of the two surfaces it is put."""
    return FakeComment(
        id=comment_id,
        body=body,
        user=FakeUser(author),
        created_at=_settled(),
    )


class _ConsumptionFixtureMixin(_PatchedWorkflowMixin):
    """The issue a parked developer answered, on whichever stage reads it next."""

    def _seed(self, *, label, pr, issue_comments=(), **state_fields):
        gh = FakeGitHubClient()
        issue = make_issue(ISSUE, label=label, comments=[
            _comment(PARK_NOTICE_ID, PARK_NOTICE_BODY, author=ORCHESTRATOR),
            _comment(ISSUE_REPLY_ID, DELIVERED_REPLY),
            *issue_comments,
        ])
        gh.add_issue(issue)
        gh.add_pr(pr)
        gh.seed_state(
            ISSUE,
            pr_number=PR_NUMBER,
            branch=BRANCH,
            dev_agent=DEV_AGENT,
            dev_session_id=DEV_SESSION,
            review_round=1,
            orchestrator_comment_ids=[PARK_NOTICE_ID],
            **state_fields,
        )
        return gh, issue

    def _pr(self, **pr_fields):
        defaults = {
            "number": PR_NUMBER,
            "head_branch": BRANCH,
            "head": FakePRRef(sha=HEAD_SHA),
            "mergeable": True,
            "check_state": "success",
        }
        defaults.update(pr_fields)
        return FakePR(**defaults)

    def _seeded_watermark(self, watermark) -> dict:
        """The PR-side cursor a relabelled or legacy issue arrives carrying."""
        return {} if watermark is None else {PR_LAST_COMMENT_ID: watermark}

    def _state(self, gh) -> dict:
        """The pinned record the issue carries after a tick."""
        return gh.pinned_data(ISSUE)

    def _prompts(self, mocks) -> list[str]:
        """Every prompt string handed to an agent across one stage run."""
        return [call.args[1] for call in mocks[RUN_AGENT].call_args_list]

    def _run_dev_stage(self, label, gh, issue):
        """One tick of `label`'s handler, whose dev resume pushes a fix."""
        # The validating tick resumes the developer and reaches no reviewer,
        # so the pull request is left carrying no report: relabelled by hand,
        # the issue is one nothing has reported or approved over.
        runners = {
            LABEL_IN_REVIEW: self._run_in_review,
            LABEL_FIXING: self._run_fixing,
            LABEL_VALIDATING: partial(self._run_validating, reported=False),
        }
        with patch.object(config, DEBOUNCE_SETTING, DEBOUNCE_SECONDS):
            return runners[label](
                gh,
                issue,
                run_agent=_agent(session_id=DEV_SESSION, last_message="done"),
                has_new_commits=[True],
                dirty_files=(),
                push_branch=True,
                head_shas=[HEAD_SHA, FIXED_SHA],
            )


class DeliveredIssueReplyTest(unittest.TestCase, _ConsumptionFixtureMixin):
    """Validating answers the reply; the PR scans answer the pull request.

    The developer is resumed on the issue thread, which settles
    `last_action_comment_id` and leaves `pr_last_comment_id` unwritten. A human
    then moves the label by hand, so no approval handoff seeded a PR-side
    watermark -- and the scan that picks the issue up owes the reply nothing
    and the pull request everything.

    The two cases are the two shapes that relabel arrives in: a thread the
    delivery answered in full, which may cost no second run at all, and one
    with a PR comment numbered below that reply, which has to surface without
    the reply riding along.
    """

    def test_delivery_is_the_only_invocation(self) -> None:
        # Nothing on the pull request and nothing newer on the thread, so the
        # reply validating answered is the whole of what either scan can see.
        # A second run here is a developer paid to read its own answer.
        gh, issue, invocations = self._deliver_through_validating(
            unread_pr_comment=False,
        )

        for label in (LABEL_IN_REVIEW, LABEL_FIXING):
            gh.apply_foreign_label(issue, label)
            invocations += len(self._prompts(
                self._run_dev_stage(label, gh, issue),
            ))

        self.assertEqual(invocations, 1)
        self.assertNotIn((ISSUE, LABEL_FIXING), gh.label_history)
        self.assertIsNone(self._state(gh).get(PENDING_FIX_ISSUE_MAX_ID))

    def test_relabel_routes_the_unread_surface(self) -> None:
        gh, issue = self._deliver_through_validating()[:2]
        gh.apply_foreign_label(issue, LABEL_IN_REVIEW)

        review_mocks = self._run_dev_stage(LABEL_IN_REVIEW, gh, issue)

        # in_review never resumes the developer itself; it bookmarks the
        # batch, and the batch is the PR comment alone.
        review_mocks[RUN_AGENT].assert_not_called()
        self.assertIn((ISSUE, LABEL_FIXING), gh.label_history)
        self.assertEqual(
            self._state(gh).get(PENDING_FIX_ISSUE_MAX_ID),
            PR_CONVERSATION_ID,
        )

        fixing_mocks = self._run_dev_stage(LABEL_FIXING, gh, issue)

        prompt = "\n".join(self._prompts(fixing_mocks))
        self.assertIn(PR_CONVERSATION_BODY, prompt)
        self.assertNotIn(DELIVERED_REPLY, prompt)
        # Only what this prompt carried is consumed, so the issue thread is
        # still answered by the cursor the validating resume settled.
        self.assertEqual(
            self._state(gh).get(PR_LAST_COMMENT_ID), PR_CONVERSATION_ID,
        )

    def _deliver_through_validating(self, *, unread_pr_comment: bool = True):
        """Answer the reply on `workflow:validating`, and count what that cost.

        Returns the invocations so far, so a caller crossing into the stages
        that read the reply back can assert the total rather than each tick.
        """
        gh, issue = self._seed(
            label=LABEL_VALIDATING,
            pr=self._pr(issue_comments=[
                _comment(PR_CONVERSATION_ID, PR_CONVERSATION_BODY),
            ] if unread_pr_comment else []),
            awaiting_human=True,
            last_action_comment_id=PARK_NOTICE_ID,
        )

        prompts = self._prompts(self._run_dev_stage(LABEL_VALIDATING, gh, issue))

        self.assertEqual(
            len([quoted for quoted in prompts if DELIVERED_REPLY in quoted]), 1,
        )
        state = self._state(gh)
        self.assertEqual(state.get(LAST_ACTION_COMMENT_ID), ISSUE_REPLY_ID)
        # The resume read the issue thread only, so the surface a PR comment
        # would sit on is left exactly as unbounded as it was.
        self.assertIsNone(state.get(PR_LAST_COMMENT_ID))
        return gh, issue, len(prompts)


class AnsweredReplyRoutesNothingTest(unittest.TestCase, _ConsumptionFixtureMixin):
    """A thread whose only content the developer already answered is quiet.

    Both PR-side cursor shapes a relabelled or legacy issue arrives with sit
    BELOW the answered reply, so the reply is what the scan would re-read --
    and re-reading it spends a developer run on work already done.
    """

    def test_neither_stage_re_delivers(self) -> None:
        for watermark in LEGACY_WATERMARK_SHAPES:
            for label in (LABEL_IN_REVIEW, LABEL_FIXING):
                with self.subTest(pr_last_comment_id=watermark, label=label):
                    self._assert_quiet(label, watermark)

    def _assert_quiet(self, label, watermark) -> None:
        gh, issue = self._seed(
            label=label,
            pr=self._pr(),
            last_action_comment_id=ISSUE_REPLY_ID,
            **self._seeded_watermark(watermark),
        )

        mocks = self._run_dev_stage(label, gh, issue)

        mocks[RUN_AGENT].assert_not_called()
        self.assertNotIn((ISSUE, LABEL_FIXING), gh.label_history)
        self.assertIsNone(self._state(gh).get(PENDING_FIX_ISSUE_MAX_ID))


class UnreadFeedbackStillRoutesTest(unittest.TestCase, _ConsumptionFixtureMixin):
    """Every surface the developer has not answered still reaches `fixing`.

    The delivered reply bounds the issue thread and nothing else, so a PR
    conversation comment numbered below it, a later issue comment, an inline
    review comment, and a review summary all have to survive the scan that
    drops the reply -- each against the cursor that is actually its own, and
    each on a first tick whose review-surface cursors the migration has to
    seed without crossing them.
    """

    def test_lower_id_pr_comment_surfaces(self) -> None:
        for watermark in LEGACY_WATERMARK_SHAPES:
            with self.subTest(pr_last_comment_id=watermark):
                gh = self._route(
                    pr_fields={"issue_comments": [
                        _comment(PR_CONVERSATION_ID, PR_CONVERSATION_BODY),
                    ]},
                    **self._seeded_watermark(watermark),
                )

                # The bookmark is the PR comment and not the higher-numbered
                # reply, which is the whole of "read as separate surfaces".
                self.assertEqual(
                    self._state(gh).get(PENDING_FIX_ISSUE_MAX_ID),
                    PR_CONVERSATION_ID,
                )

    def test_later_issue_comment_surfaces(self) -> None:
        gh = self._route(
            issue_comments=[_comment(LATER_ISSUE_ID, LATER_ISSUE_BODY)],
        )

        self.assertEqual(
            self._state(gh).get(PENDING_FIX_ISSUE_MAX_ID), LATER_ISSUE_ID,
        )

    def test_inline_review_comment_surfaces(self) -> None:
        gh = self._route(
            pr_fields={"review_comments": [
                _comment(INLINE_REVIEW_ID, INLINE_REVIEW_BODY),
            ]},
        )

        self.assertEqual(
            self._state(gh).get(PENDING_FIX_REVIEW_MAX_ID), INLINE_REVIEW_ID,
        )

    def test_review_summary_surfaces(self) -> None:
        gh = self._route(
            pr_fields={"reviews": [
                FakePRReview(
                    id=REVIEW_SUMMARY_ID,
                    body=REVIEW_SUMMARY_BODY,
                    state=CHANGES_REQUESTED,
                    user=FakeUser(HUMAN),
                    submitted_at=_settled(),
                    commit_id=HEAD_SHA,
                ),
            ]},
        )

        self.assertEqual(
            self._state(gh).get(PENDING_FIX_REVIEW_SUMMARY_MAX_ID),
            REVIEW_SUMMARY_ID,
        )

    def _route(self, *, pr_fields=None, issue_comments=(), **state_fields):
        gh, issue = self._seed(
            label=LABEL_IN_REVIEW,
            pr=self._pr(**(pr_fields or {})),
            issue_comments=issue_comments,
            last_action_comment_id=ISSUE_REPLY_ID,
            **state_fields,
        )

        with patch.object(config, DEBOUNCE_SETTING, DEBOUNCE_SECONDS):
            mocks = self._run_in_review(gh, issue, run_agent=_agent())

        mocks[RUN_AGENT].assert_not_called()
        self.assertIn((ISSUE, LABEL_FIXING), gh.label_history)
        return gh


if __name__ == "__main__":
    unittest.main()
