# Copyright 2026 Geser Dugarov
# SPDX-License-Identifier: Apache-2.0
"""Publishing, finding, and rereading developer reports on a pull request.

One contract, held against the real client and against the shared fake: which
reading licenses a post, what an unanswered request is answered with, that a
retry finds what an earlier attempt landed, that ownership takes our author and
our exact rendering together, and that the description is never written.
"""
from __future__ import annotations

import unittest

from orchestrator.github.developer_reports import (
    ReportRefusedError,
    content_digest,
    render_developer_report,
)
from orchestrator.github.pinned_state import MAX_PINNED_BODY
from orchestrator.github.pull_request_reports import (
    ReportLocation,
    ReportLookup,
    ReportPresence,
)
from tests.github import report_test_support as support
from tests.support.fakes import make_developer_report

_GITHUB_LOG = "orchestrator.github"
_WARNING = "WARNING"
_HUMAN_LOGIN = "alice"
_MISSING_PR_NUMBER = 99
_REPORT = make_developer_report(support.PR_NUMBER)
# The next report on the same commit: another transaction rather than a retry.
_LATER_REPORT = make_developer_report(
    support.PR_NUMBER,
    report_revision=2,
    receipt="issue-7-report-2",
    text="Reworded the summary the reviewer asked about.",
)
_HUMAN_REPORT = "## Report\n\nEverything the reviewer asked for is done."


def _publish(case, report=_REPORT) -> ReportLookup:
    """Publish one report onto the case's pull request."""
    return case.gh.publish_developer_report(case.pull_request, report)


def _read_back(case, where: tuple[int, int | None], verified: str) -> tuple:
    """Reread one location against the revision of `verified`: (presence, found)."""
    reading = case.gh.reread_report_location(
        ReportLocation(*where), content_sha256=content_digest(verified),
    )
    return reading.presence, reading.found


class _PublicationContract:
    """A report is appended once beside the description, and only ours counts."""

    def test_a_report_is_appended_once(self) -> None:
        # A retry finds what the first call posted instead of posting again, and
        # neither writes the description: the closing reference, attribution,
        # legacy tail, and maintainer's sentence survive because nothing
        # rewrote them.
        first, again = [_publish(self) for _ in range(2)]

        posted = self.pull_request.issue_comments
        self.assertEqual(
            [comment.body for comment in posted], [render_developer_report(_REPORT)],
        )
        self.assertEqual(posted[0].user.login, support.BOT_LOGIN)
        self.assertEqual(first, ReportLookup(ReportPresence.PRESENT, posted[0]))
        self.assertIs(again.presence, ReportPresence.PRESENT)
        self.assertIs(again.found, first.found)
        self.assertEqual(self.pull_request.body, support.LEGACY_BODY)
        self.assertEqual(self.description_writes(), [])

    def test_a_later_report_is_a_second_comment(self) -> None:
        _publish(self)

        later = _publish(self, _LATER_REPORT)

        self.assertIs(later.presence, ReportPresence.PRESENT)
        self.assertEqual(
            [comment.body for comment in self.pull_request.issue_comments],
            [render_developer_report(_REPORT), render_developer_report(_LATER_REPORT)],
        )

    def test_a_pasted_copy_proves_nothing(self) -> None:
        # The header is an HTML comment anybody can copy. Under another author
        # it neither satisfies the retry nor holds the post back.
        self.seed(render_developer_report(_REPORT), login=_HUMAN_LOGIN)

        found = self.gh.find_developer_report(self.pull_request, _REPORT)
        published = _publish(self)

        self.assertEqual(found, ReportLookup(ReportPresence.ABSENT))
        self.assertIs(published.presence, ReportPresence.PRESENT)
        self.assertEqual(published.found.user.login, support.BOT_LOGIN)

    def test_our_edited_report_holds_the_post(self) -> None:
        # A maintainer's edit leaves the comment attributed to us and its
        # receipt naming this transaction, so a second comment would be a
        # second claim to it -- the caller is told instead.
        edited = self.seed(
            render_developer_report(_REPORT).replace("Implemented", "Skipped"),
            login=support.BOT_LOGIN,
        )

        held = _publish(self)

        self.assertEqual(held, ReportLookup(ReportPresence.CHANGED, edited))
        self.assertEqual(self.pull_request.issue_comments, [edited])


class _RecoveryContract:
    """Nothing unanswered counts as published, and a reread is exact."""

    def test_an_unpublishable_report_asks_nothing(self) -> None:
        # Every read fails here, so a report that reached the thread would come
        # back unconfirmed: the refusal is what proves nothing was asked.
        self.refuse(support.UNREADABLE)
        oversized = make_developer_report(support.PR_NUMBER, text="x" * MAX_PINNED_BODY)
        elsewhere = make_developer_report(support.OTHER_PR_NUMBER)
        for report in (oversized, elsewhere):
            with (
                self.subTest(pr_number=report.pr_number, length=len(report.text)),
                self.assertRaises(ReportRefusedError),
            ):
                _publish(self, report)
        self.assertEqual(self.pull_request.issue_comments, [])

    def test_unanswered_is_unconfirmed_until_reread(self) -> None:
        # (how the request went unanswered, comments GitHub holds afterwards)
        for failure, landed in (
            (support.UNREADABLE, 0),
            (support.REFUSED, 0),
            (support.LOST, 1),
        ):
            with self.subTest(failure=failure):
                self.setUp()
                self.refuse(failure)
                with self.assertLogs(_GITHUB_LOG, _WARNING):
                    unanswered = _publish(self)
                held = len(self.pull_request.issue_comments)
                self.refuse(None)

                retried = _publish(self)

                self.assertEqual(unanswered, ReportLookup(ReportPresence.UNCONFIRMED))
                self.assertEqual(held, landed)
                self.assertIs(retried.presence, ReportPresence.PRESENT)
                self.assertEqual(
                    [comment.body for comment in self.pull_request.issue_comments],
                    [render_developer_report(_REPORT)],
                )

    def test_a_location_is_reread_exactly(self) -> None:
        human = self.seed(_HUMAN_REPORT, login=_HUMAN_LOGIN)
        _publish(self)
        # (where, the revision somebody verified) -> (presence, what is found)
        expected = {
            ((support.PR_NUMBER, human.id), _HUMAN_REPORT): (ReportPresence.PRESENT, human),
            (
                (support.PR_NUMBER, self.pull_request.issue_comments[-1].id),
                render_developer_report(_REPORT),
            ): (ReportPresence.PRESENT, self.pull_request.issue_comments[-1]),
            ((support.PR_NUMBER, None), support.LEGACY_BODY): (
                ReportPresence.PRESENT, self.pull_request,
            ),
            ((support.PR_NUMBER, human.id), f"{_HUMAN_REPORT}."): (ReportPresence.CHANGED, human),
            ((support.PR_NUMBER, None), "Resolves #7"): (
                ReportPresence.CHANGED, self.pull_request,
            ),
            # The same comment id asked of another pull request is not there.
            ((support.OTHER_PR_NUMBER, human.id), _HUMAN_REPORT): (ReportPresence.ABSENT, None),
            ((support.OTHER_PR_NUMBER, None), ""): (ReportPresence.ABSENT, None),
        }
        for (where, verified), answer in expected.items():
            with self.subTest(where=where, verified=verified):
                self.assertEqual(_read_back(self, where, verified), answer)

    def test_an_unreadable_location_is_unconfirmed(self) -> None:
        human = self.seed(_HUMAN_REPORT, login=_HUMAN_LOGIN)
        self.refuse(support.UNREADABLE)
        for where in (
            (support.PR_NUMBER, human.id),
            (support.PR_NUMBER, None),
            (_MISSING_PR_NUMBER, None),
        ):
            with self.subTest(where=where), self.assertLogs(_GITHUB_LOG, _WARNING):
                self.assertEqual(
                    _read_back(self, where, _HUMAN_REPORT),
                    (ReportPresence.UNCONFIRMED, None),
                )


class _ReportContract(_PublicationContract, _RecoveryContract):
    """Everything the real client and the shared fake answer alike."""


class WireClientReportTest(support.WireBackend, _ReportContract, unittest.TestCase):
    """The contract, over the requests production makes."""


class FakeClientReportTest(support.FakeBackend, _ReportContract, unittest.TestCase):
    """The contract, over the double stage tests publish through."""


if __name__ == "__main__":
    unittest.main()
