# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Reviewer fixtures for tracked-repository prompt tests."""
from __future__ import annotations

from orchestrator.workflow.stages.validating import handler as _validating
from tests.workflow import published_reports as _published_reports
from tests.workflow.stages import tracked_repos_test_support as support


def _review_seed():
    github = support.FakeGitHubClient()
    issue = support.make_issue(
        support._REVIEW_ISSUE_NUMBER,
        label="workflow:validating",
    )
    github.add_issue(issue)
    github.seed_state(
        support._REVIEW_ISSUE_NUMBER,
        pr_number=support._REVIEW_PR_NUMBER,
        branch="orchestrator/chippingway__orchestrator/issue-711",
        codex_session_id=support._DEV_SESSION_ID,
        review_round=0,
    )
    support._helpers._open_pr_for(
        github,
        issue_number=support._REVIEW_ISSUE_NUMBER,
        pr_number=support._REVIEW_PR_NUMBER,
    )
    _published_reports.publishes_the_report(github, issue)
    return github, issue


def _review_prompt(case) -> str:
    github, issue = _review_seed()
    mocks = case._run(
        lambda: _validating._handle_validating(
            github,
            support._TEST_SPEC,
            issue,
        ),
        run_agent=support._agent(
            last_message=support.REVIEW_APPROVED_MESSAGE,
        ),
    )
    return support._prompt_of(mocks[support._RUN_AGENT_ATTR])
