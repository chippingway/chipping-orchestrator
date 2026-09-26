# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A developer report this orchestrator published is never PR feedback.

The report carries our marker in its rendering, so it stays out of the fixing
route once the bounded id ledger has forgotten it -- while an ordinary comment
a human wrote under the same login is still feedback, since nothing about the
login says who typed it.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from orchestrator import config
from orchestrator.github import developer_reports as _reports
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    FakeUser,
    make_issue,
)
from tests.workflow.fixtures import (
    LABEL_FIXING,
    LABEL_IN_REVIEW,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)

ISSUE = 122

PR = 222

# The human's comment, and our report numbered ABOVE it: a filter that let the
# report through would name it as the newest feedback.
HUMAN_COMMENT_ID = 3000

REPORT_COMMENT_ID = 3001

WATERMARK = 2999

# The ids the ledger does remember, which name neither comment above -- the
# shape it is left in once it has evicted our report.
REMEMBERED_IDS = (900, 901)

HEAD = "c0ffee0000000000000000000000000000c0ffee"

BOT_LOGIN = "orchestrator"

PENDING_ISSUE_MAX_ID = "pending_fix_issue_max_id"

READY_PING_SHA = "ready_ping_sha"


def _report_body() -> str:
    return _reports.render_developer_report(_reports.DeveloperReport(
        pr_number=PR,
        source_sha=HEAD,
        requirements_revision="requirements-1",
        report_revision=1,
        receipt=f"issue-{ISSUE}-report-1",
        text="Covers the change; the suite passes.",
    ))


def _outcome(github) -> tuple:
    """Whether the tick routed to `fixing`, what it bookmarked, and what it pinged."""
    pinned = github.pinned_data(ISSUE)
    return (
        (ISSUE, LABEL_FIXING) in github.label_history,
        pinned.get(PENDING_ISSUE_MAX_ID),
        pinned.get(READY_PING_SHA),
    )


class GeneratedReportFilterTest(unittest.TestCase, _PatchedWorkflowMixin):
    """What an in_review scan makes of our report and of a same-login human."""

    def test_a_report_never_routes_a_human_does(self) -> None:
        for human_wrote_too in (False, True):
            with self.subTest(human_wrote_too=human_wrote_too):
                github, issue = self._seeded(human_wrote_too=human_wrote_too)

                with patch.object(config, "ALLOWED_ISSUE_AUTHORS", ()):
                    mocks = self._run_in_review(github, issue, run_agent=_agent())

                mocks["run_agent"].assert_not_called()
                self.assertEqual(
                    _outcome(github),
                    (True, HUMAN_COMMENT_ID, None) if human_wrote_too
                    else (False, None, HEAD),
                )

    def _seeded(self, *, human_wrote_too: bool):
        """A documented head whose pull request carries our report."""
        github = FakeGitHubClient(bot_login=BOT_LOGIN)
        issue = make_issue(ISSUE, label=LABEL_IN_REVIEW)
        github.add_issue(issue)
        written = datetime.now(UTC) - timedelta(hours=1)
        thread = [FakeComment(
            id=REPORT_COMMENT_ID, body=_report_body(),
            user=FakeUser(BOT_LOGIN), created_at=written,
        )]
        if human_wrote_too:
            thread.insert(0, FakeComment(
                id=HUMAN_COMMENT_ID,
                body="please explain the migration before this merges",
                user=FakeUser(BOT_LOGIN),
                created_at=written,
            ))
        github.add_pr(FakePR(
            number=PR,
            head_branch=_issue_branch(ISSUE),
            head=FakePRRef(sha=HEAD),
            mergeable=True,
            issue_comments=thread,
        ))
        github.seed_state(
            ISSUE,
            pr_number=PR,
            branch=_issue_branch(ISSUE),
            dev_agent="claude",
            dev_session_id="dev-sess",
            pr_last_comment_id=WATERMARK,
            pr_last_review_comment_id=0,
            pr_last_review_summary_id=0,
            orchestrator_comment_ids=list(REMEMBERED_IDS),
            docs_checked_sha=HEAD,
            docs_verdict="no_change",
        )
        return github, issue


if __name__ == "__main__":
    unittest.main()
