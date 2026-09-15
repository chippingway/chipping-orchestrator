# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Developer-report requests for the in-memory GitHub client.

The policy is the real client's, inherited: which reading licenses a post, what
a request that raised is answered with, that a report goes only onto the pull
request it names, and that nothing is ever edited. What this supplies is the
three requests, answered from the pull requests the client holds -- and the ways
GitHub leaves them unanswered, named per pull request on `report_failures`.
"""
from __future__ import annotations

from orchestrator.github.pull_request_reports import GitHubPullRequestReports
from tests.support.github.models import FakeComment, FakeUser
from tests.support.github.pull_request_models import FakePR
from tests.support.github.state import _FakeReportFailures

# What an unanswered request raises. The real client catches whatever a request
# raises, so the double need not spell PyGithub's exceptions to be answered alike.
_READ_REFUSED = "GitHub did not answer the read"
_POST_REFUSED = "GitHub refused the comment"
_RESPONSE_LOST = "the comment landed and its response was lost"


class _PullReportService(GitHubPullRequestReports):
    """Answer developer-report requests from the pull requests this client holds."""

    @property
    def report_failures(self) -> _FakeReportFailures:
        """The pull requests whose report requests go unanswered, by how."""
        return self._pull_state._report_failures

    def _fetch_report_pull(self, pr_number: int) -> FakePR:
        pull_request = self.pulls.get(pr_number)
        if pull_request is None or pr_number in self.report_failures.unreadable:
            raise RuntimeError(_READ_REFUSED)
        return pull_request

    def _report_thread(self, pr: FakePR) -> list[FakeComment]:
        if pr.number in self.report_failures.unreadable:
            raise RuntimeError(_READ_REFUSED)
        return list(pr.issue_comments)

    def _post_report(self, pr: FakePR, body: str) -> FakeComment:
        """Append one comment under this client's login, as any PR comment is.

        A lost response lands the comment and raises afterwards, which is the
        accepted write a retry has to find rather than post again.
        """
        if pr.number in self.report_failures.refused:
            raise RuntimeError(_POST_REFUSED)
        posted = FakeComment(
            id=self._next_comment_id(pr),
            body=body,
            user=FakeUser(self._bot_login),
        )
        pr.issue_comments.append(posted)
        self.posted_pr_comments.append((pr.number, body))
        if pr.number in self.report_failures.lost:
            raise RuntimeError(_RESPONSE_LOST)
        return posted
