# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Pull-request creation, editing, labeling, merging, and branch deletion.

The complete client surface includes the read, developer-report,
verification-artifact, and retirement owners through this mixin. Reads
preserve unknown publication evidence, reports and verification artifacts are
each appended beside the description rather than written into it, and
retirement keeps its notice and close ordered; these mutation methods retain
the exact SHA and ref the caller proved before asking GitHub to change them.
"""
from __future__ import annotations

import logging

from github import GithubException
from github.IssueComment import IssueComment
from github.PullRequest import PullRequest

from orchestrator.github import (
    pull_request_reads as _pr_reads,
    pull_request_reports as _pr_reports,
    pull_request_retirement as _pr_retirement,
    pull_request_verification as _pr_verification,
)
from orchestrator.github.aliases import StaticMethodAlias

log = logging.getLogger("orchestrator.github")
_HTTP_NOT_FOUND = 404


PR_HAS_LABEL_METHOD = StaticMethodAlias(_pr_reads.pr_has_label)
PR_STATE_METHOD = StaticMethodAlias(_pr_reads.pr_state)
PR_IS_MERGEABLE_METHOD = StaticMethodAlias(_pr_reads.pr_is_mergeable)


class _PullRequestEvidence(
    _pr_reports.GitHubPullRequestReports,
    _pr_verification.GitHubPullRequestVerification,
):
    """The two append-only evidence surfaces one pull request carries.

    Grouped because they are one kind of thing reached one way: a developer
    run's report and the workflow's own verification artifact are each posted
    beside the description and never into it, and each answers on the owner
    that defines it.
    """


class GitHubPullRequestMixin(
    _PullRequestEvidence,
    _pr_retirement.GitHubPullRequestRetirement,
    _pr_reads.GitHubPullRequestReads,
):
    """Pull-request mutations with inherited lookup, evidence, and guarded retirement operations."""

    pr_has_label = PR_HAS_LABEL_METHOD
    pr_state = PR_STATE_METHOD
    pr_is_mergeable = PR_IS_MERGEABLE_METHOD

    def open_pr(
        self,
        *,
        branch: str,
        base: str,
        title: str,
        body: str,
    ) -> PullRequest:
        """Open a pull request for a published issue branch."""
        return self.repo.create_pull(
            title=title,
            body=body,
            head=branch,
            base=base,
        )

    def edit_pr_body(self, pr: PullRequest, body: str) -> None:
        """Rewrite one pull request's body.

        For a caller that adopts a PR it did not necessarily open -- the
        discussion stage reuses whatever is open on the branch it published,
        and implementing reuses that same plan PR once the dev's commits are
        on the branch -- and so has to make the description say what the
        branch now carries.
        """
        pr.edit(body=body)

    def pr_comment(self, pr_number: int, body: str) -> IssueComment:
        """Post one pull-request conversation comment."""
        return self.repo.get_pull(pr_number).create_issue_comment(body)

    def add_pr_label(self, pr: PullRequest, label_name: str) -> None:
        """Add one pull-request label idempotently at the GitHub layer."""
        pr.add_to_labels(label_name)

    def merge_pr(
        self,
        pr: PullRequest,
        *,
        sha: str,
        method: str = "squash",
    ) -> bool:
        """Attempt one SHA-pinned merge without blind retries."""
        try:
            pr.merge(sha=sha, merge_method=method)
        except GithubException as error:
            log.warning(
                "merge failed for PR #%s (HTTP %s): %s",
                pr.number,
                error.status,
                error.data,
            )
            return False
        return True

    def delete_remote_branch(self, branch: str) -> bool:
        """Delete a remote branch, treating an absent ref as success."""
        try:
            self.repo.get_git_ref(f"heads/{branch}").delete()
        except GithubException as error:
            if error.status == _HTTP_NOT_FOUND:
                return True
            log.warning(
                "could not delete remote branch %r (HTTP %s): %s",
                branch,
                error.status,
                error.data,
            )
            return False
        return True
