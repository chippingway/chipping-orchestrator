# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures and protocol values for implementing PR tests."""

from __future__ import annotations

from orchestrator.workflow.stages.implementing import (
    dev_pr as _dev_pr,
    state as _state,
)
from tests.support import fakes
from tests.workflow import fixtures
from tests.workflow.stages import implementing_fixing_test_cases

# The cap and the marker are state constants; the formatter that applies them
# to a PR body belongs to the owner that builds the body.
_PR_BODY_AGENT_MESSAGE_CAP = _state._PR_BODY_AGENT_MESSAGE_CAP
_PR_BODY_TRUNCATION_MARKER = _state._PR_BODY_TRUNCATION_MARKER
_format_pr_agent_message = _dev_pr._format_pr_agent_message

FakeComment = fakes.FakeComment
FakeGitHubClient = fakes.FakeGitHubClient
FakePR = fakes.FakePR
FakeUser = fakes.FakeUser
LazyPullRequest = fakes.LazyPullRequest
make_issue = fakes.make_issue
IssueScenario = implementing_fixing_test_cases.IssueScenario
posted_comment_contains = implementing_fixing_test_cases.posted_comment_contains

LABEL_IMPLEMENTING = fixtures.LABEL_IMPLEMENTING
_PatchedWorkflowMixin = fixtures._PatchedWorkflowMixin
_TEST_SPEC = fixtures._TEST_SPEC
_agent = fixtures._agent
_reported = fixtures._reported
_named_description = fixtures._named_description

DEV_SESSION = "sess-1"
DONE_MESSAGE = _reported("done")
FEATURE_PREFIX = "feat"
TEST_ISSUE_TITLE = "add a thing"
SPARKLY_TITLE = "add a sparkly thing"
SPARKLY_COMMIT_SUBJECT = "feat: add a sparkly thing"
GITHUB_BODY_LIMIT = 65536
EXISTING_PR_NUMBER = 42
BRANCHLESS_ISSUE = 11
BRANCHLESS_REPLY_ID = 2100
BRANCHLESS_WATERMARK = 2000
LONG_MESSAGE_WORD_COUNT = 20000
CODE_FENCE_LINE_COUNT = 20000
TOKEN_TAIL_LENGTH = 4000
LONG_BODY_REPEAT_COUNT = 5000
BODY_SHORT_ISSUE = 61
CONVENTIONAL_ISSUE = 30
INFERRED_PREFIX_ISSUE = 37


class _ConventionalTitleFixtureMixin(_PatchedWorkflowMixin):
    def _seeded(self, *, issue_number: int = CONVENTIONAL_ISSUE) -> tuple:
        gh = FakeGitHubClient()
        issue = make_issue(
            issue_number,
            label=LABEL_IMPLEMENTING,
            title=SPARKLY_TITLE,
        )
        gh.add_issue(issue)
        return gh, issue
