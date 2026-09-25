# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Verification-artifact requests for the in-memory GitHub client.

The policy is the real client's, inherited: which reading licenses a post,
what a request that raised is answered with, that an artifact goes only onto
the pull request it names, and that nothing is ever edited. What this supplies
is the two requests, answered from the pull requests the client holds.

The ways GitHub leaves them unanswered are the ones already named per pull
request on `report_failures`, because there is one conversation behind both:
a thread nobody can read is unreadable for an artifact exactly as it is for a
report, and a case that refuses one refuses the other.
"""
from __future__ import annotations

from orchestrator.github.pull_request_verification import GitHubPullRequestVerification
from tests.support.github.models import FakeComment, FakeUser
from tests.support.github.pull_request_models import FakePR
from tests.support.github.report_service import _PullReportService

# What an unanswered request raises. The real client catches whatever a request
# raises, so the double need not spell PyGithub's exceptions to be answered alike.
_READ_REFUSED = "GitHub did not answer the read"
_POST_REFUSED = "GitHub refused the comment"
_RESPONSE_LOST = "the comment landed and its response was lost"


class _PullVerificationService(GitHubPullRequestVerification):
    """Answer verification-artifact requests from the pull requests this client holds."""

    def _verification_thread(self, pr: FakePR) -> list[FakeComment]:
        if pr.number in self.report_failures.unreadable:
            raise RuntimeError(_READ_REFUSED)
        return list(pr.issue_comments)

    def _post_verification_artifact(self, pr: FakePR, body: str) -> FakeComment:
        """Append one comment under this client's login, as any PR comment is.

        Recorded in the same ledger of comments this orchestrator posted that
        every other one enters, which is what keeps a published artifact from
        being read back as somebody's fresh feedback. A lost response lands the
        comment and raises afterwards, which is the accepted write a retry has
        to find rather than post again.
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


class _PullEvidenceService(_PullReportService, _PullVerificationService):
    """The two append-only evidence surfaces one pull request carries.

    Grouped here rather than at the composition root because the artifact
    requests are answered out of the failures the report service names: one
    conversation, one way GitHub leaves its requests unanswered.
    """
