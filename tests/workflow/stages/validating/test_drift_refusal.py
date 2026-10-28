# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A body edit under review over a record the drift resume refuses.

The resume prepares its checkout before it says anything, and preparing it
resolves the branch the record names: a pull request recorded with no branch
beside it names none live work may use, so the edit is refused before its
notice. Nothing records the refusal as progress, so every tick that finds the
same record refuses it again -- and says nothing each time.
"""
from __future__ import annotations

import unittest

from orchestrator.git.worktrees import naming
from orchestrator.workflow.stages.validating import handler
from tests.support.fakes import FakeGitHubClient, FakePR, make_issue
from tests.workflow.approval_records import STALE_REQUIREMENTS
from tests.workflow.fixtures import _TEST_SPEC

ISSUE = 7
PR_NUMBER = 42

# The ticks that find the same refused record.
_TICKS = 2


class BranchlessDriftTest(unittest.TestCase):
    """An edited body under review, over a pull request recorded with no branch beside it."""

    def test_every_tick_refuses_in_silence(self) -> None:
        github = FakeGitHubClient()
        issue = make_issue(ISSUE, label="workflow:validating", body="Updated requirements")
        github.add_issue(issue)
        github.add_pr(FakePR(number=PR_NUMBER, head_branch=naming._branch_name(_TEST_SPEC, ISSUE)))
        github.seed_state(
            ISSUE, pr_number=PR_NUMBER, user_content_hash=STALE_REQUIREMENTS,
            dev_agent="claude", dev_session_id="dev-session",
        )
        writes = github.write_state_calls

        refusals = [
            self.assertRaises(naming.BranchRefused, handler._handle_validating, github, _TEST_SPEC, issue)
            for _ in range(_TICKS)
        ]

        self.assertEqual(len(refusals), _TICKS)
        self.assertEqual(github.posted_comments, [])
        self.assertEqual(github.write_state_calls, writes)
        self.assertEqual(github.label_history, [])


if __name__ == "__main__":
    unittest.main()
