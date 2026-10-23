# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""A developer report this orchestrator published is never PR feedback.

The report carries our marker in its rendering, so it stays out of the fixing
route once the bounded id ledger has forgotten it -- while an ordinary comment
a human wrote under the same login is still feedback, since nothing about the
login says who typed it. The report is the settled one an approval over
passing evidence covered, so a scan that drops it reaches the ready ping.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from orchestrator import config
from orchestrator.workflow.engine import report_settlement_state as _report_settlement
from tests.support.fakes import (
    FakeComment,
    FakeGitHubClient,
    FakePR,
    FakePRRef,
    FakeUser,
    make_issue,
)
from tests.workflow import verified_approvals as _verified
from tests.workflow.fixtures import (
    LABEL_FIXING,
    LABEL_IN_REVIEW,
    _agent,
    _issue_branch,
    _PatchedWorkflowMixin,
)

ISSUE = 122

PR = 222

# The last comment the scan has read, the human's comment past it, and our
# report published after both, numbered ABOVE them: a filter that let the
# report through would name it as the newest feedback.
WATERMARK = 2999

HUMAN_COMMENT_ID = 3000

# What the comment the scan has read says.
READ_NOTICE = ":sparkles: PR opened"

# The ids the ledger does remember, which name neither comment above -- the
# shape it is left in once it has evicted our report.
REMEMBERED_IDS = (900, 901)

HEAD = "c0ffee0000000000000000000000000000c0ffee"

BOT_LOGIN = "orchestrator"

PENDING_ISSUE_MAX_ID = "pending_fix_issue_max_id"

READY_PING_SHA = "ready_ping_sha"


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
                    mocks = self._run_in_review(
                        github, issue, run_agent=_agent(), **_verified.proving(github, issue),
                    )

                mocks["run_agent"].assert_not_called()
                self.assertGreater(self._report_id(github, issue), WATERMARK)
                self.assertEqual(
                    _outcome(github),
                    (True, HUMAN_COMMENT_ID, None) if human_wrote_too
                    else (False, None, HEAD),
                )

    def _seeded(self, *, human_wrote_too: bool):
        """A documented head whose pull request carries our settled report, and the approval's evidence."""
        github = FakeGitHubClient(bot_login=BOT_LOGIN)
        issue = make_issue(ISSUE, label=LABEL_IN_REVIEW)
        github.add_issue(issue)
        written = datetime.now(UTC) - timedelta(hours=1)
        thread = [FakeComment(
            id=WATERMARK, body=READ_NOTICE,
            user=FakeUser(BOT_LOGIN), created_at=written,
        )]
        if human_wrote_too:
            thread.append(FakeComment(
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
        with patch.object(config, "ALLOWED_ISSUE_AUTHORS", ()):
            _verified.verifies_the_approval(github, issue)
        return github, issue

    def _report_id(self, github, issue) -> int:
        """The comment the settled report landed as, which the ledger does not name."""
        settled = _report_settlement.read_current_report(github.read_pinned_state(issue))
        self.assertNotIn(settled.location.comment_id, github.pinned_data(ISSUE)["orchestrator_comment_ids"])
        return settled.location.comment_id


if __name__ == "__main__":
    unittest.main()
