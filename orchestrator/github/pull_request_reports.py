# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Finding, posting, and rereading the developer reports on a pull request.

Every reading answers one of four ways, and only one of them licenses a post.
PRESENT is the expected report where it was looked for. ABSENT is a place that
was read and holds no such report. CHANGED is a report identity something else
now occupies: our receipt on a comment that no longer renders as the report, or
a location whose content moved off the revision somebody verified. UNCONFIRMED
is every reading nobody could take -- including a post whose response never
came back, since GitHub may well hold that comment and only a later read can
say.

A post is made only on ABSENT, which is what keeps publication idempotent and
append-only: a retry finds what an earlier attempt landed instead of repeating
it, a report once posted is never edited, and the description is never written
at all. The requests themselves sit behind three small methods, so the shared
in-memory double answers them while inheriting everything decided here.
"""
from __future__ import annotations

import enum
import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from github.IssueComment import IssueComment
from github.PullRequest import PullRequest

from orchestrator.github import comments as _comments, developer_reports as _reports

log = logging.getLogger("orchestrator.github")


class ReportPresence(enum.Enum):
    """Whether a report is where it was looked for, and how sure that is."""

    PRESENT = "present"
    ABSENT = "absent"
    CHANGED = "changed"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True)
class ReportLookup:
    """One reading: its presence, what it was read off, and that thing's id.

    `found` is the comment -- or, for a description, the pull request -- that
    answered PRESENT or CHANGED, so a caller can ask who wrote it before
    trusting it. Every other answer found nothing to hand over.

    `landed_id` is resolved here, ONCE, when the reading is taken, rather than
    answered afresh to whoever asks. That is what makes it part of the reading
    instead of a question two callers can get different answers to: the id is
    a member of an object GitHub handed back, so on a worker that has not
    completed it the read is a request -- and a request can fail once and
    succeed the next time it is made. Read twice on the publication road, the
    ledger of this orchestrator's own comments would be written from one
    answer and the settled report's location from the other, so a report
    recorded as published would sit at a comment nothing recorded posting --
    and the drift hash and every feedback scan would read its own text back as
    a human's.

    None is every answer but a usable identity, and callers owe them all the
    same thing. A reading that found nothing names no comment; so does one
    whose id would not read. And a caller holding a DESCRIPTION reading has a
    pull request here rather than a comment, so the identity it finds is not a
    comment id at all -- which is why only the conversation road asks.
    """

    presence: ReportPresence
    found: Any = None
    landed_id: int | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        """Resolve the identity of what was found, at the moment it was found.

        Guarded, because `found` is an object GitHub handed back: on a worker
        that has not completed it this is a request, and every caller of this
        reading runs inside a dispatch guard where one that raised would leave
        by an exception rather than by an answer -- out of the tick entirely.
        """
        try:
            identity = getattr(self.found, "id", None)
        except Exception:
            log.warning(
                "could not read the id of what a developer-report reading found",
                exc_info=True,
            )
            identity = None
        if isinstance(identity, bool) or not isinstance(identity, int):
            identity = None
        object.__setattr__(self, "landed_id", identity)


@dataclass(frozen=True)
class ReportLocation:
    """Where a report sits: one conversation comment, or the description.

    Exact in both halves. A comment id alone names a comment anywhere in the
    repository, so the pull request is part of the location, and a comment
    that is not on that pull request's own conversation is not there.
    """

    pr_number: int
    comment_id: int | None = None


class GitHubPullRequestReports:
    """GitHubClient operations for the developer reports a pull request carries."""

    def find_developer_report(
        self, pr: PullRequest, report: _reports.DeveloperReport,
    ) -> ReportLookup:
        """Whether `report` is already on this pull request's conversation.

        Scoped by the report's receipt, so what a retry finds is its own
        transaction's comment and never a later report on the same commit.
        PRESENT needs a comment of ours carrying exactly the rendering. A
        comment of ours carrying the receipt in any other shape is CHANGED,
        which a caller holds on rather than posts past, since a second comment
        under one receipt would leave two claims to one transaction. A copy
        anybody else pasted is neither: it is not ours, so it is not there.

        UNCONFIRMED is a thread nobody could read, or one whose comments would
        not say who wrote them: an author is a request on a worker that has
        not completed it, and one that raised decides nothing about a comment.
        """
        _refuse_another_pull_request(pr, report)
        try:
            lookup = _report_on_thread(
                self._report_thread(pr), report,
                bot_login=getattr(self, "_bot_login", None),
            )
        except Exception:
            log.warning(
                "could not read PR #%s, or who wrote what is on it, for "
                "developer report revision %s",
                report.pr_number, report.report_revision, exc_info=True,
            )
            lookup = ReportLookup(ReportPresence.UNCONFIRMED)
        return lookup

    def publish_developer_report(
        self, pr: PullRequest, report: _reports.DeveloperReport,
    ) -> ReportLookup:
        """Post `report` onto this pull request once, and say where it stands.

        `ReportRefusedError` before any request when the report names another
        pull request or would not fit in one comment. Then the thread is read,
        and only ABSENT is posted onto; every other reading is handed back as
        it came. A post that raised is UNCONFIRMED whatever raised it: a
        timeout after GitHub accepted the comment and a refusal before it did
        look alike from here, and the next call's read tells them apart.
        """
        body = _reports.render_developer_report(report)
        lookup = self.find_developer_report(pr, report)
        if lookup.presence is not ReportPresence.ABSENT:
            return lookup
        try:
            posted = self._post_report(pr, body)
        except Exception:
            log.warning(
                "could not confirm developer report revision %s on PR #%s",
                report.report_revision, report.pr_number, exc_info=True,
            )
            return ReportLookup(ReportPresence.UNCONFIRMED)
        return ReportLookup(ReportPresence.PRESENT, posted)

    def reread_report_location(
        self, location: ReportLocation, *, content_sha256: str,
    ) -> ReportLookup:
        """Whether `location` still holds exactly the content revision named.

        Fetched afresh rather than read off an object a caller already holds,
        since what is proved is the content NOW: a human editing a report after
        it was verified moves it off that revision. Whether whoever wrote what
        was found may be trusted is the caller's question, so the comment or
        pull request is handed back with the answer.
        """
        try:
            found, body = self._location_content(location)
        except Exception:
            log.warning(
                "could not reread the developer report at %s", location,
                exc_info=True,
            )
            return ReportLookup(ReportPresence.UNCONFIRMED)
        return _report_at(found, body, content_sha256)

    def _location_content(self, location: ReportLocation) -> tuple[Any, str | None]:
        """What sits at `location` now and its body, or `(None, None)` for nothing."""
        pull_request = self._fetch_report_pull(location.pr_number)
        if location.comment_id is None:
            return pull_request, pull_request.body
        found = next(
            (
                posted for posted in self._report_thread(pull_request)
                if posted.id == location.comment_id
            ),
            None,
        )
        return found, getattr(found, "body", None)

    def _fetch_report_pull(self, pr_number: int) -> PullRequest:
        """One pull request, fetched from GitHub rather than from memory."""
        return self.repo.get_pull(pr_number)

    def _report_thread(self, pr: PullRequest) -> list[IssueComment]:
        """Every conversation comment on one pull request, read in full."""
        return list(pr.get_issue_comments())

    def _post_report(self, pr: PullRequest, body: str) -> IssueComment:
        """Append one conversation comment to one pull request."""
        return pr.create_issue_comment(body)


def _refuse_another_pull_request(
    pr: PullRequest, report: _reports.DeveloperReport,
) -> None:
    """Refuse looking for a report on a pull request it does not name.

    The rendering says which pull request it reports on, so on another thread
    it is a report about somewhere else -- and found there, a retry would take
    it as having landed where it belongs.
    """
    if pr.number != report.pr_number:
        raise _reports.ReportRefusedError(
            f"a developer report for PR #{report.pr_number} "
            f"cannot go onto PR #{pr.number}",
        )


def _report_on_thread(
    thread: Iterable[Any],
    report: _reports.DeveloperReport,
    *,
    bot_login: str | None,
) -> ReportLookup:
    """What one read thread holds for `report`'s transaction."""
    expected = _reports.render_developer_report(report)
    claimants = [
        posted for posted in thread
        if _comments.carries_own_marker(
            (posted,), report.receipt_scope, bot_login=bot_login,
        )
    ]
    exact = next((posted for posted in claimants if posted.body == expected), None)
    if exact is not None:
        return ReportLookup(ReportPresence.PRESENT, exact)
    if claimants:
        return ReportLookup(ReportPresence.CHANGED, claimants[0])
    return ReportLookup(ReportPresence.ABSENT)


def _report_at(found: Any, body: str | None, content_sha256: str) -> ReportLookup:
    """What one reread location holds against the revision somebody verified.

    A location holding nothing -- gone, or blank -- is ABSENT rather than a
    revision that happens to differ: nothing is there to have been edited.
    """
    if found is None or not isinstance(body, str) or not body.strip():
        return ReportLookup(ReportPresence.ABSENT)
    if _reports.content_digest(body) == content_sha256:
        return ReportLookup(ReportPresence.PRESENT, found)
    return ReportLookup(ReportPresence.CHANGED, found)
