# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Live `paused` guard for the fixing stage: an operator who applies `paused`
(or `backlog`) WHILE the PR-feedback dev resume is in flight freezes the issue
before the run's results are published. `_resume_dev_with_text(pause_guard=True)`
re-fetches the issue after the run returns (`gh.get_issue`) and, on a hit, the
handler returns before the delivery settlement, the ACK fast path,
`_handle_dev_fix_result`, or any relabel / pinned-state write past the run's
charge, its accounting, and the capture of the report it finished on -- so the
feedback stays unconsumed and the committed work stays on the branch until the
label is removed, when the dispatcher's recovery publishes that work under the
captured report with no developer running again."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from orchestrator import config
from orchestrator.github.labels import PAUSED_LABEL
from orchestrator.workflow.engine import completion_routes as _routes, issue_processing as _issue_processing
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakeLabel,
    FakePR,
    FakePRRef,
    FakeUser,
    make_issue,
)
from tests.workflow import drift_reports as _drift_world
from tests.workflow.fixtures import (
    _FAKE_WT,
    _TEST_SPEC,
    AGENT_RUN_WRITES,
    Launched,
    _agent,
    _PatchedWorkflowMixin,
    accounted,
)
from tests.workflow.stages.fixing import fixing_test_support as support
from tests.workflow.stages.fixing.prompt_expectations import (
    only_prompt,
    pr_feedback_prompt,
)

ISSUE = 880
PR_NUMBER = 880
BRANCH = "orchestrator/chippingway__chipping-orchestrator/issue-880"
PR_HEAD_SHA = support.PR_HEAD_SHA
DEV_AGENT = "claude"
DEV_SESSION = "dev-sess"
TRIGGER_ID = 2000
INITIAL_COMMENT_WATERMARK = 1999
DEBOUNCE_SECONDS = 600

# The one field a held run's report is captured in, beside its accounting.
CAPTURED = "developer_completion"


def _paused_view(number: int) -> object:
    """A `fixing` issue that also carries `paused` -- the state a fresh
    `gh.get_issue` returns after an operator pauses mid-run."""
    view = make_issue(number, label="workflow:fixing")
    view.labels.append(FakeLabel(PAUSED_LABEL))
    return view


# The one comment every case here is a fix round over, so the prompt a case
# asserts is the prompt this batch earns.
FEEDBACK = FakeComment(
    id=TRIGGER_ID,
    body="rename foo to bar",
    user=FakeUser("alice"),
    created_at=datetime.now(UTC) - timedelta(hours=1),
)


def _seed_fixing_pause(gh: FakeGitHubClient) -> object:
    issue = make_issue(ISSUE, label="workflow:fixing")
    issue.comments.append(FEEDBACK)
    gh.add_issue(issue)
    gh.add_pr(
        FakePR(
            number=PR_NUMBER,
            head_branch=BRANCH,
            head=FakePRRef(sha=PR_HEAD_SHA),
            mergeable=True,
            check_state="success",
        )
    )
    gh.seed_state(
        ISSUE,
        pr_number=PR_NUMBER,
        branch=BRANCH,
        dev_agent=DEV_AGENT,
        dev_session_id=DEV_SESSION,
        review_round=1,
        pr_last_comment_id=INITIAL_COMMENT_WATERMARK,
        pr_last_review_comment_id=0,
        pr_last_review_summary_id=0,
        pending_fix_at="2026-05-24T00:00:00+00:00",
        pending_fix_issue_max_id=TRIGGER_ID,
    )
    return issue


def _assert_fixing_pause_preserves_state(
    test_case,
    github,
    mocks,
    before,
) -> None:
    mocks["_push_branch"].assert_not_called()
    test_case.assertEqual(github.label_history, [])
    test_case.assertEqual(github.posted_comments, [])
    pinned_data = before.held(
        test_case, github, ISSUE, writes=AGENT_RUN_WRITES + 1, beside=(CAPTURED,),
    )
    # The report the run finished on, captured on the pull request feedback
    # road and owned by nothing else yet.
    test_case.assertEqual(
        (pinned_data[CAPTURED]["stage"], pinned_data[CAPTURED]["route"]),
        ("pending", _routes.CompletionRoute.PR_FEEDBACK),
    )
    test_case.assertEqual(
        pinned_data.get("pr_last_comment_id"),
        INITIAL_COMMENT_WATERMARK,
    )
    # The issue-action reader a delivered round also settles is left exactly
    # as unset as the seed left it: nothing was delivered.
    test_case.assertIsNone(pinned_data.get("last_action_comment_id"))
    test_case.assertEqual(
        pinned_data.get("pending_fix_at"),
        "2026-05-24T00:00:00+00:00",
    )
    test_case.assertFalse(pinned_data.get("awaiting_human"))
    test_case.assertEqual(
        pinned_data.get("dev_session_id"),
        DEV_SESSION,
    )


class FixingLivePauseTest(unittest.TestCase, _PatchedWorkflowMixin):
    def test_resume_pause_blocks_publish_and_relabel(
        self,
    ) -> None:
        # The handler's `issue` snapshot carries no `paused`; the operator
        # applied it only after the resume started, so it appears solely on the
        # freshly fetched view. The dev even reports a pushable fix -- a guard
        # that consulted the stale labels (or skipped the check) would push and
        # flip to `validating`. Asserting no push / no relabel proves the guard
        # reads `gh.get_issue` and honors it.
        gh = FakeGitHubClient()
        issue = _seed_fixing_pause(gh)
        before = Launched.over(gh, ISSUE)

        get_issue_mock = MagicMock(return_value=_paused_view(ISSUE))
        with (
            patch.object(config, "IN_REVIEW_DEBOUNCE_SECONDS", DEBOUNCE_SECONDS),
            patch.object(gh, "get_issue", get_issue_mock),
        ):
            mocks = self._run_fixing(
                gh,
                issue,
                run_agent=_agent(session_id=DEV_SESSION, last_message=support.PUSHED_FIX_MESSAGE),
                head_shas=(support.SHA_BEFORE, support.SHA_AFTER),
                push_branch=True,
            )

        # One run, handed exactly this batch: the pause refuses what the run
        # produced, never the delivery that reached it.
        self.assertEqual(only_prompt(mocks), pr_feedback_prompt([FEEDBACK]))
        get_issue_mock.assert_called_with(ISSUE)
        _assert_fixing_pause_preserves_state(
            self,
            gh,
            mocks,
            before,
        )

    def test_unpause_publishes_the_captured_report(self) -> None:
        # End-to-end: tick 1 is frozen by a live pause, which leaves the
        # feedback unconsumed and the report the run finished on captured;
        # tick 2, after the operator removes `paused`, is a whole dispatch,
        # whose recovery pushes the commit under that report and flips to
        # `validating` with no developer launched -- the batch the pause left
        # unconsumed settled once, the round reset, and the run's exit
        # accounted once. The fetch carries the same thread the round was
        # handed, because the admission and the settlement behind the push
        # both re-read the issue to say whether its requirements have moved:
        # a view missing the very comment this round answered would read as
        # an edit nobody made.
        gh = FakeGitHubClient()
        issue = _seed_fixing_pause(gh)

        with (
            patch.object(config, "IN_REVIEW_DEBOUNCE_SECONDS", DEBOUNCE_SECONDS),
            patch.object(gh, "get_issue", MagicMock(return_value=_paused_view(ISSUE))),
        ):
            self._run_fixing(
                gh,
                issue,
                run_agent=_agent(session_id=DEV_SESSION, last_message=support.PUSHED_FIX_MESSAGE),
                head_shas=(support.SHA_BEFORE, support.SHA_AFTER),
                push_branch=True,
            )
        self.assertEqual(gh.label_history, [])

        unpaused = make_issue(ISSUE, label="workflow:fixing")
        unpaused.comments.append(FEEDBACK)
        with (
            patch.object(config, "IN_REVIEW_DEBOUNCE_SECONDS", DEBOUNCE_SECONDS),
            patch.object(gh, "get_issue", MagicMock(return_value=unpaused)),
        ):
            mocks = self._run(
                lambda: _issue_processing._process_issue(gh, _TEST_SPEC, unpaused),
                run_agent=MagicMock(),
                head_shas=(support.SHA_AFTER,),
                push_branch=_drift_world._LandingPush(gh.get_pr(PR_NUMBER)),
                issue_checkout=_FAKE_WT,
            )

        mocks["run_agent"].assert_not_called()
        mocks["_push_branch"].assert_called_once()
        self.assertIn((ISSUE, "workflow:validating"), gh.label_history)
        pinned_data = gh.pinned_data(ISSUE)
        self.assertEqual(
            (
                pinned_data[CAPTURED]["stage"],
                pinned_data.get("review_round"),
                pinned_data.get("pending_fix_at"),
                pinned_data.get("pr_last_comment_id"),
                accounted(pinned_data),
            ),
            ("handed_off", 0, None, TRIGGER_ID, (1, 1)),
        )


if __name__ == "__main__":
    unittest.main()
