# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

from tests.support.fakes import FakeGitHubClient, make_issue
from tests.workflow.fixtures import (
    LABEL_VALIDATING,
    _issue_branch,
    _open_pr_for,
    _PatchedWorkflowMixin,
)

ISSUE = 7
PR_NUMBER = 21
DEV_SESSION = "dev-sess"


class VerifyGateFixtureMixin(_PatchedWorkflowMixin):
    def _seeded(self, **state):
        gh = FakeGitHubClient()
        issue = make_issue(ISSUE, label=LABEL_VALIDATING)
        gh.add_issue(issue)
        defaults = {
            "pr_number": PR_NUMBER,
            "branch": _issue_branch(ISSUE),
            "dev_agent": "codex",
            "dev_session_id": DEV_SESSION,
            "review_round": 0,
        }
        defaults.update(state)
        gh.seed_state(ISSUE, **defaults)
        _open_pr_for(gh, issue_number=ISSUE, pr_number=defaults["pr_number"])
        return gh, issue
