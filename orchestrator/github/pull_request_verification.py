# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finding and posting the verification artifacts on a pull request.

The road is the developer report's, and deliberately the same one: every
reading is present, absent, changed, or unconfirmed, and only ABSENT licenses
a post. That is what keeps publication idempotent and append-only -- a retry
finds what an earlier attempt landed instead of repeating it, an artifact once
posted is never edited, and the description is never written at all.

The readings themselves are `pull_request_reports`' own types rather than a
second vocabulary saying the same thing. A reading is one moment on one pull
request's conversation, and the identity of what it found is resolved once
when it is taken, for a reason that does not change with what the comment
carries: the id is a member of an object GitHub handed back, so it is a
request that can fail once and succeed the next time it is made. Rereading a
published artifact is that owner's `reread_report_location` for the same
reason -- a location is a pull request and a comment id, and what proves it
unchanged is the digest of the body sitting there NOW.

What is separate is the thread request and the post, which are this owner's
own seams: the shared in-memory double answers them for artifacts without
inheriting whatever a case has arranged for reports.

Recording the comment an artifact landed as is not something this owner can
discharge: the ledger of this orchestrator's own comments is pinned state,
which lives above here. A caller publishes through
`workflow/engine/verification_comments.py`, which takes that id off the
reading returned below -- so a post whose response was lost is still recorded
by the retry that finds the comment it landed. The marker in the rendering
says the comment is ours after its id ages out of that ledger; the id says so
after somebody edits the marker away.
"""
from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from github.IssueComment import IssueComment
from github.PullRequest import PullRequest

from orchestrator.github import (
    comments as _comments,
    verification_artifacts as _artifacts,
    verification_evidence as _evidence,
)
from orchestrator.github.pull_request_reports import ReportLookup, ReportPresence

log = logging.getLogger("orchestrator.github")


class GitHubPullRequestVerification:
    """GitHubClient operations for the verification artifacts a pull request carries."""

    def find_verification_artifact(
        self, pr: PullRequest, artifact: _artifacts.VerificationArtifact,
    ) -> ReportLookup:
        """Whether `artifact` is already on this pull request's conversation.

        Scoped by the artifact's receipt, so what a retry finds is its own
        transaction's comment and never a later artifact on the same commit.
        PRESENT needs a comment of ours carrying exactly the rendering. A
        comment of ours carrying the receipt in any other shape is CHANGED,
        which a caller holds on rather than posts past, since a second comment
        under one receipt would leave two claims to one transaction. A copy
        anybody else pasted is neither: it is not ours, so it is not there.

        UNCONFIRMED is a thread nobody could read, or one whose comments would
        not say who wrote them: an author is a request on a worker that has
        not completed it, and one that raised decides nothing about a comment.
        """
        _refuse_another_pull_request(pr, artifact)
        try:
            lookup = _artifact_on_thread(
                self._verification_thread(pr), artifact,
                bot_login=getattr(self, "_bot_login", None),
            )
        except Exception:
            log.warning(
                "could not read PR #%s, or who wrote what is on it, for "
                "verification artifact revision %s",
                artifact.pr_number, artifact.artifact_revision, exc_info=True,
            )
            lookup = ReportLookup(ReportPresence.UNCONFIRMED)
        return lookup

    def publish_verification_artifact(
        self, pr: PullRequest, artifact: _artifacts.VerificationArtifact,
    ) -> ReportLookup:
        """Post `artifact` onto this pull request once, and say where it stands.

        `ArtifactRefusedError` before any request when the artifact names
        another pull request or would not fit in one comment. Then the thread
        is read, and only ABSENT is posted onto; every other reading is handed
        back as it came. A post that raised is UNCONFIRMED whatever raised it:
        a timeout after GitHub accepted the comment and a refusal before it did
        look alike from here, and the next call's read tells them apart.
        """
        body = _artifacts.render_verification_artifact(artifact)
        lookup = self.find_verification_artifact(pr, artifact)
        if lookup.presence is not ReportPresence.ABSENT:
            return lookup
        try:
            posted = self._post_verification_artifact(pr, body)
        except Exception:
            log.warning(
                "could not confirm verification artifact revision %s on PR #%s",
                artifact.artifact_revision, artifact.pr_number, exc_info=True,
            )
            return ReportLookup(ReportPresence.UNCONFIRMED)
        return ReportLookup(ReportPresence.PRESENT, posted)

    def _verification_thread(self, pr: PullRequest) -> list[IssueComment]:
        """Every conversation comment on one pull request, read in full."""
        return list(pr.get_issue_comments())

    def _post_verification_artifact(
        self, pr: PullRequest, body: str,
    ) -> IssueComment:
        """Append one conversation comment to one pull request."""
        return pr.create_issue_comment(body)


def _refuse_another_pull_request(
    pr: PullRequest, artifact: _artifacts.VerificationArtifact,
) -> None:
    """Refuse looking for an artifact on a pull request it does not name.

    The rendering says which pull request it is evidence for, so on another
    thread it is evidence about somewhere else -- and found there, a retry
    would take it as having landed where it belongs.
    """
    if pr.number != artifact.pr_number:
        raise _evidence.ArtifactRefusedError(
            f"a verification artifact for PR #{artifact.pr_number} "
            f"cannot go onto PR #{pr.number}",
        )


def _artifact_on_thread(
    thread: Iterable[Any],
    artifact: _artifacts.VerificationArtifact,
    *,
    bot_login: str | None,
) -> ReportLookup:
    """What one read thread holds for `artifact`'s transaction."""
    expected = _artifacts.render_verification_artifact(artifact)
    claimants = [
        posted for posted in thread
        if _comments.carries_own_marker(
            (posted,), artifact.receipt_scope, bot_login=bot_login,
        )
    ]
    exact = next((posted for posted in claimants if posted.body == expected), None)
    if exact is not None:
        return ReportLookup(ReportPresence.PRESENT, exact)
    if claimants:
        return ReportLookup(ReportPresence.CHANGED, claimants[0])
    return ReportLookup(ReportPresence.ABSENT)
